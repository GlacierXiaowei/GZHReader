from __future__ import annotations

from typing import Protocol

from ..models import ProviderBatch, SourceProfile


class SourceProvider(Protocol):
    def list_articles(self, source: SourceProfile, **kwargs) -> ProviderBatch: ...
    def fetch_content(self, review_id: str) -> str: ...
