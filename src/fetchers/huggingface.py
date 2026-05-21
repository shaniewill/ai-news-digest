from __future__ import annotations

import logging
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import NewsItem

NAME = "huggingface"
log = logging.getLogger(NAME)

PAPERS_URL = "https://huggingface.co/api/daily_papers"
MODELS_URL = "https://huggingface.co/api/models"


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=1, max=5))
async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> Any:
    r = await client.get(url, params=params or {}, timeout=15.0, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def _ts(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


async def _fetch_papers(client: httpx.AsyncClient, max_items: int) -> list[NewsItem]:
    try:
        data = await _get_json(client, PAPERS_URL)
    except Exception as e:
        log.warning("hf daily_papers failed: %s", e)
        return []
    items: list[NewsItem] = []
    for entry in data[:max_items]:
        paper = entry.get("paper") or {}
        pid = paper.get("id") or entry.get("id")
        if not pid:
            continue
        title = paper.get("title") or entry.get("title") or ""
        upvotes = int(paper.get("upvotes") or entry.get("numUpvotes") or 0)
        published = _ts(entry.get("publishedAt") or paper.get("publishedAt"))
        url = f"https://huggingface.co/papers/{pid}"
        items.append(
            NewsItem(
                id=f"hf-paper-{pid}",
                title=title.strip(),
                url=url,
                source="huggingface:papers",
                published_at=published,
                score=upvotes,
                comments=int(entry.get("numComments") or 0),
                raw={"hf_paper_id": pid, "abstract": paper.get("summary")},
            )
        )
    log.info("hf papers fetched %d", len(items))
    return items


async def _fetch_models(client: httpx.AsyncClient, max_items: int) -> list[NewsItem]:
    params = {"sort": "trendingScore", "direction": "-1", "limit": max_items, "full": "true"}
    try:
        data = await _get_json(client, MODELS_URL, params)
    except Exception as e:
        log.warning("hf trending models failed: %s", e)
        return []
    items: list[NewsItem] = []
    for m in data[:max_items]:
        mid = m.get("modelId") or m.get("id")
        if not mid:
            continue
        likes = int(m.get("likes") or 0)
        downloads = int(m.get("downloads") or 0)
        modified = _ts(m.get("lastModified") or m.get("createdAt"))
        title_desc = (m.get("description") or "").strip().splitlines()[0] if m.get("description") else ""
        title = f"{mid}" + (f" — {title_desc[:120]}" if title_desc else "")
        items.append(
            NewsItem(
                id=f"hf-model-{sha1(mid.encode()).hexdigest()[:12]}",
                title=title,
                url=f"https://huggingface.co/{mid}",
                source="huggingface:models",
                published_at=modified,
                score=likes,
                comments=downloads,  # 复用 comments 字段记下载数
                raw={"model_id": mid, "likes": likes, "downloads": downloads},
            )
        )
    log.info("hf trending models fetched %d", len(items))
    return items


async def fetch(config: dict[str, Any]) -> list[NewsItem]:
    cfg = config.get("sources", {}).get(NAME, {})
    if not cfg.get("enabled", True):
        return []

    fetch_papers = bool(cfg.get("papers", True))
    fetch_models = bool(cfg.get("models", True))
    max_papers = int(cfg.get("max_papers", 15))
    max_models = int(cfg.get("max_models", 10))

    out: list[NewsItem] = []
    async with httpx.AsyncClient(headers={"User-Agent": "ai-news-digest/0.1"}) as client:
        if fetch_papers:
            out.extend(await _fetch_papers(client, max_papers))
        if fetch_models:
            out.extend(await _fetch_models(client, max_models))
    return out
