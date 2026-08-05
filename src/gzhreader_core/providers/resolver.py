from __future__ import annotations

import base64
import hashlib
import html as html_module
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from ..models import SourceProfile

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)


class ArticleLinkResolver:
    def resolve_source(self, url: str) -> dict:
        clean_url = url.strip()
        parsed = urlparse(clean_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"mp.weixin.qq.com", "weixin.qq.com"}:
            raise ValueError("请粘贴微信公众号文章链接")
        html = ""
        final_url = clean_url
        try:
            with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": DESKTOP_UA}) as client:
                response = client.get(clean_url)
                response.raise_for_status()
                html = response.text
                final_url = str(response.url)
        except Exception:
            html, final_url = self._browser_fetch(clean_url)
        value = self._extract(html, final_url)
        if not value["biz"] or not value["name"]:
            if not html:
                raise ValueError("内容暂时无法读取，请检查网络后再试")
            raise ValueError("暂时无法识别这个公众号，请换一篇文章再试")
        source_id = f"MP_WXS_{self.decode_biz(value['biz'])}"
        source = SourceProfile(
            id=source_id,
            name=value["name"],
            avatar=value["avatar"],
            intro=value["intro"],
            sample_url=final_url,
        ).to_dict()
        source["sample_article"] = {
            "origin_id": value["article_id"],
            "title": value["title"] or "已添加的公众号文章",
            "url": final_url,
            "published_at": value["published_at"],
            "author": value["name"],
            "cover": value["cover"],
        }
        return source

    def _browser_fetch(self, url: str) -> tuple[str, str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise ValueError("内容暂时无法读取，请检查网络后再试") from exc
        with sync_playwright() as playwright:
            errors: list[str] = []
            for launch in ({"channel": "msedge"}, {"channel": "chrome"}):
                try:
                    browser = playwright.chromium.launch(headless=True, **launch)
                    break
                except Exception as exc:
                    errors.append(str(exc))
            else:
                raise ValueError("未找到可用的 Edge 或 Chrome 浏览器")
            try:
                page = browser.new_page(user_agent=DESKTOP_UA)
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                return page.content(), page.url
            finally:
                browser.close()

    def _extract(self, html: str, final_url: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")

        def js(*names: str) -> str:
            for name in names:
                escaped = re.escape(name)
                patterns = (
                    rf"(?:var\s+)?{escaped}\s*=\s*['\"](.*?)['\"]\s*[;,]",
                    rf"['\"]?{escaped}['\"]?\s*:\s*['\"](.*?)['\"]\s*[,}}]",
                )
                for pattern in patterns:
                    match = re.search(pattern, html, flags=re.S)
                    if match:
                        return self._clean_js_string(match.group(1))
            return ""

        query = parse_qs(urlparse(final_url).query)
        name_node = soup.select_one("#js_name") or soup.select_one(".profile_nickname")
        title_node = soup.select_one("#activity-name") or soup.select_one("h1.rich_media_title")
        cover_meta = soup.find("meta", attrs={"property": "og:image"})
        description_meta = soup.find("meta", attrs={"name": "description"})
        timestamp = js("ct", "publish_time", "create_time")
        try:
            published_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            published_at = datetime.now(timezone.utc).isoformat()
        article_seed = "-".join(
            [
                (query.get("mid") or [""])[0],
                (query.get("idx") or [""])[0],
                (query.get("sn") or [""])[0],
            ]
        ).strip("-")
        if not article_seed:
            article_seed = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:24]
        cover = str(cover_meta.get("content") or "") if cover_meta else ""
        return {
            "biz": js("biz", "__biz") or (query.get("__biz") or [""])[0],
            "name": js("nickname") or (name_node.get_text(strip=True) if name_node else ""),
            "intro": js("profile_signature", "profile_signature_new") or (str(description_meta.get("content") or "") if description_meta else ""),
            "avatar": js("ori_head_img_url", "head_img") or cover,
            "title": js("msg_title") or (title_node.get_text(" ", strip=True) if title_node else ""),
            "cover": cover,
            "article_id": article_seed,
            "published_at": published_at,
        }

    @staticmethod
    def _clean_js_string(value: str) -> str:
        value = value.replace(r"\/", "/").replace(r"\x26", "&")
        if "\\u" in value or "\\x" in value:
            try:
                value = bytes(value, "utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                pass
        return html_module.unescape(value).strip()

    @staticmethod
    def decode_biz(biz: str) -> str:
        candidate = biz.strip()
        try:
            padding = "=" * (-len(candidate) % 4)
            decoded = base64.b64decode(candidate + padding).decode("utf-8", errors="ignore").strip()
        except Exception:
            decoded = ""
        cleaned = "".join(ch for ch in (decoded or candidate) if ch.isalnum() or ch in {"_", "-"})
        if not cleaned:
            raise ValueError("公众号标识无效")
        return cleaned
