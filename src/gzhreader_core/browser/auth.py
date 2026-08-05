from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from ..credentials import CredentialVault


class WeReadLoginCapture:
    def __init__(self, profile_dir: Path, vault: CredentialVault, validator=None):
        self.profile_dir = profile_dir
        self.vault = vault
        self.validator = validator
        self._cancel = threading.Event()
        self._running = threading.Lock()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self, source_id: str, emit: Callable[[str, dict], None], timeout_seconds: int = 180) -> dict:
        if not self._running.acquire(blocking=False):
            return {"accepted": False, "message": "连接窗口已经打开"}
        self._cancel.clear()
        captured: dict[str, str | float] = {}
        emit("auth.progress", {"stage": "opening", "message": "正在打开微信读书"})
        try:
            with sync_playwright() as playwright:
                errors: list[str] = []
                context = None
                for launch in ({"channel": "msedge"}, {"channel": "chrome"}):
                    try:
                        context = playwright.chromium.launch_persistent_context(
                            str(self.profile_dir),
                            headless=False,
                            viewport={"width": 1120, "height": 760},
                            **launch,
                        )
                        break
                    except Exception as exc:
                        errors.append(str(exc))
                if context is None:
                    raise RuntimeError("未找到可用的 Edge 或 Chrome 浏览器")
                try:
                    page = context.pages[0] if context.pages else context.new_page()

                    def capture_request(request) -> None:
                        if "/web/mp/articles" not in request.url:
                            return
                        try:
                            headers = request.all_headers()
                            ticket = headers.get("x-wr-ticket", "")
                            cookies = context.cookies("https://weread.qq.com")
                            cookie = "; ".join(f"{item['name']}={item['value']}" for item in cookies)
                            if cookie and ticket:
                                captured.update(cookie=cookie, ticket=ticket, captured_at=time.time())
                        except Exception:
                            return

                    page.on("request", capture_request)
                    page.goto(
                        f"https://weread.qq.com/web/reader/{source_id}",
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    emit("auth.progress", {"stage": "waiting", "message": "请在浏览器中扫码登录，应用会自动完成连接"})
                    deadline = time.time() + timeout_seconds
                    last_reload = time.time()
                    while time.time() < deadline and not self._cancel.is_set() and not captured:
                        page.wait_for_timeout(500)
                        if time.time() - last_reload > 15:
                            page.reload(wait_until="domcontentloaded", timeout=30_000)
                            last_reload = time.time()
                    if self._cancel.is_set():
                        raise RuntimeError("已取消连接")
                    if not captured:
                        raise TimeoutError("连接超时，请重新尝试")
                    cookie = str(captured["cookie"])
                    ticket = str(captured["ticket"])
                    if self.validator:
                        self.validator(source_id, cookie, ticket)
                    self.vault.save("weread", captured)
                    emit("auth.completed", {"message": "微信读书已连接", "source_id": source_id})
                    return {"ok": True, "message": "微信读书已连接"}
                finally:
                    context.close()
        finally:
            self._running.release()
