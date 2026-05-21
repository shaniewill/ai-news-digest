from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from src.models import NewsItem


def rank(items: list[NewsItem], cfg: dict[str, Any]) -> list[NewsItem]:
    weights = cfg.get("weights", {"score": 0.4, "comments": 0.3, "recency_hours": 0.3})
    decay_h = float(cfg.get("recency_decay_hours", 48))
    now = datetime.now(timezone.utc)

    max_score = max((it.score for it in items), default=1) or 1
    max_comm = max((it.comments for it in items), default=1) or 1

    def key(it: NewsItem) -> float:
        s = it.score / max_score
        c = it.comments / max_comm
        age_h = max((now - it.published_at).total_seconds() / 3600.0, 0.0)
        r = math.exp(-age_h / decay_h)
        return (
            float(weights.get("score", 0.4)) * s
            + float(weights.get("comments", 0.3)) * c
            + float(weights.get("recency_hours", 0.3)) * r
        )

    scored = sorted(items, key=key, reverse=True)
    return scored
