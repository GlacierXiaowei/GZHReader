from __future__ import annotations

from datetime import date, datetime, timedelta

from gzhreader_core.credentials import CredentialVault
from gzhreader_core.scheduler import Scheduler
from gzhreader_core.storage import Storage


def test_credentials_round_trip_and_clear(tmp_path):
    vault = CredentialVault(tmp_path)
    vault.save("weread", {"cookie": "secret-cookie", "ticket": "secret-ticket"})
    stored = (tmp_path / "weread.bin").read_bytes()
    assert b"secret-cookie" not in stored
    assert vault.load("weread")["ticket"] == "secret-ticket"
    vault.clear("weread")
    assert vault.load("weread") == {}


def test_scheduler_reschedules_and_respects_briefing_skip(tmp_path):
    storage = Storage(tmp_path / "data.db")
    scheduler = Scheduler(storage, lambda: {}, lambda: {}, lambda *_: None)
    storage.update_settings({"refresh_minutes": 15})
    status = scheduler.reschedule(reset=True)
    next_refresh = datetime.fromisoformat(status["next_refresh_at"])
    assert timedelta(minutes=14) < next_refresh - datetime.now().astimezone() < timedelta(minutes=16)
    storage.update_settings({"briefing_time": "00:01", "briefing_skip_day": date.today().isoformat()})
    assert scheduler.briefing_due_now() is False
