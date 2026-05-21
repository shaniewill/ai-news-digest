from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from src.engagement import format_engagement
from src.models import DigestPayload


def _env(template_dir: str | Path = "templates") -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(disabled_extensions=("md", "j2")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["engagement_line"] = format_engagement
    return env


def render_daily(payload: DigestPayload, template_dir: str | Path = "templates") -> str:
    env = _env(template_dir)
    tpl = env.get_template("daily-digest.md.j2")
    return tpl.render(p=payload)
