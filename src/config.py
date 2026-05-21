from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    load_dotenv()
    p = Path(path)
    if not p.exists():
        example = Path("config.example.yaml")
        if example.exists():
            raise FileNotFoundError(
                f"{p} not found. Copy config.example.yaml to config.yaml and edit."
            )
        raise FileNotFoundError(str(p))
    with p.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_env"] = {
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
    }
    return cfg
