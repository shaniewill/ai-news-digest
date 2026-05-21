from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.llm.anthropic_client import AnthropicLLM, load_prompt

log = logging.getLogger("weekly")


def _collect_recent_daily(vault: Path, daily_dir: str, days: int = 7) -> list[tuple[str, str]]:
    folder = vault / daily_dir
    if not folder.exists():
        return []
    today = datetime.now().date()
    out: list[tuple[str, str]] = []
    for d in range(days):
        date = today - timedelta(days=d)
        path = folder / f"{date.isoformat()}.md"
        if path.exists():
            out.append((date.isoformat(), path.read_text(encoding="utf-8")))
    return out


def _collect_recent_predictions(vault: Path, preds_dir: str, days: int = 14) -> list[tuple[str, str]]:
    folder = vault / preds_dir
    if not folder.exists():
        return []
    cutoff = datetime.now().date() - timedelta(days=days)
    out: list[tuple[str, str]] = []
    for path in sorted(folder.glob("pred-*.md")):
        text = path.read_text(encoding="utf-8")
        first_line = text.split("\n", 1)[0]
        try:
            ymd = path.stem.split("-", 4)
            if len(ymd) >= 4:
                date = datetime.strptime("-".join(ymd[1:4]), "%Y-%m-%d").date()
                if date < cutoff:
                    continue
        except Exception:
            pass
        out.append((path.name, text))
    return out


def run_weekly(cfg: dict[str, Any], llm: AnthropicLLM) -> tuple[str, Path]:
    vault = Path(cfg["vault"]["path"])
    dailies = _collect_recent_daily(vault, cfg["vault"]["daily_dir"], days=7)
    preds = _collect_recent_predictions(vault, cfg["vault"]["predictions_dir"], days=14)

    if not dailies:
        raise RuntimeError(f"no daily digests found in {vault / cfg['vault']['daily_dir']}")

    daily_blob = "\n\n=====\n\n".join(
        f"# {date}\n\n{content}" for date, content in dailies
    )
    pred_blob = "\n\n---\n\n".join(f"## {name}\n\n{content}" for name, content in preds) or "（无）"

    prompt = load_prompt("weekly_reviewer")
    user = f"## 过去 7 天 daily digests\n\n{daily_blob}\n\n## 过去 14 天 predictions\n\n{pred_blob}"
    result = llm.call(prompt, user, deep=True, max_tokens=4096)

    today = datetime.now().date()
    iso_year, iso_week, _ = today.isocalendar()
    weekly_dir = vault / cfg["vault"]["weekly_dir"]
    weekly_dir.mkdir(parents=True, exist_ok=True)
    out_path = weekly_dir / f"{iso_year}-W{iso_week:02d}.md"

    frontmatter = f"""---
type: weekly-review
date: {today.isoformat()}
week: {iso_year}-W{iso_week:02d}
dailies_included: {len(dailies)}
predictions_reviewed: {len(preds)}
tags: [ai-news, weekly, auto]
---

# Weekly review — {iso_year}-W{iso_week:02d}

"""
    out_path.write_text(frontmatter + result.text + "\n", encoding="utf-8")
    log.info("wrote weekly review to %s (tokens: %d in / %d out)", out_path, result.input_tokens, result.output_tokens)
    return result.text, out_path
