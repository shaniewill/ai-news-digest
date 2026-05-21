from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from src.engagement import SOURCE_METRICS_GUIDE
from src.llm.anthropic_client import AnthropicLLM, load_prompt
from src.models import BriefCluster, DeepAnalysis, DigestPayload, NewsItem, Prediction

log = logging.getLogger("analyze")


def _items_json(items: list[NewsItem]) -> str:
    return json.dumps([it.to_dict() for it in items], ensure_ascii=False, indent=2)


def _by_id(items: list[NewsItem]) -> dict[str, NewsItem]:
    return {it.id: it for it in items}


def run_curator(
    items: list[NewsItem],
    cfg: dict[str, Any],
    llm: AnthropicLLM,
    blocked_deep_urls: frozenset[str] | set[str] = frozenset(),
) -> dict[str, Any]:
    prompt = load_prompt("curator")
    deep_n = int(cfg["llm"].get("max_items_deep", 5))
    brief_n = int(cfg["llm"].get("max_items_brief", 35))
    weak_n = int(cfg["llm"].get("max_items_weak", 5))

    blocked_section = ""
    if blocked_deep_urls:
        blocked_section = (
            "\n\nblocked_deep_urls (近期已被 deep-analyst 深挖过的 canonical URL，"
            "不能再进 deep_ids；可以进 brief_ids 或 weak_ids):\n"
            f"{json.dumps(sorted(blocked_deep_urls), ensure_ascii=False, indent=2)}\n"
        )

    user = (
        f"max_items_deep={deep_n}\nmax_items_brief={brief_n}\nmax_items_weak={weak_n}"
        f"{blocked_section}\n"
        f"{SOURCE_METRICS_GUIDE}\n\n"
        f"items:\n{_items_json(items)}"
    )
    out = llm.call_json(prompt, user, deep=False, max_tokens=2048)
    log.info(
        "curator picked deep=%d brief=%d weak=%d (blocked_deep_urls=%d)",
        len(out.get("deep_ids", [])),
        len(out.get("brief_ids", [])),
        len(out.get("weak_ids", [])),
        len(blocked_deep_urls),
    )
    return out


def run_deep_analyst(item: NewsItem, llm: AnthropicLLM) -> DeepAnalysis:
    prompt = load_prompt("deep_analyst")
    user = (
        f"{SOURCE_METRICS_GUIDE}\n\n"
        f"item:\n{json.dumps(item.to_dict(), ensure_ascii=False, indent=2)}"
    )
    out = llm.call_json(prompt, user, deep=True, max_tokens=2048)
    return DeepAnalysis(
        item=item,
        fact=out.get("fact", ""),
        context=out.get("context", ""),
        stakeholders=out.get("stakeholders", ""),
        implications=out.get("implications", ""),
        uncertainty=out.get("uncertainty", ""),
        confidence=out.get("confidence", "中"),
        source_excerpt=out.get("source_excerpt") or None,
    )


def run_brief_summarizer(
    items: list[NewsItem], cfg: dict[str, Any], llm: AnthropicLLM
) -> tuple[str, list[BriefCluster]]:
    if not items:
        return "", []
    prompt = load_prompt("brief_summarizer")
    target_clusters = int(cfg["llm"].get("brief_clusters", 4))
    user = f"target_clusters={target_clusters}\n\nitems:\n{_items_json(items)}"
    out = llm.call_json(prompt, user, deep=False, max_tokens=3500)
    by_id = _by_id(items)
    overview = out.get("overview", "")
    clusters: list[BriefCluster] = []
    seen_ids: set[str] = set()
    for c in out.get("clusters", []):
        theme = (c.get("theme") or "").strip() or "其他"
        pairs: list[tuple[NewsItem, str]] = []
        for b in c.get("items", []):
            iid = b.get("id", "")
            it = by_id.get(iid)
            if it and iid not in seen_ids:
                pairs.append((it, b.get("one_line", "")))
                seen_ids.add(iid)
        if pairs:
            clusters.append(BriefCluster(theme=theme, items=pairs))
    # 兜底：未被分入 cluster 的 items 放到"其他"
    leftovers = [(it, "") for it in items if it.id not in seen_ids]
    if leftovers:
        clusters.append(BriefCluster(theme="其他", items=leftovers))
    return overview, clusters


