from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from src.models import BriefCluster, DeepAnalysis, DigestPayload, NewsItem, Prediction
from src.pipeline.dedup import (
    get_recently_deep_analyzed_urls,
    mark_deep_analyzed,
    normalize_url,
    open_db,
    record_candidates,
)
from src.pipeline.rank import rank
from src.pipeline.render import render_daily


def _load_sample() -> list[NewsItem]:
    raw = json.loads(Path("fixtures/sample_items.json").read_text(encoding="utf-8"))
    return [
        NewsItem(
            id=r["id"],
            title=r["title"],
            url=r["url"],
            source=r["source"],
            published_at=datetime.fromisoformat(r["published_at"]),
            score=r["score"],
            comments=r["comments"],
        )
        for r in raw
    ]


def test_normalize_url_strips_tracking_and_trailing_slash():
    assert normalize_url("https://www.example.com/foo/?utm_source=x&id=1") == "https://example.com/foo?id=1"
    assert normalize_url("http://Example.com/Bar/") == "http://example.com/Bar"


def test_record_candidates_dedups_intra_batch_only():
    """Same canonical URL appearing twice in one batch is folded once.
    Items seen in PRIOR runs are NOT filtered — they re-enter the LLM pool."""
    items = _load_sample()
    dup = NewsItem(
        id="hn-sample-001-dup",
        title="duplicate of opus 4.7",
        url="https://www.anthropic.com/news/claude-opus-4-7?utm_source=share",
        source="hackernews",
        published_at=items[0].published_at,
        score=10,
        comments=2,
    )
    items.append(dup)
    with tempfile.TemporaryDirectory() as td:
        with open_db(Path(td) / "test.db") as conn:
            out = record_candidates(conn, items)
    assert len(out) == 10  # intra-batch dup folded; original 10 unique URLs kept


def test_record_candidates_keeps_previously_seen_items():
    """A candidate seen in a prior run still comes back the next day."""
    items = _load_sample()
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        with open_db(db) as conn:
            first = record_candidates(conn, items)
        # Second run with the same items — should NOT shrink
        with open_db(db) as conn:
            second = record_candidates(conn, items)
            row = conn.execute(
                "SELECT seen_count FROM items WHERE canonical_url = ?",
                (normalize_url(items[0].url),),
            ).fetchone()
    assert len(first) == 10
    assert len(second) == 10  # critical: dedup no longer drops on day 2
    assert row["seen_count"] == 2


def test_mark_and_query_deep_analyzed_urls():
    items = _load_sample()
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        with open_db(db) as conn:
            record_candidates(conn, items)
            mark_deep_analyzed(conn, [items[0].url, items[3].url])
            blocked = get_recently_deep_analyzed_urls(conn, days=14)
    assert normalize_url(items[0].url) in blocked
    assert normalize_url(items[3].url) in blocked
    assert normalize_url(items[1].url) not in blocked
    assert len(blocked) == 2


def test_ranking_orders_by_weighted_score():
    items = _load_sample()
    ranked = rank(items, {"weights": {"score": 0.5, "comments": 0.3, "recency_hours": 0.2}, "recency_decay_hours": 48})
    assert ranked[0].score >= ranked[-1].score
    assert len(ranked) == len(items)


def test_render_daily_produces_frontmatter_and_sections():
    items = _load_sample()
    deeps = [
        DeepAnalysis(
            item=items[0],
            fact="发布 Claude Opus 4.7。",
            context="Anthropic 在前代基础上扩展 context window 至 1M。",
            stakeholders="开发者：欢迎。竞品：被动应对。",
            implications="长上下文 RAG 工作流可简化；token cost 重新被关注。",
            uncertainty="性价比尚需第三方 benchmark。",
            confidence="高",
            source_excerpt=None,
        )
    ]
    brief_overview = "今日速览主要围绕模型版本号、企业合作、安全合规三类。"
    brief_clusters = [
        BriefCluster(theme="模型与版本", items=[(items[2], "OpenAI 给批处理推理降价。")]),
        BriefCluster(theme="政策与监管", items=[(items[5], "EU AI Act 第二轮执法细则落地。")]),
    ]
    weak = [(items[7], "小团队便宜训练 / 盯：MMLU 复现")]
    preds = [
        Prediction(
            statement="若 Opus 4.7 性价比兑现，6 个月内 1M context 成为新基线",
            rationale="基于发布与定价信号",
            verify_by="2026-11-19",
            falsifiable_when="3 家主要厂商无对标 1M context 模型",
            related_item_url=items[0].url,
        )
    ]
    payload = DigestPayload(
        date="2026-05-19",
        one_liner="Anthropic Opus 4.7 + 1M context 成为今日主线",
        deep=deeps,
        brief_overview=brief_overview,
        brief_clusters=brief_clusters,
        weak_signals=weak,
        trend_links=["- [[LLM-训练与推理]] — 长上下文走向"],
        predictions=preds,
        sources_count=10,
        run_id=uuid.uuid4().hex[:8],
    )
    md = render_daily(payload)
    assert "type: daily-digest" in md
    assert "🔥 热点深度" in md
    assert "🔮 预判草稿" in md
    assert "Anthropic Opus 4.7" in md
    assert "[[LLM-训练与推理]]" in md
    assert "模型与版本" in md
    assert "今日速览主要" in md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
