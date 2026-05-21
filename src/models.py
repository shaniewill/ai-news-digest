from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class NewsItem:
    id: str
    title: str
    url: str
    source: str
    published_at: datetime
    score: int = 0
    comments: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from src.engagement import format_engagement

        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
            "score": self.score,
            "comments": self.comments,
            "engagement": format_engagement(self),
        }


@dataclass(slots=True)
class DeepAnalysis:
    item: NewsItem
    fact: str
    context: str
    stakeholders: str
    implications: str
    uncertainty: str
    confidence: str
    source_excerpt: str | None = None


@dataclass(slots=True)
class Prediction:
    statement: str
    rationale: str
    verify_by: str
    falsifiable_when: str
    related_item_url: str | None = None


@dataclass(slots=True)
class BriefCluster:
    theme: str
    items: list[tuple[NewsItem, str]] = field(default_factory=list)


@dataclass(slots=True)
class DigestPayload:
    date: str
    one_liner: str
    deep: list[DeepAnalysis]
    brief_overview: str
    brief_clusters: list[BriefCluster]
    weak_signals: list[tuple[NewsItem, str]]
    trend_links: list[str]
    predictions: list[Prediction]
    sources_count: int
    run_id: str
