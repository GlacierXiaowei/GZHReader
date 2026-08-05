from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path


class BriefingService:
    def __init__(self, storage, briefing_dir: Path, summarizer):
        self.storage = storage
        self.dir = briefing_dir
        self.summarizer = summarizer

    def generate(self, day: date) -> dict:
        articles = self.storage.day_articles(day)
        grouped: dict[str, list[dict]] = defaultdict(list)
        for article in articles:
            grouped[article["source_name"]].append(article)
        digest_lines = [
            f"- {article['source_name']}《{article['title']}》：{article['summary'] or article['digest']}"
            for article in articles
        ]
        overview = "今天没有新增文章。"
        if articles:
            if len(articles) > 50:
                chunk_summaries = []
                for index in range(0, len(digest_lines), 25):
                    chunk = "\n".join(digest_lines[index:index + 25])
                    chunk_summaries.append(
                        self.summarizer.summarize(f"第 {index // 25 + 1} 组文章小结", chunk, "GZHReader")["summary"]
                    )
                digest = "\n".join(f"- {item}" for item in chunk_summaries)
            else:
                digest = "\n".join(digest_lines)
            overview = self.summarizer.summarize(f"{day.isoformat()} 每日简报", digest, "GZHReader")["summary"]
        tag_counts = Counter(tag for article in articles for tag in article.get("tags", []))
        themes = [name for name, _count in tag_counts.most_common(5)]
        lines = [
            f"# 公众号每日简报 · {day.isoformat()}",
            "",
            "## 今日概览",
            "",
            overview,
            "",
            f"共收录 {len(articles)} 篇文章。",
            "",
            "## 主要主题",
            "",
            "、".join(themes) if themes else "暂无明确主题",
            "",
            "## 今日必读 Top 3",
            "",
        ]
        for article in articles[:3]:
            lines += [
                f"### [{article['title']}]({article['url']})",
                article["takeaway"] or article["summary"] or article["digest"] or "等待整理",
                "",
            ]
        for source, items in grouped.items():
            lines += [f"## {source}", ""]
            for article in items:
                lines += [
                    f"### [{article['title']}]({article['url']})",
                    article["summary"] or article["digest"] or "等待整理",
                    "",
                ]
        lines += ["---", f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
        markdown = "\n".join(lines)
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{day.isoformat()}.md"
        path.write_text(markdown, encoding="utf-8")
        self.storage.save_briefing(day, overview, markdown, str(path), len(articles))
        return {
            "day": day.isoformat(),
            "overview": overview,
            "markdown": markdown,
            "file_path": str(path),
            "article_count": len(articles),
            "themes": themes,
        }
