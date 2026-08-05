from __future__ import annotations

from datetime import datetime, timezone

from gzhreader_core.models import SourceProfile
from gzhreader_core.providers.resolver import ArticleLinkResolver
from gzhreader_core.providers.weread import build_mp_url, extract_mp_content, parse_mp_articles


def test_biz_decode_and_metadata_extract():
    resolver = ArticleLinkResolver()
    assert resolver.decode_biz("Mzg5Mjc3MjIyMA==") == "3892772220"
    html = """
    <html><head><meta property="og:image" content="https://img/cover.jpg"></head>
    <body><h1 id="activity-name">文章标题</h1><strong id="js_name">测试公众号</strong>
    <script>var biz = 'Mzg5Mjc3MjIyMA=='; var ct = '1760000000'; var ori_head_img_url = 'https://img/avatar.jpg';</script></body></html>
    """
    value = resolver._extract(html, "https://mp.weixin.qq.com/s?mid=1&idx=2&sn=3")
    assert value["name"] == "测试公众号"
    assert value["title"] == "文章标题"
    assert value["article_id"] == "1-2-3"


def test_parse_weread_articles_and_content():
    source = SourceProfile("MP_WXS_1", "测试公众号")
    payload = {"reviews": [{"createTime": 1770000000, "subReviews": [{"review": {"reviewId": "r1", "createTime": 1770000001, "mpInfo": {"title": "标题", "originalId": "abc~def", "pic_url": "cover", "content": "导语", "time": 1770000002}}}]}]}
    articles, groups = parse_mp_articles(payload, source)
    assert groups == 1
    assert articles[0].origin_id == "r1"
    assert articles[0].url == build_mp_url("abc~def")
    assert articles[0].digest == "导语"
    assert extract_mp_content('<div id="js_content"><p>第一段</p><script>bad()</script><p>第二段</p></div>') == "第一段\n第二段"
