from __future__ import annotations

import logging
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import NewsItem

NAME = "twitter"
log = logging.getLogger(NAME)

DEFAULT_INSTANCE = "https://rsshub.app"


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=1, max=4))
async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=15.0, follow_redirects=True)
    r.raise_for_status()
    return r.text


async def fetch(config: dict[str, Any]) -> list[NewsItem]:
    cfg = config.get("sources", {}).get(NAME, {})
    if not cfg.get("enabled", False):
        return []

    instance = (cfg.get("instance_url") or DEFAULT_INSTANCE).rstrip("/")
    accounts: list[str] = cfg.get("accounts", []) or []
    max_per_account = int(cfg.get("max_per_account", 8))
    min_age_days = int(cfg.get("max_age_days", 3))

    if not accounts:
        log.info("twitter: no accounts configured, skipping")
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - min_age_days * 86400
    out: list[NewsItem] = []

    async with httpx.AsyncClient(headers={"User-Agent": "ai-news-digest/0.1"}) as client:
        for handle in accounts:
            handle = handle.lstrip("@")
            url = f"{instance}/twitter/user/{handle}"
            try:
                xml = await _get_text(client, url)
            except Exception as e:
                log.warning("twitter @%s failed via %s: %s", handle, instance, e)
                continue

            parsed = feedparser.parse(xml)
            kept = 0
            for entry in parsed.entries[: max_per_account * 2]:
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
                    if published.timestamp() < cutoff:
                        continue
                    out.append(
                        NewsItem(
                            id=f"x-{handle}-{sha1(link.encode()).hexdigest()[:12]}",
                            title=f"@{handle}: {title[:200]}",
                            url=link,
                            source=f"twitter:{handle}",
                            published_at=published,
                            score=0,
                            comments=0,
                            raw={"handle": handle, "instance": instance},
                        )
                    )
                    kept += 1
                    if kept >= max_per_account:
                        break
                except Exception as e:
                    log.warning("twitter entry @%s skipped: %s", handle, e)

    log.info("twitter fetched %d items across %d accounts via %s", len(out), len(accounts), instance)
    return out
