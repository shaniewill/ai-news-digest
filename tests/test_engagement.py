from __future__ import annotations

from datetime import datetime, timezone

from src.engagement import format_engagement
from src.models import NewsItem


def test_github_engagement_shows_stars_forks_issues():
    it = NewsItem(
        id="gh-1",
        title="NousResearch/hermes-agent",
        url="https://github.com/NousResearch/hermes-agent",
        source="github_trending",
        published_at=datetime.now(timezone.utc),
        score=161_000,
        comments=4_400,
        raw={"stars": 161_000, "forks": 26_100, "open_issues": 4_400},
    )
    line = format_engagement(it)
    assert "stars=161,000" in line
    assert "forks=26,100" in line
    assert "open_items=4,400" in line
    assert "comments=" not in line


def test_github_engagement_omits_unfetched_fields():
    """When GitHub API enrich failed (no token / rate limit), forks/open_items
    must be omitted from the engagement line, never shown as '0' — otherwise
    LLM may write "this repo has 0 forks" into the digest as a fake fact."""
    it = NewsItem(
        id="gh-2",
        title="some/repo",
        url="https://github.com/some/repo",
        source="github_trending",
        published_at=datetime.now(timezone.utc),
        score=12_345,
        comments=0,
        raw={"stars": 12_345},  # no forks, no open_issues — API enrich failed
    )
    line = format_engagement(it)
    assert line == "stars=12,345"
    assert "forks" not in line
    assert "open_items" not in line


def test_hackernews_engagement_unchanged():
    it = NewsItem(
        id="hn-1",
        title="Test",
        url="https://news.ycombinator.com/item?id=1",
        source="hackernews",
        published_at=datetime.now(timezone.utc),
        score=457,
        comments=119,
    )
    assert format_engagement(it) == "points=457 · comments=119"
