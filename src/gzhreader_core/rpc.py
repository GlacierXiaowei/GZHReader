from __future__ import annotations

import json
import logging
import sys
import threading
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .ai import Summarizer
from .article_fetcher import ArticleContentFetcher
from .briefing import BriefingService
from .browser import WeReadLoginCapture
from .credentials import CredentialVault
from .fetch_config import ArticleFetchConfig, RSSConfig
from .logging_utils import configure_logging
from .paths import AppPaths, get_paths
from .platform_utils import open_local_path, open_web_url
from .providers import ArticleLinkResolver, WeReadProvider
from .scheduler import Scheduler
from .service import ReaderService
from .storage import Storage

logger = logging.getLogger(__name__)


class CoreApp:
    def __init__(self, emit, paths: AppPaths | None = None, start_scheduler: bool = True):
        self.emit = emit
        self.paths = paths or get_paths()
        configure_logging(self.paths.logs)
        self.storage = Storage(self.paths.db, self.paths.backups)
        self.vault = CredentialVault(self.paths.secrets)
        self.provider = WeReadProvider(self.vault)
        self.resolver = ArticleLinkResolver()
        self.summarizer = Summarizer(self.vault)
        self.fetcher = ArticleContentFetcher(ArticleFetchConfig(), RSSConfig())
        self.reader = ReaderService(self.storage, self.provider, self.resolver, self.fetcher, self.summarizer)
        self.briefing = BriefingService(self.storage, self.paths.briefings, self.summarizer)
        self.login = WeReadLoginCapture(self.paths.browser_profile, self.vault, self.provider.validate_credentials)
        self.scheduler = Scheduler(
            self.storage,
            lambda: self.reader.sync(self.emit),
            lambda: self.briefing.generate(date.today()),
            self.emit,
        )
        if start_scheduler:
            self.scheduler.start()

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "app.bootstrap":
            return self.bootstrap()
        if method == "app.health":
            return {"ok": True, "connection": self.provider.health().to_dict(), "scheduler": self.scheduler.status()}
        if method == "subscriptions.resolve_link":
            return self.reader.resolve_link(str(params["url"]))
        if method == "subscriptions.add":
            return self.reader.add_source(dict(params["source"]))
        if method == "subscriptions.list":
            return self.storage.sources()
        if method == "subscriptions.update":
            self.storage.set_source_enabled(str(params["source_id"]), bool(params["enabled"]))
            return {"ok": True}
        if method == "subscriptions.remove":
            self.storage.remove_source(str(params["source_id"]))
            return {"ok": True}
        if method == "subscriptions.sync":
            return self._background_sync(str(params.get("source_id") or ""), force=True)
        if method == "articles.list":
            return self.storage.articles(
                source_id=str(params.get("source_id") or ""),
                unread_only=bool(params.get("unread_only")),
                query=str(params.get("query") or ""),
                limit=min(max(int(params.get("limit") or 200), 1), 500),
            )
        if method == "articles.get":
            return self._require_article(int(params["article_id"]))
        if method == "articles.mark_read":
            self.storage.mark_read(int(params["article_id"]), bool(params.get("read", True)))
            return {"ok": True}
        if method == "articles.retry_summary":
            item = self._require_article(int(params["article_id"]))
            payload = self.summarizer.summarize(
                item["title"], item["content"] or item.get("digest", ""), item["source_name"]
            )
            self.storage.update_summary(item["id"], payload)
            self.emit("summary.completed", {"article_id": item["id"]})
            return self._require_article(item["id"])
        if method == "briefings.list":
            return self.storage.briefings()
        if method == "briefings.get":
            return self.storage.briefing(str(params.get("day") or date.today().isoformat()))
        if method == "briefings.generate":
            self.storage.update_settings({"briefing_skip_day": ""})
            result = self.briefing.generate(date.fromisoformat(str(params.get("day") or date.today().isoformat())))
            self.emit("briefing.ready", {"day": result["day"], "file_path": result["file_path"]})
            return result
        if method == "briefings.export":
            briefing = self.storage.briefing(str(params.get("day") or date.today().isoformat()))
            if not briefing:
                raise ValueError("这一天还没有简报")
            return {"file_path": briefing["file_path"]}
        if method == "settings.get":
            return {**self.storage.settings(), "ai": self.summarizer.public_config()}
        if method == "settings.update":
            return self._update_settings(dict(params.get("settings") or {}))
        if method == "ai.test_connection":
            return self.summarizer.test(params)
        if method == "auth.start":
            return self._background_auth(str(params["source_id"]))
        if method == "auth.cancel":
            self.login.cancel()
            return {"ok": True}
        if method == "auth.reconnect":
            source_id = str(params.get("source_id") or self._first_source_id())
            if not source_id:
                raise ValueError("请先添加一个公众号")
            return self._background_auth(source_id)
        if method == "scheduler.status":
            return self.scheduler.status()
        if method == "scheduler.run_now":
            return self._background_sync(str(params.get("source_id") or ""), force=True)
        if method == "system.open_url":
            open_web_url(str(params["url"]))
            return {"ok": True}
        if method == "system.open_path":
            open_local_path(str(params["path"]))
            return {"ok": True}
        if method == "core.shutdown":
            self.shutdown()
            return {"ok": True, "shutdown": True}
        raise KeyError("不支持的操作")

    def bootstrap(self) -> dict[str, Any]:
        health = self.provider.health()
        return {
            "dashboard": self.storage.dashboard(),
            "sources": self.storage.sources(),
            "articles": self.storage.articles(limit=200),
            "briefings": self.storage.briefings(),
            "settings": {**self.storage.settings(), "ai": self.summarizer.public_config()},
            "connection": health.to_dict(),
            "scheduler": self.scheduler.status(),
        }

    def shutdown(self) -> None:
        self.login.cancel()
        self.scheduler.stop()

    def _update_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        old = self.storage.settings()
        ai = values.pop("ai", None)
        if ai is not None:
            self.summarizer.save(dict(ai))
        updated = self.storage.update_settings(values)
        refresh_changed = any(
            old.get(key) != updated.get(key) for key in ("refresh_minutes", "refresh_paused")
        )
        if refresh_changed:
            self.scheduler.reschedule(reset=True)
        else:
            self.scheduler.reschedule(reset=False)
        briefing_changed = (
            old.get("briefing_time") != updated.get("briefing_time")
            or old.get("briefing_enabled") != updated.get("briefing_enabled")
        )
        due_now = briefing_changed and self.scheduler.briefing_due_now()
        if due_now:
            updated = self.storage.update_settings({"briefing_skip_day": date.today().isoformat()})
        return {**updated, "ai": self.summarizer.public_config(), "briefing_due_now": due_now}

    def _require_article(self, article_id: int) -> dict[str, Any]:
        item = self.storage.article(article_id)
        if not item:
            raise ValueError("文章不存在或已经删除")
        return item

    def _first_source_id(self) -> str:
        sources = self.storage.sources()
        return str(sources[0]["id"]) if sources else ""

    def _background_sync(self, source_id: str = "", force: bool = False) -> dict[str, Any]:
        def run() -> None:
            self.reader.sync(self.emit, source_id, force=force)

        threading.Thread(target=run, name="gzhreader-manual-sync", daemon=True).start()
        return {"accepted": True}

    def _background_auth(self, source_id: str) -> dict[str, Any]:
        def run() -> None:
            try:
                result = self.login.run(source_id, self.emit)
                if result.get("ok"):
                    self.storage.set_connection_state("weread", "ready", "微信读书已连接")
                    self.reader.sync(self.emit, source_id, force=True)
            except Exception as exc:
                logger.exception("WeRead login failed")
                self.emit("auth.failed", {"message": str(exc)})

        threading.Thread(target=run, name="gzhreader-auth", daemon=True).start()
        return {"accepted": True}


