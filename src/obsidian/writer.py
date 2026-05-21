from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from src.models import DigestPayload, Prediction

log = logging.getLogger("obsidian")


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w一-龥]+", "-", text.lower()).strip("-")
    return s[:max_len] or "untitled"


def write_daily(payload: DigestPayload, rendered: str, cfg: dict[str, Any]) -> Path:
    vault = Path(cfg["vault"]["path"])
    daily_dir = vault / cfg["vault"]["daily_dir"]
    daily_dir.mkdir(parents=True, exist_ok=True)
    out_path = daily_dir / f"{payload.date}.md"
    out_path.write_text(rendered, encoding="utf-8")
    log.info("wrote %s", out_path)
    return out_path


def write_predictions(payload: DigestPayload, cfg: dict[str, Any]) -> list[Path]:
    if not payload.predictions:
        return []
    vault = Path(cfg["vault"]["path"])
    preds_dir = vault / cfg["vault"]["predictions_dir"]
    preds_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for i, p in enumerate(payload.predictions):
        slug = _slug(p.statement, max_len=30)
        fname = f"pred-{payload.date}-{i+1:02d}-{slug}.md"
        path = preds_dir / fname
        path.write_text(_render_prediction(payload.date, p), encoding="utf-8")
        written.append(path)
    log.info("wrote %d prediction files", len(written))
    return written


def _render_prediction(date: str, p: Prediction) -> str:
    return f"""---
type: prediction
created: {date}
verify_by: {p.verify_by}
status: pending
tags: [prediction, ai-news]
---

# {p.statement}

**依据**：{p.rationale}

**验证时间点**：{p.verify_by}

**证伪条件**：{p.falsifiable_when}

{f"**相关来源**：{p.related_item_url}" if p.related_item_url else ""}

---

## 回溯（待复盘时填写）

- 状态：⏳ pending
- 实际观察：
- 学到了什么：
"""
