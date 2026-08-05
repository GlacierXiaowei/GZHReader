from __future__ import annotations

import base64
import hashlib
import html as html_module
import logging
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from ..models import SourceProfile

logger = logging.getLogger(__name__)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

HTTP_HEADERS = {
    "User-Agent": DESKTOP_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    "Cache-Control": "no-cache",
}

CHALLENGE_URL_MARKERS = (
    "/mp/wappoc_appmsgcaptcha",
    "appmsgcaptcha",
    "poc_token=",
)

CHALLENGE_HTML_MARKERS = (
    "wappoc_appmsgcaptcha",
    "poc_token",
    "请完成验证",
    "环境异常",
    "访问过于频繁",
    "操作过于频繁",
)


class ArticleLinkResolver:
    def __init__(
        self,
        profile_dir: Path | None = None,
        progress: Callable[[dict], None] | None = None,
        browser_timeout_seconds: int = 100,
    ) -> None:
        self.profile_dir = profile_dir
        self.progress = progress
        self.browser_timeout_seconds = browser_timeout_seconds

    def resolve_source(self, url: str) -> dict:
        clean_url = url.strip()
        parsed = urlparse(clean_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"mp.weixin.qq.com", "weixin.qq.com"}:
            raise ValueError("请粘贴微信公众号文章链接")

        html = ""
        final_url = clean_url
        try:
            self._emit_progress("reading", "正在读取文章信息")
            with httpx.Client(timeout=20, follow_redirects=True, headers=HTTP_HEADERS) as client:
                response = client.get(clean_url)
                response.raise_for_status()
                html = response.text
                final_url = str(response.url)
        except Exception as exc:
            logger.warning("Article link HTTP fetch failed for %s: %s", clean_url, exc)
            html, final_url = self._browser_fetch(clean_url)
        else:
            value = self._extract(html, final_url)
            challenge = self._is_challenge(html, final_url)
            if challenge or not value["biz"] or not value["name"]:
                logger.info(
                    "Article link requires browser fallback: url=%s final_url=%s challenge=%s has_biz=%s has_name=%s",
                    clean_url,
                    final_url,
                    challenge,
                    bool(value["biz"]),
                    bool(value["name"]),
                )
                html, final_url = self._browser_fetch(clean_url)

        value = self._extract(html, final_url)
        if not value["biz"] or not value["name"]:
            if self._is_challenge(html, final_url):
                raise ValueError("微信仍需要验证，请重新识别并在打开的浏览器中完成验证")
            if not html:
                raise ValueError("内容暂时无法读取，请检查网络后再试")
            raise ValueError("没有读取到公众号信息，请换一篇该公众号近期文章再试")

        source_id = f"MP_WXS_{self.decode_biz(value['biz'])}"
        source = SourceProfile(
            id=source_id,
            name=value["name"],
            avatar=value["avatar"],
            intro=value["intro"],
            sample_url=final_url,
        ).to_dict()
        source["sample_article"] = {
            "origin_id": value["article_id"],
            "title": value["title"] or "已添加的公众号文章",
            "url": final_url,
            "published_at": value["published_at"],
            "author": value["name"],
            "cover": value["cover"],
        }
        self._emit_progress("completed", f"已识别公众号：{value['name']}")
        return source

    def _browser_fetch(self, url: str) -> tuple[str, str]:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise ValueError("无法打开本机浏览器，请确认 Edge 或 Chrome 可以正常使用") from exc

        self._emit_progress("opening_browser", "正在打开浏览器读取文章")
        temporary_profile = None
        profile_dir = self.profile_dir
        if profile_dir is None:
            temporary_profile = tempfile.TemporaryDirectory(prefix="gzhreader-link-")
            profile_dir = Path(temporary_profile.name)
        profile_dir.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as playwright:
                errors: list[str] = []
                context = None
                for launch in ({"channel": "msedge"}, {"channel": "chrome"}):
                    try:
                        context = playwright.chromium.launch_persistent_context(
                            str(profile_dir),
                            headless=False,
                            viewport={"width": 1080, "height": 760},
                            args=["--disable-extensions", "--disable-sync", "--no-first-run"],
                            **launch,
                        )
                        break
                    except Exception as exc:
                        errors.append(str(exc))
                if context is None:
                    logger.warning("Unable to launch Edge/Chrome for link resolution: %s", "; ".join(errors))
                    raise ValueError("未找到可用的 Edge 或 Chrome 浏览器")

                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    except PlaywrightTimeoutError:
                        # 验证页或较慢的文章仍可能已经显示，继续读取当前页面。
                        pass

                    deadline = time.time() + self.browser_timeout_seconds
                    normal_page_deadline = time.time() + 8
                    challenge_seen = False
                    last_html = ""
                    last_url = page.url or url
                    while time.time() < deadline:
                        try:
                            last_html = page.content()
                            last_url = page.url or url
                        except PlaywrightError as exc:
                            raise ValueError("识别窗口已关闭，请重新尝试") from exc

                        value = self._extract(last_html, last_url)
                        if value["biz"] and value["name"]:
                            return last_html, last_url

                        challenge = self._is_challenge(last_html, last_url)
                        if challenge and not challenge_seen:
                            challenge_seen = True
                            self._emit_progress(
                                "waiting_verification",
                                "微信需要确认访问，请在打开的浏览器中完成验证",
                            )
                        if not challenge and not challenge_seen and time.time() >= normal_page_deadline:
                            return last_html, last_url
                        page.wait_for_timeout(500)

                    if challenge_seen:
                        raise ValueError("验证等待超时，请重新识别并在浏览器中完成验证")
                    return last_html, last_url
                finally:
                    context.close()
        finally:
            if temporary_profile is not None:
                temporary_profile.cleanup()

    @classmethod
    def _is_challenge(cls, html: str, final_url: str) -> bool:
        lowered_url = final_url.lower()
        lowered_html = html.lower()
        return any(marker in lowered_url for marker in CHALLENGE_URL_MARKERS) or any(
            marker.lower() in lowered_html for marker in CHALLENGE_HTML_MARKERS
        )

    def _emit_progress(self, stage: str, message: str) -> None:
        if self.progress is None:
            return
        try:
            self.progress({"stage": stage, "message": message})
        except Exception:
            logger.debug("Unable to emit link resolution progress", exc_info=True)

    def _extract(self, html: str, final_url: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        search_html = html_module.unescape(html)

        def js(*names: str) -> str:
            for name in names:
                escaped = re.escape(name)
                patterns = (
                    rf"(?:var\s+|window\.)?{escaped}\s*=\s*['\"](.*?)['\"]\s*[;,]",
                    rf"['\"]?{escaped}['\"]?\s*:\s*['\"](.*?)['\"]\s*[,}}]",
                    rf"(?:var\s+|window\.)?{escaped}\s*=\s*(\d+)\s*[;,]",
                    rf"['\"]?{escaped}['\"]?\s*:\s*(\d+)\s*[,}}]",
                )
                for pattern in patterns:
                    match = re.search(pattern, search_html, flags=re.S)
                    if match:
                        return self._clean_js_string(match.group(1))
            return ""

        def meta(*, name: str = "", property_name: str = "") -> str:
            attrs = {"name": name} if name else {"property": property_name}
            node = soup.find("meta", attrs=attrs)
            return str(node.get("content") or "").strip() if node else ""

        query = parse_qs(urlparse(final_url).query)
        name_node = (
            soup.select_one("#js_name")
            or soup.select_one(".profile_nickname")
            or soup.select_one(".wx_follow_nickname")
            or soup.select_one(".account_nickname")
        )
        title_node = soup.select_one("#activity-name") or soup.select_one("h1.rich_media_title")
        timestamp = js("ct", "publish_time", "create_time")
        published_meta = meta(property_name="article:published_time")
        try:
            published_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            try:
                published_at = datetime.fromisoformat(published_meta.replace("Z", "+00:00")).isoformat()
            except (TypeError, ValueError):
                published_at = datetime.now(timezone.utc).isoformat()

        mid = (query.get("mid") or [""])[0] or js("mid", "appmsgid")
        idx = (query.get("idx") or [""])[0] or js("idx", "itemidx")
        sn = (query.get("sn") or [""])[0] or js("sn")
        article_seed = "-".join([mid, idx, sn]).strip("-")
        if not article_seed:
            article_seed = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:24]

        cover = meta(property_name="og:image") or meta(name="twitter:image")
        biz = js("biz", "__biz") or (query.get("__biz") or [""])[0]
        if not biz:
            biz_match = re.search(r"(?:[?&]|&amp;)__biz=([^&'\"\\\s<>]+)", search_html)
            if biz_match:
                biz = unquote(biz_match.group(1))

        name = (
            js("nickname", "user_name")
            or (name_node.get_text(" ", strip=True) if name_node else "")
            or meta(property_name="og:article:author")
            or meta(name="author")
        )
        return {
            "biz": biz,
            "name": name,
            "intro": js("profile_signature", "profile_signature_new") or meta(name="description") or meta(property_name="og:description"),
            "avatar": js("ori_head_img_url", "head_img", "round_head_img") or cover,
            "title": js("msg_title") or (title_node.get_text(" ", strip=True) if title_node else "") or meta(property_name="og:title"),
            "cover": cover,
            "article_id": article_seed,
            "published_at": published_at,
        }

    @staticmethod
    def _clean_js_string(value: str) -> str:
        value = value.replace(r"\/", "/").replace(r"\x26", "&")
        if "\\u" in value or "\\x" in value:
            try:
                value = bytes(value, "utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                pass
        return html_module.unescape(value).strip()

    @staticmethod
    def decode_biz(biz: str) -> str:
        candidate = biz.strip()
        try:
            padding = "=" * (-len(candidate) % 4)
            decoded = base64.b64decode(candidate + padding).decode("utf-8", errors="ignore").strip()
        except Exception:
            decoded = ""
        cleaned = "".join(ch for ch in (decoded or candidate) if ch.isalnum() or ch in {"_", "-"})
        if not cleaned:
            raise ValueError("公众号标识无效")
        return cleaned
