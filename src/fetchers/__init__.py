from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.models import NewsItem

from . import github_trending, hackernews, huggingface, rss, twitter

Fetcher = Callable[[dict[str, Any]], Awaitable[list[NewsItem]]]

REGISTRY: dict[str, Fetcher] = {
    hackernews.NAME: hackernews.fetch,
    rss.NAME: rss.fetch,
    github_trending.NAME: github_trending.fetch,
    huggingface.NAME: huggingface.fetch,
    twitter.NAME: twitter.fetch,
}


def get(name: str) -> Fetcher:
    if name not in REGISTRY:
        raise KeyError(f"unknown source: {name}. available={list(REGISTRY)}")
    return REGISTRY[name]


def all_names() -> list[str]:
    return list(REGISTRY.keys())
