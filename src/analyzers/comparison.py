"""
comparison.py — Compare scraped TikTok videos against our rendered videos.

Loads per-video analyses from both sets, sends to Claude for a structured
gap analysis, and outputs actionable improvement recommendations.

Usage:
  python -m src.analyzers  # menu option 7
"""

import json
import re
from pathlib import Path

import anthropic
from rich import print as rprint

from src.analyzers.frame_extractor import get_video_id
from src.analyzers.prompts import COMPARISON_SYSTEM_PROMPT, COMPARISON_USER_TEMPLATE
from src.utils.config import (
    ANTHROPIC_API_KEY,
    DATA_ANALYSIS_DIR,
    OUTPUT_DIR,
    VIDEOS_DIR,
    load_pipeline_config,
)


def _load_all_analyses() -> dict[str, dict]:
    """Load all analysis JSON files, keyed by video_id."""
    if not DATA_ANALYSIS_DIR.exists():
        return {}

    analyses = {}
    for f in sorted(DATA_ANALYSIS_DIR.glob("analysis_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict) and data.get("video_id"):
                    analyses[data["video_id"]] = data
        except (json.JSONDecodeError, OSError):
            continue

    return analyses


def _get_video_ids(directory: Path) -> set[str]:
    """Compute video_ids for all .mp4 files in a directory."""
    if not directory.exists():
        return set()
    return {get_video_id(f) for f in directory.glob("*.mp4")}


def load_scraped_analyses() -> list[dict]:
    """Load analyses for scraped videos (from videos/ directory)."""
    scraped_ids = _get_video_ids(VIDEOS_DIR)
    all_analyses = _load_all_analyses()
    return [a for vid, a in all_analyses.items() if vid in scraped_ids]


def load_rendered_analyses() -> list[dict]:
    """Load analyses for our rendered videos (from output/videos/ directory)."""
    rendered_ids = _get_video_ids(OUTPUT_DIR)
    all_analyses = _load_all_analyses()
    return [a for vid, a in all_analyses.items() if vid in rendered_ids]


def _summarize_set(analyses: list[dict], label: str) -> str:
    """Summarize a set of analyses into a compact text block."""
    if not analyses:
        return f"{label}: No analyses available."

    n = len(analyses)
    lines = [f"{label} ({n} videos):"]

    # Hook types
    hook_types = {}
    hook_durations = []
    for a in analyses:
        hook = a.get("hook", {})
        ht = hook.get("type", "unknown")
        hook_types[ht] = hook_types.get(ht, 0) + 1
        if hook.get("duration_s"):
            hook_durations.append(hook["duration_s"])

    if hook_types:
        types_str = ", ".join(f"{t}: {c}" for t, c in sorted(hook_types.items(), key=lambda x: -x[1]))
        lines.append(f"  Hook types: {types_str}")
    if hook_durations:
        lines.append(f"  Avg hook duration: {sum(hook_durations)/len(hook_durations):.1f}s")

    # Structure
    durations = [a.get("structure", {}).get("total_duration_s", 0) for a in analyses if a.get("structure", {}).get("total_duration_s")]
    cuts = [a.get("structure", {}).get("num_cuts", 0) for a in analyses if a.get("structure", {}).get("num_cuts")]
    avg_cut = [a.get("structure", {}).get("avg_cut_duration_s", 0) for a in analyses if a.get("structure", {}).get("avg_cut_duration_s")]

    if durations:
        lines.append(f"  Avg duration: {sum(durations)/len(durations):.1f}s")
    if cuts:
        lines.append(f"  Avg cuts per video: {sum(cuts)/len(cuts):.1f}")
    if avg_cut:
        lines.append(f"  Avg cut duration: {sum(avg_cut)/len(avg_cut):.1f}s")

    # Colors
    colors = set()
    accents = set()
    for a in analyses:
        palette = a.get("color_palette", {})
        if palette.get("dominant"):
            colors.add(palette["dominant"])
        if palette.get("accent"):
            accents.add(palette["accent"])
    if colors:
        lines.append(f"  Dominant colors: {', '.join(list(colors)[:5])}")
    if accents:
        lines.append(f"  Accent colors: {', '.join(list(accents)[:5])}")

    # Audio
    music_count = sum(1 for a in analyses if a.get("audio", {}).get("has_music"))
    vo_count = sum(1 for a in analyses if a.get("audio", {}).get("has_voiceover"))
    lines.append(f"  Music: {music_count}/{n}, Voiceover: {vo_count}/{n}")

    # Quality scores
    scores = [a.get("overall_quality_score", 0) for a in analyses if a.get("overall_quality_score")]
    if scores:
        lines.append(f"  Quality scores: avg {sum(scores)/len(scores):.0f}, range {min(scores)}-{max(scores)}")

    # Text overlays summary
    overlay_counts = [len(a.get("text_overlays", [])) for a in analyses]
    if overlay_counts:
        lines.append(f"  Avg text overlays: {sum(overlay_counts)/len(overlay_counts):.1f}")

    # CTA types
    cta_types = {}
    for a in analyses:
        ct = a.get("cta", {}).get("type", "")
        if ct:
            cta_types[ct] = cta_types.get(ct, 0) + 1
    if cta_types:
        types_str = ", ".join(f"{t}: {c}" for t, c in sorted(cta_types.items(), key=lambda x: -x[1]))
        lines.append(f"  CTA types: {types_str}")

    # Engagement factors
    factors = {}
    for a in analyses:
        for f in a.get("engagement_factors", []):
            factors[f] = factors.get(f, 0) + 1
    if factors:
        top = sorted(factors.items(), key=lambda x: -x[1])[:5]
        lines.append(f"  Top engagement factors: {', '.join(f[0] for f in top)}")

    return "\n".join(lines)


def compare_videos() -> dict | None:
    """
    Run a comparison between scraped TikTok videos and our rendered videos.

    Sends summaries of both analysis sets to Claude for a structured gap
    analysis with actionable improvement recommendations.

    Returns:
        Comparison report dict, or None on failure.
    """
    if not ANTHROPIC_API_KEY:
        rprint("[red]ANTHROPIC_API_KEY not set[/red]")
        return None

    scraped = load_scraped_analyses()
    rendered = load_rendered_analyses()

    if not scraped:
        rprint("[yellow]No scraped video analyses found. Run the analysis pipeline on scraped videos first.[/yellow]")
        return None

    if not rendered:
        rprint("[yellow]No rendered video analyses found. Render videos and analyze them first.[/yellow]")
        return None

    scraped_summary = _summarize_set(scraped, "SCRAPED TIKTOK VIDEOS (top performers)")
    rendered_summary = _summarize_set(rendered, "OUR RENDERED VIDEOS (factory output)")

    config = load_pipeline_config()
    niche = config.get("niche", "general")
    model = config.get("analyzer", {}).get("synthesis_model", "claude-sonnet-4-20250514")

    user_prompt = COMPARISON_USER_TEMPLATE.format(
        niche=niche,
        scraped_summary=scraped_summary,
        rendered_summary=rendered_summary,
        num_scraped=len(scraped),
        num_rendered=len(rendered),
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        rprint(f"[blue]Comparing {len(scraped)} scraped vs {len(rendered)} rendered videos (model: {model})...[/blue]")
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=COMPARISON_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as e:
        rprint(f"[red]Claude API error: {e}[/red]")
        return None

    raw_text = response.content[0].text
    usage = response.usage
    rprint(f"[dim]Tokens -- input: {usage.input_tokens}, output: {usage.output_tokens}[/dim]")

    # Parse JSON
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    try:
        report = json.loads(text)
    except json.JSONDecodeError as e:
        rprint(f"[red]Failed to parse comparison JSON: {e}[/red]")
        return None

    # Save report
    _save_comparison_report(report)

    rprint(f"[bold green]Comparison report generated with {len(report.get('gaps', []))} gaps identified[/bold green]")
    return report


def _save_comparison_report(report: dict) -> None:
    """Save comparison report as JSON and Markdown."""
    DATA_ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = DATA_ANALYSIS_DIR / "comparison_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    rprint(f"[green]Saved:[/green] {json_path}")

    md_path = DATA_ANALYSIS_DIR / "comparison_report.md"
    md = _report_to_markdown(report)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    rprint(f"[green]Saved:[/green] {md_path}")


def _report_to_markdown(report: dict) -> str:
    """Convert comparison report to readable Markdown."""
    lines = [
        "# Video Comparison Report",
        f"\nScraped: {report.get('num_scraped', '?')} videos | "
        f"Rendered: {report.get('num_rendered', '?')} videos\n",
        f"**Overall verdict:** {report.get('overall_verdict', 'N/A')}\n",
    ]

    # Quality comparison
    quality = report.get("quality_comparison", {})
    if quality:
        lines.append("## Quality Scores")
        lines.append(f"- Scraped average: {quality.get('scraped_avg', '?')}")
        lines.append(f"- Rendered average: {quality.get('rendered_avg', '?')}")
        lines.append(f"- Gap: {quality.get('gap', '?')} points")
        lines.append("")

    # Gaps
    gaps = report.get("gaps", [])
    if gaps:
        lines.append("## Key Gaps")
        for gap in gaps:
            lines.append(f"\n### {gap.get('category', 'Unknown')}")
            lines.append(f"**Issue:** {gap.get('issue', '')}")
            lines.append(f"- Scraped: {gap.get('scraped_value', '')}")
            lines.append(f"- Rendered: {gap.get('rendered_value', '')}")
            lines.append(f"- **Impact:** {gap.get('impact', '')}")
            lines.append(f"- **Fix:** {gap.get('fix', '')}")
        lines.append("")

    # Priorities
    priorities = report.get("priority_fixes", [])
    if priorities:
        lines.append("## Priority Fixes (in order)")
        for i, fix in enumerate(priorities, 1):
            lines.append(f"{i}. {fix}")
        lines.append("")

    return "\n".join(lines)


def load_comparison_report() -> dict | None:
    """Load the latest comparison report if it exists."""
    json_path = DATA_ANALYSIS_DIR / "comparison_report.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
