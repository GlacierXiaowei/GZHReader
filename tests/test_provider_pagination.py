from __future__ import annotations

from pathlib import Path

import httpx

from gzhreader_core.credentials import CredentialVault
from gzhreader_core.models import SourceProfile
from gzhreader_core.providers.weread import WeReadError, WeReadProvider


class FakeClient:
    pages = []
    content = ""
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, url, params, headers):
        if url.endswith("/articles"):
            payload = self.pages.pop(0)
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))
        return httpx.Response(200, text=self.content, request=httpx.Request("GET", url))


def review(review_id, ts):
    return {"review": {"reviewId": review_id, "createTime": ts, "mpInfo": {"title": review_id, "originalId": review_id, "time": ts}}}


def test_pagination_uses_group_offsets_and_stops_at_cursor(tmp_path):
    vault = CredentialVault(tmp_path)
    vault.save("weread", {"cookie": "a=b", "ticket": "ticket"})
    FakeClient.pages = [
        {"reviews": [{"subReviews": [review("new", 200)]}]},
        {"reviews": [{"subReviews": [review("old", 100)]}]},
    ]
    provider = WeReadProvider(vault, client_factory=FakeClient, sleep=lambda _: None)
    batch = provider.list_articles(SourceProfile("MP_WXS_1", "公众号"), previous_cursor=100, max_pages=20)
    assert [item.origin_id for item in batch.articles] == ["new"]
    assert batch.reached_cursor
    assert batch.pages_scanned == 2


def test_auth_error_is_classified(tmp_path):
    vault = CredentialVault(tmp_path)
    vault.save("weread", {"cookie": "a=b", "ticket": "ticket"})
    FakeClient.pages = [{"errCode": -2041, "errMsg": "expired"}]
    provider = WeReadProvider(vault, client_factory=FakeClient, sleep=lambda _: None)
    try:
        provider.list_articles(SourceProfile("MP_WXS_1", "公众号"))
    except WeReadError as exc:
        assert exc.reconnect
    else:
        raise AssertionError("auth error was not raised")
