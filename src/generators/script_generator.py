"""
script_generator.py — Generates TikTok scripts using the Claude API.

Takes scraped hook data from Phase 1 (trending videos + ads) and feeds it
to Claude to generate new scripts in hook/body/CTA format.

Pipeline:
  1. Load latest scraped hooks from data/raw/
  2. Build prompt with trending + ad hooks
  3. Call Claude API (single request — all hooks together so Claude sees patterns)
  4. Parse JSON response, enrich with metadata
  5. Save to data/scripts/scripts_<timestamp>.json

Usage:
  python -m src.generators.script_generator
"""

import json
import re
import uuid

import anthropic
from rich import print as rprint
from rich.table import Table

from src.generators.templates import (
    CLAUDE_MODEL,
    MAX_TOKENS,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from src.utils.config import ANTHROPIC_API_KEY, DATA_RAW_DIR, DATA_SCRIPTS_DIR
from src.utils.data_io import load_latest, save_json


def load_hooks() -> tuple[list[dict], list[dict]]:
    """
    Load the latest scraped hooks from data/raw/.

    Returns:
        Tuple of (trending_hooks, ad_hooks). Either may be empty.
    """
    trending = load_latest(DATA_RAW_DIR, "trending_videos") or []
    ads = load_latest(DATA_RAW_DIR, "ads") or []

    if not trending and not ads:
        rprint("[yellow]Warning: No scraped hook data found in data/raw/[/yellow]")
        rprint("[yellow]Run scrapers first, or the generator will use generic prompts.[/yellow]")

    return trending, ads


def generate_scripts(
    trending_hooks: list[dict],
    ad_hooks: list[dict],
    num_scripts: int = 5,
) -> list[dict]:
    """
    Call the Claude API to generate TikTok scripts from hook data.

    Args:
        trending_hooks: Trending video hooks with stats
        ad_hooks: Ad hooks with CTAs
        num_scripts: Number of scripts to generate

    Returns:
        List of parsed script dicts
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_prompt = build_user_prompt(trending_hooks, ad_hooks, num_scripts)

    rprint(f"[blue]Calling Claude API ({CLAUDE_MODEL})…[/blue]")
    rprint(f"[dim]Requesting {num_scripts} scripts[/dim]")

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text

    # Print token usage
    usage = response.usage
    rprint(
        f"[dim]Tokens — input: {usage.input_tokens}, "
        f"output: {usage.output_tokens}[/dim]"
    )

    return parse_scripts(raw_text, trending_hooks, ad_hooks)


def parse_scripts(
    raw_text: str,
    trending_hooks: list[dict],
    ad_hooks: list[dict],
) -> list[dict]:
    """
    Parse Claude's response text into a list of script dicts.

    Handles markdown fencing if present, enriches each script with
    metadata (ID, source type, duration estimate).

    Args:
        raw_text: Raw text from Claude's response
        trending_hooks: Used to determine source_type
        ad_hooks: Used to determine source_type

    Returns:
        List of enriched script dicts, or empty list on parse failure
    """
    text = raw_text.strip()

    # Strip markdown code fencing if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    # Fallback: find the JSON array boundaries
    if not text.startswith("["):
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    try:
        scripts = json.loads(text)
    except json.JSONDecodeError as e:
        rprint(f"[red]Failed to parse Claude's response as JSON: {e}[/red]")
        rprint(f"[dim]Raw response (first 500 chars): {raw_text[:500]}[/dim]")
        return []

    if not isinstance(scripts, list):
        rprint("[red]Expected a JSON array of scripts, got something else.[/red]")
        return []

    # Determine source type
    has_trending = len(trending_hooks) > 0
    has_ads = len(ad_hooks) > 0
    if has_trending and has_ads:
        source_type = "mixed"
    elif has_trending:
        source_type = "trending"
    elif has_ads:
        source_type = "ad"
    else:
        source_type = "mixed"

    # Enrich each script with metadata
    for script in scripts:
        script["script_id"] = str(uuid.uuid4())
        script["source_type"] = source_type

        # Estimate duration from word count (body + hook + cta)
        all_text = " ".join(
            script.get(k, "") for k in ("hook", "body", "cta")
        )
        word_count = len(all_text.split())
        script["estimated_duration_sec"] = round(word_count / 3)

    rprint(f"[green]Parsed {len(scripts)} scripts from Claude's response[/green]")
    return scripts


def display_scripts(scripts: list[dict]) -> None:
    """Pretty-print generated scripts as a rich table."""
    if not scripts:
        rprint("[yellow]No scripts to display.[/yellow]")
        return

    table = Table(title="Generated TikTok Scripts", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Hook", style="bold cyan", max_width=35)
    table.add_column("Body", style="white", max_width=50)
    table.add_column("CTA", style="green", max_width=25)
    table.add_column("Duration", style="yellow", justify="right", width=8)

    for i, script in enumerate(scripts, 1):
        hook = script.get("hook", "")
        body = script.get("body", "")
        cta = script.get("cta", "")
        duration = script.get("estimated_duration_sec", 0)

        # Truncate body for display
        if len(body) > 120:
            body = body[:117] + "..."

        table.add_row(str(i), hook, body, cta, f"{duration}s")

    rprint(table)


def run(num_scripts: int = 5) -> list[dict]:
    """
    Full pipeline: load hooks -> generate scripts -> save -> display.

    Args:
        num_scripts: Number of scripts to generate

    Returns:
        List of generated script dicts
    """
    trending_hooks, ad_hooks = load_hooks()

    scripts = generate_scripts(trending_hooks, ad_hooks, num_scripts)

    if scripts:
        save_json(scripts, "scripts", DATA_SCRIPTS_DIR)
        display_scripts(scripts)
    else:
        rprint("[red]No scripts were generated.[/red]")

    return scripts


# ── Run standalone for testing ──
if __name__ == "__main__":
    rprint("[bold blue]TikTok Script Generator[/bold blue]")
    rprint("─" * 40)

    if not ANTHROPIC_API_KEY:
        rprint("[red]ERROR: ANTHROPIC_API_KEY not set in .env[/red]")
        rprint("Copy .env.example to .env and add your Anthropic API key.")
    else:
        run()
