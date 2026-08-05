from __future__ import annotations

import random
import threading
from datetime import date, datetime, timedelta
from typing import Callable


class Scheduler:
    def __init__(self, storage, sync: Callable[[], dict], briefing: Callable[[], dict], emit):
        self.storage = storage
        self.sync = sync
        self.briefing = briefing
        self.emit = emit
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._run_lock = threading.Lock()

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.reschedule(reset=False)
        self.thread = threading.Thread(target=self._loop, name="gzhreader-scheduler", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)

    def reschedule(self, reset: bool = True) -> dict:
        settings = self.storage.settings()
        minutes = int(settings.get("refresh_minutes", 60))
        if minutes <= 0 or settings.get("refresh_paused", False):
            next_refresh = ""
        else:
            current = str(settings.get("next_refresh_at") or "")
            if reset or not current:
                next_refresh = (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
            else:
                next_refresh = current
        self.storage.update_settings({"next_refresh_at": next_refresh})
        self.wake_event.set()
        return self.status()

    def status(self) -> dict:
        settings = self.storage.settings()
        return {
            "running": bool(self.thread and self.thread.is_alive()),
            "paused": bool(settings.get("refresh_paused", False)),
            "next_refresh_at": settings.get("next_refresh_at", ""),
            "briefing_enabled": settings.get("briefing_enabled", True),
            "briefing_time": settings.get("briefing_time", "21:30"),
        }

    def run_now(self) -> dict:
        if not self._run_lock.acquire(blocking=False):
            return {"accepted": False, "message": "正在刷新，请稍候"}
        try:
            return self.sync()
        finally:
            self._run_lock.release()

    def briefing_due_now(self) -> bool:
        settings = self.storage.settings()
        if (
            not settings.get("briefing_enabled", True)
            or self.storage.briefing(date.today())
            or settings.get("briefing_skip_day") == date.today().isoformat()
        ):
            return False
        try:
            hour, minute = map(int, str(settings.get("briefing_time", "21:30")).split(":"))
        except ValueError:
            return False
        scheduled = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        return datetime.now() >= scheduled

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                self.emit("core.error", {"message": "后台任务暂时未能完成", "detail": str(exc)})
            self.wake_event.wait(20)
            self.wake_event.clear()

    def _tick(self) -> None:
        settings = self.storage.settings()
        now = datetime.now().astimezone()
        next_value = str(settings.get("next_refresh_at") or "")
        if int(settings.get("refresh_minutes", 60)) > 0 and not settings.get("refresh_paused", False) and next_value:
            try:
                next_refresh = datetime.fromisoformat(next_value)
            except ValueError:
                self.reschedule(reset=True)
                next_refresh = None
            if next_refresh and now >= next_refresh:
                self.run_now()
                minutes = int(settings.get("refresh_minutes", 60))
                next_time = now + timedelta(minutes=minutes, seconds=random.randint(-300, 300))
                self.storage.update_settings({"next_refresh_at": next_time.isoformat(timespec="seconds")})
        if self.briefing_due_now():
            result = self.briefing()
            self.emit("briefing.ready", {"day": result["day"], "file_path": result["file_path"]})
