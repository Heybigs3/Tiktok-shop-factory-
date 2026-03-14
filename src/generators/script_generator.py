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
    PRODUCT_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_product_prompt,
    build_user_prompt,
)
from src.utils.config import ANTHROPIC_API_KEY, DATA_PROCESSED_DIR, DATA_RAW_DIR, DATA_SCRIPTS_DIR, load_pipeline_config
from src.utils.data_io import load_latest, save_json


def load_hooks() -> tuple[list[dict], list[dict], list[dict]]:
    """
    Load the latest scraped hooks and hashtags.

    Prefers enriched data from data/processed/ (produced by hook_processor).
    Falls back to raw data from data/raw/ for backward compatibility.

    Returns:
        Tuple of (trending_hooks, ad_hooks, hashtags). Any may be empty.
    """
    # Try processed data first (enriched, deduped, filtered)
    trending = load_latest(DATA_PROCESSED_DIR, "processed_hooks")
    if trending is not None:
        rprint(f"[green]Loaded {len(trending)} processed video hooks[/green]")
    else:
        trending = load_latest(DATA_RAW_DIR, "trending_videos") or []
        if trending:
            rprint("[yellow]Using raw data — run scrapers again for processed hooks[/yellow]")

    ads = load_latest(DATA_PROCESSED_DIR, "processed_ad_hooks")
    if ads is not None:
        rprint(f"[green]Loaded {len(ads)} processed ad hooks[/green]")
    else:
        ads = load_latest(DATA_RAW_DIR, "ads") or []
        if ads:
            rprint("[yellow]Using raw ad data — run scrapers again for processed hooks[/yellow]")

    hashtags = load_latest(DATA_RAW_DIR, "hashtags") or []

    if not trending and not ads:
        rprint("[yellow]Warning: No scraped hook data found[/yellow]")
        rprint("[yellow]Run scrapers first, or the generator will use generic prompts.[/yellow]")

    if hashtags:
        rprint(f"[green]Loaded {len(hashtags)} trending hashtags[/green]")

    return trending, ads, hashtags


def load_products() -> list[dict]:
    """
    Load the latest scraped product data from data/raw/.

    Returns:
        List of product dicts, or empty list if none found.
    """
    products = load_latest(DATA_RAW_DIR, "products")
    if products:
        rprint(f"[green]Loaded {len(products)} products[/green]")
    else:
        products = []
    return products


def generate_scripts(
    trending_hooks: list[dict],
    ad_hooks: list[dict],
    num_scripts: int = 5,
    trending_hashtags: list[dict] | None = None,
    niche: str = "",
    mode: str = "content",
    products: list[dict] | None = None,
) -> list[dict]:
    """
    Call the Claude API to generate TikTok scripts from hook data.

    Args:
        trending_hooks: Trending video hooks with stats
        ad_hooks: Ad hooks with CTAs
        num_scripts: Number of scripts to generate
        trending_hashtags: Trending hashtag data for script enrichment
        niche: Target niche from pipeline_config.json
        mode: "content" for viral content scripts, "product" for TikTok Shop product scripts
        products: Product data from Kalodata (used when mode="product")

    Returns:
        List of parsed script dicts
    """
    # Load Style Bible if available (enhances prompt with analyzed patterns)
    style_bible_duration = None
    try:
        from src.analyzers.style_bible import load_style_bible
        style_context = load_style_bible(niche if niche else None)
        # Also load raw Style Bible dict to extract numeric duration
        from src.analyzers.style_overrides import _load_style_bible as _load_sb_dict
        sb_dict = _load_sb_dict()
        if sb_dict:
            style_bible_duration = (
                sb_dict.get("structure_patterns", {}).get("avg_duration_s")
            )
    except ImportError:
        style_context = None

    # Load comparison report gaps (feedback loop — tells Claude what to fix)
    try:
        from src.analyzers.style_overrides import get_prompt_overrides
        comparison_context = get_prompt_overrides()
    except ImportError:
        comparison_context = None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Select prompt and system prompt based on mode
    if mode == "product" and products:
        system_prompt = PRODUCT_SYSTEM_PROMPT
        user_prompt = build_product_prompt(
            products, hooks=trending_hooks, hashtags=trending_hashtags,
            niche=niche, num_scripts=num_scripts,
        )
        rprint(f"[blue]Calling Claude API ({CLAUDE_MODEL}) — product mode[/blue]")
    else:
        system_prompt = SYSTEM_PROMPT
        user_prompt = build_user_prompt(trending_hooks, ad_hooks, num_scripts, trending_hashtags, niche)
        rprint(f"[blue]Calling Claude API ({CLAUDE_MODEL})…[/blue]")

    # Inject Style Bible into system prompt if available
    if style_context:
        system_prompt += f"\n\n## Style Intelligence\n{style_context}"
        rprint("[green]Style Bible loaded -- scripts will follow analyzed patterns[/green]")

    # Inject data-driven duration constraint from Style Bible
    if style_bible_duration:
        wps = 2.5  # words per second at natural speaking pace
        target_words = int(style_bible_duration * wps)
        system_prompt += (
            f"\n\n## Duration Target (data-driven)\n"
            f"Target total video duration: {style_bible_duration}s "
            f"(based on top-performing videos in this niche). "
            f"Write enough body content to fill this time when read aloud "
            f"at natural pace (~2.5 words/second = ~{target_words} words total). "
            f"Include target_duration_sec in visual_hints."
        )
        rprint(f"[green]Duration target: {style_bible_duration}s from Style Bible[/green]")

    # Inject comparison gaps (feedback loop — most important for improvement)
    if comparison_context:
        system_prompt += f"\n\n{comparison_context}"
        rprint("[green]Comparison gaps loaded -- scripts will address identified weaknesses[/green]")

    rprint(f"[dim]Requesting {num_scripts} scripts[/dim]")

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as e:
        rprint(f"[red]Claude API error: {e}[/red]")
        return []

    raw_text = response.content[0].text

    # Print token usage
    usage = response.usage
    rprint(
        f"[dim]Tokens — input: {usage.input_tokens}, "
        f"output: {usage.output_tokens}[/dim]"
    )

    scripts = parse_scripts(raw_text, trending_hooks, ad_hooks, style_bible_duration)

    # Enrich scripts with product metadata so downstream modules can track lineage
    if products and scripts:
        for i, script in enumerate(scripts):
            if i < len(products):
                script["product_id"] = products[i].get("product_id", "")
                script["product_title"] = products[i].get("title", "")
                price = products[i].get("price")
                if price is not None:
                    script["product_price"] = price

    return scripts


