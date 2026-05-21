"""Per-source engagement labels for digest + LLM (avoid misleading score/comments)."""

from __future__ import annotations

from src.models import NewsItem


def _fmt(n: int) -> str:
    return f"{n:,}"


def format_engagement(item: NewsItem) -> str:
    """Human-readable metrics line for templates and LLM context."""
    src = item.source
    raw = item.raw or {}

    if src == "github_trending":
        stars = int(raw.get("stars") or item.score or 0)
        forks = raw.get("forks")
        issues = raw.get("open_issues")
        parts = [f"stars={_fmt(stars)}"]
        if forks is not None:
            parts.append(f"forks={_fmt(int(forks))}")
        if issues is not None:
            # GitHub REST API open_issues_count = open issues + open PRs
            parts.append(f"open_items={_fmt(int(issues))}")
        return " · ".join(parts)

    if src == "hackernews":
        return f"points={_fmt(item.score)} · comments={_fmt(item.comments)}"

    if src.startswith("huggingface:papers"):
        return f"upvotes={_fmt(item.score)} · hf_comments={_fmt(item.comments)}"

    if src.startswith("huggingface:models"):
        return f"likes={_fmt(item.score)} · downloads={_fmt(item.comments)}"

    if src.startswith("rss:") or src == "rss":
        return "RSS"

    if src.startswith("twitter:"):
        return "X / Twitter"

    if item.score or item.comments:
        return f"score={_fmt(item.score)} · comments={_fmt(item.comments)}"
    return "—"


SOURCE_METRICS_GUIDE = """
各 source 的 score/comments 含义（禁止混用、禁止对 github 写「评论数为 0」）：
- github_trending：score=stars；comments=open_items（GitHub API = open issues + open PRs；非 HN 评论数）。看 engagement 行的 stars/forks/open_items。
- hackernews：score=points，comments=HN 讨论条数。
- huggingface:papers：score=upvotes，comments=HF 评论数。
- huggingface:models：score=likes，comments=downloads（下载量，不是评论）。
- rss:*：通常 score/comments 为 0，勿据此推断热度。
""".strip()
