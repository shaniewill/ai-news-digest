from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.logging import RichHandler

from src.config import load_config
from src.fetchers import REGISTRY as FETCHERS
from src.fetchers import get as get_fetcher
from src.llm.anthropic_client import AnthropicLLM
from src.models import NewsItem
from src.obsidian.writer import write_daily, write_predictions
from src.pipeline.analyze import run_daily as analyze_daily
from src.pipeline.dedup import (
    get_recently_deep_analyzed_urls,
    mark_deep_analyzed,
    open_db,
    record_candidates,
)
from src.pipeline.rank import rank
from src.pipeline.render import render_daily

console = Console()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


async def _fetch_all(cfg: dict[str, Any]) -> list[NewsItem]:
    enabled = [name for name, _ in FETCHERS.items()
               if cfg.get("sources", {}).get(name, {}).get("enabled", True)]
    console.log(f"fetchers: {enabled}")
    results = await asyncio.gather(
        *(get_fetcher(n)(cfg) for n in enabled),
        return_exceptions=True,
    )
    items: list[NewsItem] = []
    for name, r in zip(enabled, results, strict=True):
        if isinstance(r, Exception):
            console.log(f"[red]{name} failed: {r}")
            continue
        items.extend(r)
    return items


@click.group()
@click.option("--config", "config_path", default="config.yaml", help="config.yaml path")
@click.option("-v", "--verbose", is_flag=True)
@click.pass_context
def cli(ctx: click.Context, config_path: str, verbose: bool) -> None:
    _setup_logging(verbose=verbose)
    ctx.ensure_object(dict)
    ctx.obj["cfg"] = load_config(config_path)


@cli.command("daily")
@click.option("--dry-run", is_flag=True, help="render but don't write vault / DB")
@click.pass_context
def daily(ctx: click.Context, dry_run: bool) -> None:
    cfg = ctx.obj["cfg"]
    if dry_run:
        cfg["run"]["dry_run"] = True

    items = asyncio.run(_fetch_all(cfg))
    console.log(f"fetched {len(items)} raw items")

    db_path = cfg["run"]["db_path"]
    block_days = int(cfg.get("run", {}).get("deep_repeat_block_days", 14))
    with open_db(db_path) as conn:
        # Always read blocked URLs (read-only) so dry-run reflects what the real
        # run would do. Only the writes (record_candidates, mark_deep_analyzed)
        # are skipped in dry-run.
        blocked_deep_urls = get_recently_deep_analyzed_urls(conn, days=block_days)
        if dry_run:
            candidates = items
            console.log("[yellow]dry-run: skipping DB writes")
        else:
            candidates = record_candidates(conn, items)
        ranked = rank(candidates, cfg.get("ranking", {}))
        console.log(
            f"ranked {len(ranked)} items "
            f"(blocked_deep={len(blocked_deep_urls)} url(s) in last {block_days}d)"
        )

        if not ranked:
            console.log("[red]no items to analyze, exiting")
            sys.exit(1)

        llm = AnthropicLLM(cfg)
        payload = analyze_daily(ranked, cfg, llm, blocked_deep_urls=blocked_deep_urls)
        rendered = render_daily(payload)

        if dry_run:
            preview_path = Path("data") / f"dry-run-{payload.date}-{payload.run_id}.md"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.write_text(rendered, encoding="utf-8")
            console.log(f"[yellow]dry-run: rendered to {preview_path} ({len(rendered)} chars)")
        else:
            out_path = write_daily(payload, rendered, cfg)
            write_predictions(payload, cfg)
            # Mark the URLs we just deep-analyzed so future curators don't repeat them.
            deep_urls = [d.item.url for d in payload.deep]
            mark_deep_analyzed(conn, deep_urls)
            console.log(f"[green]digest written: {out_path}")


@cli.command("test-source")
@click.argument("name")
@click.pass_context
def test_source(ctx: click.Context, name: str) -> None:
    cfg = ctx.obj["cfg"]
    fetcher = get_fetcher(name)
    items = asyncio.run(fetcher(cfg))
    out = [it.to_dict() for it in items[:10]]
    click.echo(json.dumps(out, ensure_ascii=False, indent=2))
    console.log(f"[green]{name}: {len(items)} items")


@cli.command("list-sources")
def list_sources() -> None:
    for name in FETCHERS:
        click.echo(name)


@cli.command("weekly")
@click.pass_context
def weekly(ctx: click.Context) -> None:
    from src.pipeline.weekly import run_weekly

    cfg = ctx.obj["cfg"]
    llm = AnthropicLLM(cfg)
    _, out_path = run_weekly(cfg, llm)
    console.log(f"[green]weekly review written: {out_path}")


if __name__ == "__main__":
    cli(obj={})