class RpcServer:
    def __init__(self, app_factory=CoreApp):
        self.lock = threading.Lock()
        self.app = app_factory(self.emit)

    def write(self, payload: dict[str, Any]) -> None:
        with self.lock:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=self._json_default) + "\n")
            sys.stdout.flush()

    @staticmethod
    def _json_default(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(f"无法序列化 {type(value).__name__}")

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        self.write({"jsonrpc": "2.0", "event": event, "payload": payload})

    def run(self) -> None:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        self.emit("core.ready", {"version": "3.0.0"})
        for line in sys.stdin:
            if not line.strip():
                continue
            request: dict[str, Any] | None = None
            try:
                request = json.loads(line.lstrip("\ufeff"))
                if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                    raise ValueError("请求格式无效")
                result = self.app.dispatch(request["method"], request.get("params") or {})
                if request.get("id") is not None:
                    self.write({"jsonrpc": "2.0", "id": request["id"], "result": result})
                if isinstance(result, dict) and result.get("shutdown"):
                    break
            except Exception as exc:
                logger.exception("RPC request failed")
                request_id = request.get("id") if isinstance(request, dict) else None
                self.write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": str(exc) or "操作没有完成"},
                    }
                )
        self.app.shutdown()


def main() -> None:
    RpcServer().run()

