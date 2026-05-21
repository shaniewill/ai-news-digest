from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import NewsItem

NAME = "hackernews"
log = logging.getLogger(NAME)

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=1, max=5))
async def _get(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    r = await client.get(ALGOLIA_URL, params=params, timeout=10.0)
    r.raise_for_status()
    return r.json()


async def fetch(config: dict[str, Any]) -> list[NewsItem]:
    cfg = config.get("sources", {}).get(NAME, {})
    if not cfg.get("enabled", True):
        return []

    query = cfg.get("query", "ai OR llm")
    min_score = int(cfg.get("min_score", 100))
    max_items = int(cfg.get("max_items", 60))
    lookback_h = int(cfg.get("lookback_hours", 48))
    cutoff = int(datetime.now(tz=timezone.utc).timestamp()) - lookback_h * 3600

    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"points>={min_score},created_at_i>{cutoff}",
        "hitsPerPage": max_items,
    }

    items: list[NewsItem] = []
    async with httpx.AsyncClient() as client:
        try:
            data = await _get(client, params)
        except Exception as e:
            log.warning("hackernews fetch failed: %s", e)
            return []

    for hit in data.get("hits", []):
        try:
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
            ts = hit.get("created_at_i")
            published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
            items.append(
                NewsItem(
                    id=f"hn-{hit['objectID']}",
                    title=hit.get("title") or "(no title)",
                    url=url,
                    source=NAME,
                    published_at=published,
                    score=int(hit.get("points") or 0),
                    comments=int(hit.get("num_comments") or 0),
                    raw={"hn_id": hit["objectID"], "author": hit.get("author")},
                )
            )
        except Exception as e:
            log.warning("hn item skipped: %s", e)
            continue

    log.info("hackernews fetched %d items", len(items))
    return items
