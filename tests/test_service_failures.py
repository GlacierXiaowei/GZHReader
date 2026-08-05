from __future__ import annotations

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
