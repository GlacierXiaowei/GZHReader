from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .credentials import CredentialVault

TIMEOUT_SECONDS = 90
RETRIES = 2
TEMPERATURE = 0.2
PROMPT_VERSION = "article-summary-v1"


class Summarizer:
    def __init__(self, vault: CredentialVault, client_factory=httpx.Client):
        self.vault = vault
        self.client_factory = client_factory

    def config(self) -> dict[str, Any]:
        return self.vault.load("ai")

    def save(self, payload: dict[str, Any]) -> None:
        current = self.config()
        api_key = payload.get("api_key")
        if api_key is None:
            api_key = current.get("api_key", "")
        self.vault.save(
            "ai",
            {
                "base_url": str(payload.get("base_url") or "").strip(),
                "model": str(payload.get("model") or "").strip(),
                "api_key": str(api_key or "").strip(),
                "enabled": bool(payload.get("enabled", True)),
            },
        )

    def public_config(self) -> dict[str, Any]:
        config = self.config()
        return {
            "base_url": config.get("base_url", ""),
            "model": config.get("model", ""),
            "has_api_key": bool(config.get("api_key")),
            "enabled": bool(config.get("enabled", True)),
        }

    @staticmethod
    def _endpoint(base_url: str) -> str:
        return base_url.rstrip("/") + "/chat/completions"

    def test(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = {**self.config(), **payload}
        if not config.get("base_url") or not config.get("api_key") or not config.get("model"):
            return {"ok": False, "message": "请完整填写服务地址、密钥和模型名称"}
        body = {
            "model": config["model"],
            "temperature": TEMPERATURE,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "只回复：连接成功"}],
        }
        try:
            with self.client_factory(timeout=20) as client:
                response = client.post(
                    self._endpoint(str(config["base_url"])),
                    headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
                    json=body,
                )
            if response.status_code in {401, 403}:
                return {"ok": False, "message": "密钥无效"}
            if response.status_code in {400, 404, 422}:
                text = response.text.lower()
                if "model" in text:
                    return {"ok": False, "message": "模型不可用"}
                return {"ok": False, "message": "服务地址无法访问"}
            if response.status_code >= 400:
                return {"ok": False, "message": "服务地址无法访问"}
            return {"ok": True, "message": "连接成功"}
        except httpx.TimeoutException:
            return {"ok": False, "message": "连接超时"}
        except Exception:
            return {"ok": False, "message": "服务地址无法访问"}

    @staticmethod
    def fallback(text: str) -> dict[str, Any]:
        summary = " ".join((text or "").split())[:180]
        return {
            "summary": summary,
            "key_points": [],
            "tags": [],
            "takeaway": summary[:60],
            "raw_text": "",
            "prompt_version": PROMPT_VERSION,
            "status": "fallback",
        }

    def summarize(self, title: str, content: str, source: str) -> dict[str, Any]:
        config = self.config()
        text = (content or title).strip()
        if not config.get("enabled", True) or not all(config.get(key) for key in ("api_key", "base_url", "model")):
            return self.fallback(text)
        prompt = (
            "请整理下面的微信公众号文章，只返回 JSON，不要 Markdown。"
            "字段必须为 summary（120到250个中文字符）、key_points（3到5条）、"
            "tags（1到3个）、takeaway（一句话结论）。\n"
            f"公众号：{source}\n标题：{title}\n正文：{text[:12000]}"
        )
        body = {
            "model": config["model"],
            "temperature": TEMPERATURE,
            "messages": [
                {"role": "system", "content": "你是克制、准确的中文内容编辑。不要补充文章没有的信息。"},
                {"role": "user", "content": prompt},
            ],
        }
        last_raw = ""
        for _attempt in range(RETRIES + 1):
            try:
                with self.client_factory(timeout=TIMEOUT_SECONDS) as client:
                    response = client.post(
                        self._endpoint(str(config["base_url"])),
                        headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
                        json=body,
                    )
                response.raise_for_status()
                last_raw = str(response.json().get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
                data = self._parse(last_raw)
                return {
                    "summary": str(data.get("summary") or last_raw).strip(),
                    "key_points": [str(item).strip() for item in list(data.get("key_points") or [])[:5] if str(item).strip()],
                    "tags": [str(item).strip() for item in list(data.get("tags") or [])[:3] if str(item).strip()],
                    "takeaway": str(data.get("takeaway") or "").strip(),
                    "raw_text": last_raw,
                    "prompt_version": PROMPT_VERSION,
                    "status": "done",
                }
            except Exception:
                continue
        result = self.fallback(text)
        result["raw_text"] = last_raw
        return result

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I | re.S)
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        value = json.loads(match.group(0) if match else cleaned)
        if not isinstance(value, dict):
            raise ValueError("摘要格式无效")
        return value
