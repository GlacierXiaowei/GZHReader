from __future__ import annotations
from dataclasses import dataclass,field

@dataclass(slots=True)
class ArticleFetchConfig:
    enabled: bool = True
    trigger: str = "missing_rss_content"
    mode: str = "hybrid"
    timeout_seconds: int = 20
    browser_channel_order: list[str] = field(default_factory=lambda:["msedge","chrome"])
    max_content_chars: int = 12000

@dataclass(slots=True)
class RSSConfig:
    timezone: str = "Asia/Shanghai"
