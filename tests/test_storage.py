from __future__ import annotations

from datetime import date, datetime, timezone

from gzhreader_core.models import ArticleRecord, SourceProfile
from gzhreader_core.storage import Storage


def test_storage_search_unread_and_briefing(tmp_path):
    storage = Storage(tmp_path / "data.db", tmp_path / "backups")
    storage.upsert_source(SourceProfile("MP_WXS_1", "测试公众号"))
    article_id, inserted = storage.insert_article(
        ArticleRecord(
            source_id="MP_WXS_1",
            origin_id="review-1",
            title="一篇关于本地阅读的文章",
            url="https://mp.weixin.qq.com/s/demo",
            published_at=datetime.now(timezone.utc),
            content="正文讨论本地工作台和信息整理。",
        )
    )
    assert inserted
    storage.update_summary(article_id, {"summary": "本地阅读摘要", "key_points": ["本地保存"], "tags": ["阅读"], "takeaway": "减少噪音", "status": "done"})
    assert storage.articles(query="本地阅读")[0]["id"] == article_id
    assert storage.dashboard()["unread_count"] == 1
    storage.mark_read(article_id)
    assert storage.dashboard()["unread_count"] == 0
    storage.save_briefing(date.today(), "概览", "# 简报", "brief.md", 1)
    storage.save_briefing(date.today(), "新概览", "# 新简报", "brief.md", 1)
    assert storage.briefing(date.today())["overview"] == "新概览"
    assert list((tmp_path / "backups").glob("*.db"))


def test_settings_validation(tmp_path):
    storage = Storage(tmp_path / "data.db")
    assert storage.update_settings({"refresh_minutes": 15})["refresh_minutes"] == 15
    try:
        storage.update_settings({"refresh_minutes": 17})
    except ValueError as exc:
        assert "刷新频率" in str(exc)
    else:
        raise AssertionError("invalid refresh option accepted")


def test_connection_cooldown_round_trip(tmp_path):
    storage = Storage(tmp_path / "data.db")
    until = "2026-08-06T03:00:00+00:00"
    storage.set_connection_state("weread", "cooldown", "????", True, until)
    state = storage.connection_state("weread")
    assert state["state"] == "cooldown"
    assert state["reconnect_required"] == 1
    assert state["cooldown_until"] == until
