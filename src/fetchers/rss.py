from __future__ import annotations

import logging
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import NewsItem

NAME = "rss"
log = logging.getLogger(NAME)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=1, max=5))
async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=10.0, follow_redirects=True)
    r.raise_for_status()
    return r.text


async def fetch(config: dict[str, Any]) -> list[NewsItem]:
    cfg = config.get("sources", {}).get(NAME, {})
    if not cfg.get("enabled", True):
        return []

    feeds = cfg.get("feeds", [])
    out: list[NewsItem] = []

    async with httpx.AsyncClient(headers={"User-Agent": "ai-news-digest/0.1"}) as client:
        for feed_cfg in feeds:
            url = feed_cfg.get("url")
            name = feed_cfg.get("name", "unknown")
            if not url:
                continue
            try:
                xml = await _get_text(client, url)
            except Exception as e:
                log.warning("rss fetch failed (%s %s): %s", name, url, e)
                continue

            parsed = feedparser.parse(xml)
            for entry in parsed.entries[:50]:
                try:
                    link = entry.get("link") or ""
                    title = (entry.get("title") or "").strip()
                    if not link or not title:
                        continue
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    if pub:
                        published = datetime(*pub[:6], tzinfo=timezone.utc)
                    else:
                        published = datetime.now(timezone.utc)
                    out.append(
                        NewsItem(
                            id=f"rss-{name}-{sha1(link.encode()).hexdigest()[:12]}",
                            title=title,
                            url=link,
                            source=f"{NAME}:{name}",
                            published_at=published,
                            score=0,
                            comments=0,
                            raw={"feed": name, "author": entry.get("author")},
                        )
                    )
                except Exception as e:
                    log.warning("rss entry skipped (%s): %s", name, e)
                    continue

    log.info("rss fetched %d items across %d feeds", len(out), len(feeds))
    return out