def parse_scripts(
    raw_text: str,
    trending_hooks: list[dict],
    ad_hooks: list[dict],
    style_bible_duration: float | None = None,
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

        # Estimate duration: prefer Claude's target, then Style Bible, then word count
        visual_hints = script.get("visual_hints", {})
        target_dur = visual_hints.get("target_duration_sec") if isinstance(visual_hints, dict) else None
        if target_dur and isinstance(target_dur, (int, float)) and target_dur > 0:
            script["estimated_duration_sec"] = round(target_dur)
        elif style_bible_duration and style_bible_duration > 0:
            script["estimated_duration_sec"] = round(style_bible_duration)
        else:
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


def run(num_scripts: int | None = None) -> list[dict]:
    """
    Full pipeline: load hooks -> generate scripts -> save -> display.

    Args:
        num_scripts: Number of scripts to generate (reads from pipeline_config.json if None)

    Returns:
        List of generated script dicts
    """
    config = load_pipeline_config()
    if num_scripts is None:
        num_scripts = config.get("num_scripts", 5)
    niche = config.get("niche", "")

    # Determine mode from config
    video_style = config.get("video_style", "content")
    product_styles = {"product_showcase", "ugc_showcase", "comparison"}
    mode = "product" if video_style in product_styles else "content"

    trending_hooks, ad_hooks, hashtags = load_hooks()

    # Load products for product mode
    products = None
    if mode == "product":
        products = load_products()
        if not products:
            rprint("[yellow]No product data found — falling back to content mode[/yellow]")
            mode = "content"
        else:
            # 1 product = 1 script = 1 video — override config num_scripts
            num_scripts = len(products)
            rprint(f"[blue]Product mode: {num_scripts} products → {num_scripts} scripts (1:1:1)[/blue]")

    if mode == "content":
        rprint(f"[blue]Content mode: generating {num_scripts} scripts from config[/blue]")

    scripts = generate_scripts(
        trending_hooks, ad_hooks, num_scripts, hashtags, niche,
        mode=mode, products=products,
    )

    if scripts:
        save_json(scripts, "scripts", DATA_SCRIPTS_DIR)
        display_scripts(scripts)
    else:
        rprint("[red]No scripts were generated.[/red]")

    return scripts


# ── Run standalone for testing ──
if __name__ == "__main__":
    rprint("[bold blue]TikTok Script Generator[/bold blue]")
    rprint("-" * 40)

    if not ANTHROPIC_API_KEY:
        rprint("[red]ERROR: ANTHROPIC_API_KEY not set in .env[/red]")
        rprint("Copy .env.example to .env and add your Anthropic API key.")
    else:
        run()
