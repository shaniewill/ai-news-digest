from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from src.models import NewsItem

log = logging.getLogger("dedup")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    daily_run_id TEXT,
    seen_count INTEGER DEFAULT 1,
    deep_analyzed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_canonical ON items(canonical_url);
CREATE INDEX IF NOT EXISTS idx_first_seen ON items(first_seen_at);
-- idx_deep_analyzed is created in _migrate(), after the column is added on legacy DBs.

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    digest_path TEXT,
    items_fetched INTEGER,
    items_deep INTEGER,
    items_brief INTEGER,
    notes TEXT
);
"""

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}


def normalize_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        scheme = p.scheme.lower() or "https"
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path.rstrip("/")
        query_parts = []
        if p.query:
            for kv in p.query.split("&"):
                if "=" in kv:
                    k, _ = kv.split("=", 1)
                    if k.lower() in TRACKING_PARAMS:
                        continue
                query_parts.append(kv)
        query = "&".join(query_parts)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url


def _migrate(conn: sqlite3.Connection) -> None:
    # Add columns added after v1 schema. Idempotent: PRAGMA table_info tells us
    # which already exist. SQLite ALTER TABLE ADD COLUMN doesn't support IF NOT EXISTS.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
    if "seen_count" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN seen_count INTEGER DEFAULT 1")
    if "deep_analyzed_at" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN deep_analyzed_at TEXT")
    # Safe to create now that the column exists on both fresh and legacy DBs.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deep_analyzed ON items(deep_analyzed_at)")


@contextmanager
def open_db(path: str | Path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_candidates(conn: sqlite3.Connection, items: list[NewsItem]) -> list[NewsItem]:
    """Record every candidate in DB and return them all.

    Key behavior change from the old filter_new: this does NOT drop items that
    were seen before. It only deduplicates within the current batch (same URL
    coming from two sources) and bumps seen_count for items already in DB.

    Dedup that prevents the LLM from re-analyzing the same article is enforced
    later, at the curator layer, using `get_recently_deep_analyzed_urls`.
    """
    now = datetime.now(timezone.utc).isoformat()
    seen_canonical: set[str] = set()
    out: list[NewsItem] = []
    new_count = 0

    for it in items:
        canonical = normalize_url(it.url)
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)

        row = conn.execute(
            "SELECT id, score, comments FROM items WHERE canonical_url = ?",
            (canonical,),
        ).fetchone()
        if row is None:
            conn.execute(
                """INSERT INTO items
                (id, title, url, canonical_url, source, published_at, score, comments,
                 first_seen_at, last_seen_at, seen_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    it.id,
                    it.title,
                    it.url,
                    canonical,
                    it.source,
                    it.published_at.isoformat(),
                    it.score,
                    it.comments,
                    now,
                    now,
                ),
            )
            new_count += 1
        else:
            conn.execute(
                """UPDATE items SET last_seen_at = ?, score = ?, comments = ?,
                   seen_count = seen_count + 1 WHERE id = ?""",
                (now, max(it.score, row["score"]), max(it.comments, row["comments"]), row["id"]),
            )
        out.append(it)

    intra_batch_dups = len(items) - len(out)
    log.info(
        "dedup: %d candidates (new=%d, seen-before=%d, intra-batch-dups=%d)",
        len(out), new_count, len(out) - new_count, intra_batch_dups,
    )
    return out


def get_recently_deep_analyzed_urls(conn: sqlite3.Connection, days: int = 14) -> set[str]:
    """Canonical URLs that were deep-analyzed in the past `days` days.

    Curator must NOT pick these into deep_ids again — but they can still appear
    in brief_ids if today brings a new development on that story.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT canonical_url FROM items WHERE deep_analyzed_at IS NOT NULL AND deep_analyzed_at >= ?",
        (cutoff,),
    ).fetchall()
    return {r["canonical_url"] for r in rows}


def mark_deep_analyzed(conn: sqlite3.Connection, urls: list[str]) -> int:
    """Mark canonical URLs as deep-analyzed at `now`. Returns rows updated."""
    if not urls:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for u in urls:
        canonical = normalize_url(u)
        cur = conn.execute(
            "UPDATE items SET deep_analyzed_at = ? WHERE canonical_url = ?",
            (now, canonical),
        )
        updated += cur.rowcount
    log.info("marked %d url(s) as deep-analyzed", updated)
    return updated


# Backward compat alias — keep until all callers migrate. Behavior is the new one.
filter_new = record_candidates
