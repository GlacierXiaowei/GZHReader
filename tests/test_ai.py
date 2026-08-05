from __future__ import annotations

import httpx

from gzhreader_core.ai import RETRIES, TEMPERATURE, TIMEOUT_SECONDS, Summarizer
from gzhreader_core.credentials import CredentialVault


class FakeClient:
    response = None
    def __init__(self, **kwargs): self.kwargs = kwargs
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def post(self, *args, **kwargs): return self.response


def test_fixed_parameters_and_structured_summary(tmp_path):
    assert (TIMEOUT_SECONDS, RETRIES, TEMPERATURE) == (90, 2, 0.2)
    vault = CredentialVault(tmp_path)
    vault.save("ai", {"base_url": "https://example.test/v1", "api_key": "key", "model": "model", "enabled": True})
    FakeClient.response = httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"summary":"摘要","key_points":["一","二","三"],"tags":["主题"],"takeaway":"结论"}\n```'}}]}, request=httpx.Request("POST", "https://example.test"))
    result = Summarizer(vault, client_factory=FakeClient).summarize("标题", "正文", "公众号")
    assert result["status"] == "done"
    assert result["summary"] == "摘要"
    assert result["prompt_version"]


def test_missing_config_uses_fallback(tmp_path):
    result = Summarizer(CredentialVault(tmp_path)).summarize("标题", "这是一段正文", "公众号")
    assert result["status"] == "fallback"
    assert "正文" in result["summary"]
