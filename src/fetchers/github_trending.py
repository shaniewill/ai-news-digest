from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import NewsItem

NAME = "github_trending"
log = logging.getLogger(NAME)

_GH_HEADERS = {
    "User-Agent": "ai-news-digest/0.1",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=1, max=5))
async def _get(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=10.0, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _parse(html: str, lang: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows = re.findall(r'<article class="Box-row">(.*?)</article>', html, re.DOTALL)
    for row in rows:
        m_repo = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', row)
        m_desc = re.search(r'<p[^>]*class="col-9[^"]*"[^>]*>(.*?)</p>', row, re.DOTALL)
        m_stars_block = re.search(r'/stargazers"[^>]*>(.*?)</a>', row, re.DOTALL)
        if not m_repo:
            continue
        repo = m_repo.group(1).strip()
        desc = re.sub(r"<[^>]+>", "", (m_desc.group(1) if m_desc else "")).strip()
        stars = 0
        if m_stars_block:
            digit_groups = re.findall(r"([\d,]+)", m_stars_block.group(1))
            if digit_groups:
                cleaned = digit_groups[-1].replace(",", "")
                if cleaned.isdigit():
                    stars = int(cleaned)
        out.append({"repo": repo, "desc": desc, "stars": stars, "lang": lang})
    return out


async def _repo_stats(
    client: httpx.AsyncClient, repo: str, token: str | None
) -> dict[str, int] | None:
    """Return stars/forks/open_issues from GitHub REST API, or None if unavailable.

    Returning None (not {}) lets callers distinguish "unknown" from "zero" — important
    because the digest must not claim "forks=0" when we simply failed to fetch it.
    """
    headers = dict(_GH_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = await client.get(
            f"https://api.github.com/repos/{repo}",
            headers=headers,
            timeout=15.0,
        )
        if r.status_code == 404:
            return None
        if r.status_code in (401, 403):
            log.warning("github api auth/rate-limit (%d) for %s", r.status_code, repo)
            return None
        r.raise_for_status()
        d = r.json()
        return {
            "stars": int(d.get("stargazers_count") or 0),
            "forks": int(d.get("forks_count") or 0),
            "open_issues": int(d.get("open_issues_count") or 0),
        }
    except Exception as e:
        log.warning("github repo api %s: %s", repo, e)
        return None


async def _enrich_repos(
    client: httpx.AsyncClient,
    rows: list[dict[str, Any]],
    token: str | None,
    concurrency: int = 8,
) -> tuple[int, int]:
    """Enrich rows with API stats. Returns (ok_count, fail_count)."""
    sem = asyncio.Semaphore(concurrency)
    ok = 0
    fail = 0

    async def one(row: dict[str, Any]) -> None:
        nonlocal ok, fail
        async with sem:
            stats = await _repo_stats(client, row["repo"], token)
        if stats is None:
            fail += 1
            return
        ok += 1
        # Prefer API numbers (more accurate than HTML parse).
        row["stars"] = max(row.get("stars", 0), stats["stars"])
        row["forks"] = stats["forks"]
        row["open_issues"] = stats["open_issues"]

    await asyncio.gather(*(one(r) for r in rows))
    return ok, fail


async def fetch(config: dict[str, Any]) -> list[NewsItem]:
    cfg = config.get("sources", {}).get(NAME, {})
    if not cfg.get("enabled", True):
        return []

    since = cfg.get("since", "daily")
    langs = cfg.get("languages", [None])
    max_items = int(cfg.get("max_items", 20))
    token = (
        cfg.get("token")
        or config.get("_env", {}).get("GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or None
    )

    log.info(
        "github_trending starting (token=%s) — unauthenticated API is capped at 60 req/h",
        "set" if token else "MISSING",
    )

    parsed_rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(headers=_GH_HEADERS) as client:
        for lang in langs:
            url = "https://github.com/trending"
            if lang:
                url += f"/{lang}"
            url += f"?since={since}"
            try:
                html = await _get(client, url)
            except Exception as e:
                log.warning("github trending fetch failed (%s): %s", lang, e)
                continue
            parsed_rows.extend(_parse(html, lang))

        if parsed_rows:
            ok, fail = await _enrich_repos(client, parsed_rows, token)
            log.info("github_trending api enrich: ok=%d fail=%d", ok, fail)
            if fail and not token:
                log.warning(
                    "github_trending: %d/%d repos failed to enrich. "
                    "Set GITHUB_TOKEN in .env to lift the 60 req/h limit (5000 req/h with token).",
                    fail, ok + fail,
                )

    items: list[NewsItem] = []
    seen: set[str] = set()
    for r in parsed_rows:
        if r["repo"] in seen:
            continue
        seen.add(r["repo"])
        stars = int(r.get("stars") or 0)
        # forks / open_issues remain absent (not 0) if the API call didn't enrich them.
        forks = r.get("forks")
        open_issues = r.get("open_issues")
        full_url = f"https://github.com/{r['repo']}"
        raw: dict[str, Any] = {
            "repo": r["repo"],
            "lang": r["lang"],
            "stars": stars,
        }
        if forks is not None:
            raw["forks"] = int(forks)
        if open_issues is not None:
            raw["open_issues"] = int(open_issues)
        items.append(
            NewsItem(
                id=f"gh-{sha1(r['repo'].encode()).hexdigest()[:12]}",
                title=f"{r['repo']} — {r['desc']}" if r["desc"] else r["repo"],
                url=full_url,
                source=NAME,
                published_at=datetime.now(timezone.utc),
                score=stars,
                # comments stays 0 — GitHub has no HN-style comments. Engagement
                # line shows open_items only when the API call actually succeeded.
                comments=0,
                raw=raw,
            )
        )

    items.sort(key=lambda x: x.score, reverse=True)
    items = items[:max_items]
    log.info("github_trending fetched %d items", len(items))
    return items
