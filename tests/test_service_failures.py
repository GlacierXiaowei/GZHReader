from __future__ import annotations

from gzhreader_core.credentials import CredentialVault
from gzhreader_core.models import SourceProfile
from gzhreader_core.providers import WeReadError
from gzhreader_core.service import ReaderService
from gzhreader_core.storage import Storage


class FailedProvider:
    def list_articles(self, source, **kwargs):
        raise WeReadError("network_error", "网络连接失败")
    def mark_error(self, error): pass


class Dummy:
    pass


def test_failed_sync_does_not_advance_cursor(tmp_path):
    storage = Storage(tmp_path / "data.db")
    storage.upsert_source(SourceProfile("MP_WXS_1", "公众号"))
    service = ReaderService(storage, FailedProvider(), Dummy(), Dummy(), Dummy(), sleep=lambda _: None)
    result = service.sync(lambda *_: None, force=True)
    source = storage.source("MP_WXS_1")
    assert result["errors"]
    assert source["sync_cursor"] == 0
    assert source["next_attempt_at"]


class RiskProvider:
    def __init__(self, vault):
        self.vault = vault

    def list_articles(self, source, **kwargs):
        raise WeReadError(
            -2041,
            "微信读书操作过于频繁，请 24 小时后再重新连接",
            reconnect=True,
            cooldown=True,
            cooldown_minutes=24 * 60,
        )

    def mark_error(self, error):
        pass


def test_risk_control_clears_credentials_and_sets_cooldown(tmp_path):
    storage = Storage(tmp_path / "data.db")
    storage.upsert_source(SourceProfile("MP_WXS_1", "公众号"))
    vault = CredentialVault(tmp_path / "secrets")
    vault.save("weread", {"cookie": "secret", "ticket": "ticket"})
    service = ReaderService(storage, RiskProvider(vault), Dummy(), Dummy(), Dummy(), sleep=lambda _: None)

    result = service.sync(lambda *_: None, force=True)

    assert result["errors"]
    assert vault.load("weread") == {}
    assert storage.connection_state("weread")["state"] == "cooldown"
    source = storage.source("MP_WXS_1")
    assert source["status"] == "limited"
    assert source["cooldown_until"]