def run_weak_signal_scout(items: list[NewsItem], llm: AnthropicLLM) -> list[tuple[NewsItem, str]]:
    if not items:
        return []
    prompt = load_prompt("weak_signal_scout")
    user = f"items:\n{_items_json(items)}"
    out = llm.call_json(prompt, user, deep=False, max_tokens=1500)
    by_id = _by_id(items)
    pairs: list[tuple[NewsItem, str]] = []
    for s in out.get("signals", []):
        it = by_id.get(s.get("id", ""))
        if it:
            note = f"{s.get('why_weak', '')} / 盯：{s.get('what_to_watch', '')}"
            pairs.append((it, note))
    return pairs


def run_trend_connector(deeps: list[DeepAnalysis], llm: AnthropicLLM) -> list[str]:
    if not deeps:
        return []
    prompt = load_prompt("trend_connector")
    items_payload = [
        {"id": d.item.id, "title": d.item.title, "url": d.item.url, "context": d.context}
        for d in deeps
    ]
    user = f"deep_items:\n{json.dumps(items_payload, ensure_ascii=False, indent=2)}"
    try:
        out = llm.call_json(prompt, user, deep=False, max_tokens=1200)
    except Exception as e:
        log.warning("trend_connector failed: %s", e)
        return []
    lines: list[str] = []
    for link in out.get("links", []):
        topics = link.get("topics", []) or []
        if not topics:
            continue
        wikilinks = " ".join(f"[[{t}]]" for t in topics)
        lines.append(f"- {wikilinks} — {link.get('one_line_link', '')}")
    return lines


def run_prediction_drafter(deeps: list[DeepAnalysis], llm: AnthropicLLM) -> list[Prediction]:
    if not deeps:
        return []
    prompt = load_prompt("prediction_drafter")
    items_payload = [
        {
            "id": d.item.id,
            "title": d.item.title,
            "url": d.item.url,
            "implications": d.implications,
        }
        for d in deeps
    ]
    user = f"deep_items:\n{json.dumps(items_payload, ensure_ascii=False, indent=2)}"
    out = llm.call_json(prompt, user, deep=True, max_tokens=1500)
    preds: list[Prediction] = []
    for p in out.get("predictions", []):
        if not p.get("statement"):
            continue
        preds.append(
            Prediction(
                statement=p["statement"],
                rationale=p.get("rationale", ""),
                verify_by=p.get("verify_by", ""),
                falsifiable_when=p.get("falsifiable_when", ""),
                related_item_url=p.get("related_item_url"),
            )
        )
    return preds


def run_daily(
    items: list[NewsItem],
    cfg: dict[str, Any],
    llm: AnthropicLLM,
    blocked_deep_urls: frozenset[str] | set[str] = frozenset(),
) -> DigestPayload:
    run_id = uuid.uuid4().hex[:8]
    by_id = _by_id(items)

    curated = run_curator(items, cfg, llm, blocked_deep_urls=blocked_deep_urls)
    # Belt-and-suspenders: even if the LLM picks a blocked URL into deep_ids,
    # drop it here so we never re-run deep_analyst on the same canonical URL.
    if blocked_deep_urls:
        from src.pipeline.dedup import normalize_url
        original_deep = list(curated.get("deep_ids", []))
        filtered = [
            iid for iid in original_deep
            if iid in by_id and normalize_url(by_id[iid].url) not in blocked_deep_urls
        ]
        dropped = len(original_deep) - len(filtered)
        if dropped:
            log.warning("curator picked %d blocked URL(s) into deep — dropping them", dropped)
        curated["deep_ids"] = filtered
    deep_items = [by_id[i] for i in curated.get("deep_ids", []) if i in by_id]
    brief_items = [by_id[i] for i in curated.get("brief_ids", []) if i in by_id]
    weak_items = [by_id[i] for i in curated.get("weak_ids", []) if i in by_id]
    one_liner = curated.get("one_liner", "")

    log.info("running deep_analyst on %d items", len(deep_items))
    deeps = [run_deep_analyst(it, llm) for it in deep_items]

    log.info("running brief_summarizer on %d items", len(brief_items))
    brief_overview, brief_clusters = run_brief_summarizer(brief_items, cfg, llm)

    log.info("running weak_signal_scout on %d items", len(weak_items))
    weak_signals = run_weak_signal_scout(weak_items, llm)

    log.info("running trend_connector")
    trend_links = run_trend_connector(deeps, llm)

    log.info("running prediction_drafter")
    predictions = run_prediction_drafter(deeps, llm)

    return DigestPayload(
        date=datetime.now().strftime("%Y-%m-%d"),
        one_liner=one_liner,
        deep=deeps,
        brief_overview=brief_overview,
        brief_clusters=brief_clusters,
        weak_signals=weak_signals,
        trend_links=trend_links,
        predictions=predictions,
        sources_count=len(items),
        run_id=run_id,
    )
