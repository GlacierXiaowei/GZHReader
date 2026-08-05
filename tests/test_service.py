from __future__ import annotations

from datetime import datetime, timezone

from gzhreader_core.models import ArticleRecord, ProviderBatch, SourceProfile
from gzhreader_core.service import ReaderService
from gzhreader_core.storage import Storage


class Provider:
    def list_articles(self, source, **kwargs):
        item = ArticleRecord(source.id, "r1", "新文章", "https://mp.weixin.qq.com/s/r1", datetime.now(timezone.utc), source.name)
        return ProviderBatch([item], int(item.published_at.timestamp()), True, 1)
    def fetch_content(self, review_id): return "完整正文"


class Resolver: pass
class Fetcher: pass
class Summarizer:
    def summarize(self, title, content, source): return {"summary": "摘要", "key_points": [], "tags": [], "takeaway": "结论", "status": "done"}


def test_sync_deduplicates_and_updates_cursor(tmp_path):
    storage = Storage(tmp_path / "data.db")
    storage.upsert_source(SourceProfile("MP_WXS_1", "公众号"))
    events = []
    service = ReaderService(storage, Provider(), Resolver(), Fetcher(), Summarizer(), sleep=lambda _: None)
    first = service.sync(lambda event, payload: events.append((event, payload)), force=True)
    second = service.sync(lambda event, payload: None, force=True)
    assert first["inserted"] == 1
    assert first["summarized"] == 1
    assert second["inserted"] == 0
    assert storage.source("MP_WXS_1")["sync_cursor"] > 0
    assert storage.article(1)["content"] == "完整正文"
    assert [event for event, _payload in events][-2:] == ["sync.completed", "articles.new_batch"]
