"""
style_bible.py — Synthesize per-video analyses into a Style Bible.

Aggregates patterns across all analyzed videos and sends to Claude
for synthesis into an actionable creative reference document.

Usage:
  python -m src.analyzers  # menu option 4
"""

import json
import re
from collections import Counter
from pathlib import Path

import anthropic
from rich import print as rprint

from src.analyzers.prompts import STYLE_BIBLE_SYSTEM_PROMPT, STYLE_BIBLE_USER_TEMPLATE
from src.utils.config import ANTHROPIC_API_KEY, DATA_ANALYSIS_DIR, DATA_STYLE_BIBLES_DIR, load_pipeline_config


def _load_analyses() -> list[dict]:
    """Load all analysis JSON files from data/analysis/."""
    if not DATA_ANALYSIS_DIR.exists():
        return []

    analyses = []
    for f in sorted(DATA_ANALYSIS_DIR.glob("analysis_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    analyses.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return analyses


def _aggregate_stats(analyses: list[dict]) -> str:
    """Compute aggregated statistics across all video analyses."""
    if not analyses:
        return "No analyses available."

    sections = []
    n = len(analyses)

    # Hook types distribution
    hook_types: Counter[str] = Counter()
    hook_durations = []
    for a in analyses:
        hook = a.get("hook", {})
        if hook.get("type"):
            hook_types[hook["type"]] += 1
        if hook.get("duration_s"):
            hook_durations.append(hook["duration_s"])

    if hook_types:
        lines = ["Hook Type Distribution:"]
        for htype, count in hook_types.most_common():
            lines.append(f"  {htype}: {count}/{n} ({count/n*100:.0f}%)")
        if hook_durations:
            avg_dur = sum(hook_durations) / len(hook_durations)
            lines.append(f"  Average hook duration: {avg_dur:.1f}s")
        sections.append("\n".join(lines))

    # Structure stats
    durations = [a.get("structure", {}).get("total_duration_s", 0) for a in analyses if a.get("structure", {}).get("total_duration_s")]
    cuts = [a.get("structure", {}).get("num_cuts", 0) for a in analyses if a.get("structure", {}).get("num_cuts")]
    if durations:
        sections.append(
            f"Video Structure:\n"
            f"  Avg duration: {sum(durations)/len(durations):.1f}s\n"
            f"  Avg cuts: {sum(cuts)/len(cuts):.1f}" if cuts else ""
        )

    # Color palettes
    dominant_colors: Counter[str] = Counter()
    accent_colors: Counter[str] = Counter()
    for a in analyses:
        palette = a.get("color_palette", {})
        if palette.get("dominant"):
            dominant_colors[palette["dominant"]] += 1
        if palette.get("accent"):
            accent_colors[palette["accent"]] += 1

    if dominant_colors:
        lines = ["Color Palettes:"]
        lines.append(f"  Top dominant: {', '.join(c for c, _ in dominant_colors.most_common(5))}")
        lines.append(f"  Top accent: {', '.join(c for c, _ in accent_colors.most_common(5))}")
        sections.append("\n".join(lines))

    # Audio patterns
    music_count = sum(1 for a in analyses if a.get("audio", {}).get("has_music"))
    vo_count = sum(1 for a in analyses if a.get("audio", {}).get("has_voiceover"))
    energy_patterns: Counter[str] = Counter()
    for a in analyses:
        ep = a.get("audio", {}).get("energy_pattern", "")
        if ep:
            energy_patterns[ep] += 1

    sections.append(
        f"Audio:\n"
        f"  Music: {music_count}/{n} ({music_count/n*100:.0f}%)\n"
        f"  Voiceover: {vo_count}/{n} ({vo_count/n*100:.0f}%)"
    )

    # CTA types
    cta_types: Counter[str] = Counter()
    cta_positions: Counter[str] = Counter()
    for a in analyses:
        cta = a.get("cta", {})
        if cta.get("type"):
            cta_types[cta["type"]] += 1
        if cta.get("position"):
            cta_positions[cta["position"]] += 1

    if cta_types:
        lines = ["CTA Patterns:"]
        for ctype, count in cta_types.most_common():
            lines.append(f"  {ctype}: {count}/{n}")
        sections.append("\n".join(lines))

    # Engagement factors
    factors: Counter[str] = Counter()
    for a in analyses:
        for f in a.get("engagement_factors", []):
            factors[f] += 1

    if factors:
        lines = ["Engagement Factors:"]
        for factor, count in factors.most_common(10):
            lines.append(f"  {factor}: {count}/{n} ({count/n*100:.0f}%)")
        sections.append("\n".join(lines))

    # Quality scores
    scores = [a.get("overall_quality_score", 0) for a in analyses if a.get("overall_quality_score")]
    if scores:
        sections.append(
            f"Quality Scores:\n"
            f"  Average: {sum(scores)/len(scores):.0f}\n"
            f"  Range: {min(scores)}-{max(scores)}"
        )

    return "\n\n".join(sections)


def generate_style_bible(analyses: list[dict] | None = None, niche: str | None = None) -> dict | None:
    """
    Synthesize all per-video analyses into a Style Bible.

    Args:
        analyses: List of analysis dicts. If None, loads from data/analysis/.
        niche: Target niche. If None, reads from pipeline_config.json.

    Returns:
        Style Bible dict, or None on failure.
    """
    if not ANTHROPIC_API_KEY:
        rprint("[red]ANTHROPIC_API_KEY not set — cannot generate Style Bible[/red]")
        return None

    if analyses is None:
        analyses = _load_analyses()

    if not analyses:
        rprint("[yellow]No video analyses found — run video analysis first[/yellow]")
        return None

    config = load_pipeline_config()
    if niche is None:
        niche = config.get("analyzer", {}).get("style_bible_niche", config.get("niche", "general"))
    model = config.get("analyzer", {}).get("synthesis_model", "claude-sonnet-4-5-20250514")

    aggregated = _aggregate_stats(analyses)
    user_prompt = STYLE_BIBLE_USER_TEMPLATE.format(
        niche=niche,
        num_videos=len(analyses),
        aggregated_stats=aggregated,
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        rprint(f"[blue]Generating Style Bible for '{niche}' ({len(analyses)} analyses, model: {model})…[/blue]")
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=STYLE_BIBLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as e:
        rprint(f"[red]Claude API error: {e}[/red]")
        return None

    raw_text = response.content[0].text
    usage = response.usage
    rprint(f"[dim]Tokens — input: {usage.input_tokens}, output: {usage.output_tokens}[/dim]")

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
        style_bible = json.loads(text)
    except json.JSONDecodeError as e:
        rprint(f"[red]Failed to parse Style Bible JSON: {e}[/red]")
        return None

    # Save both JSON and human-readable markdown
    _save_style_bible(style_bible, niche)

    return style_bible


def _save_style_bible(style_bible: dict, niche: str) -> None:
    """Save Style Bible as both JSON and Markdown."""
    DATA_STYLE_BIBLES_DIR.mkdir(parents=True, exist_ok=True)

    # JSON version (machine-readable for script generator)
    json_path = DATA_STYLE_BIBLES_DIR / f"{niche}_style_bible.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(style_bible, f, indent=2, ensure_ascii=False)
    rprint(f"[green]Saved:[/green] {json_path}")

    # Markdown version (human-readable reference)
    md_path = DATA_STYLE_BIBLES_DIR / f"{niche}_style_bible.md"
    md = _style_bible_to_markdown(style_bible, niche)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    rprint(f"[green]Saved:[/green] {md_path}")


def _style_bible_to_markdown(sb: dict, niche: str) -> str:
    """Convert a Style Bible dict to a readable Markdown document."""
    lines = [
        f"# Style Bible — {niche.title()}",
        f"\nBased on {sb.get('num_videos_analyzed', '?')} analyzed videos.\n",
    ]

    # Hook patterns
    hooks = sb.get("hook_patterns", {})
    if hooks:
        lines.append("## Hook Patterns")
        lines.append(f"- Average duration: {hooks.get('avg_duration_s', '?')}s")
        for ht in hooks.get("top_types", []):
            lines.append(f"- **{ht['type']}**: {ht.get('frequency_pct', 0):.0f}% of videos")
        for bp in hooks.get("best_practices", []):
            lines.append(f"- {bp}")
        lines.append("")

    # Visual style
    visual = sb.get("visual_style", {})
    if visual:
        lines.append("## Visual Style")
        if visual.get("dominant_colors"):
            lines.append(f"- Dominant colors: {', '.join(visual['dominant_colors'])}")
        if visual.get("accent_colors"):
            lines.append(f"- Accent colors: {', '.join(visual['accent_colors'])}")
        if visual.get("font_size_preference"):
            lines.append(f"- Font size: {visual['font_size_preference']}")
        lines.append("")

    # CTA patterns
    cta = sb.get("cta_patterns", {})
    if cta:
        lines.append("## CTA Patterns")
        for ct in cta.get("top_types", []):
            lines.append(f"- **{ct['type']}**: {ct.get('frequency_pct', 0):.0f}%")
        lines.append("")

    # Top recommendations
    recs = sb.get("top_recommendations", [])
    if recs:
        lines.append("## Top Recommendations")
        for rec in recs:
            lines.append(f"1. {rec}")
        lines.append("")

    return "\n".join(lines)


def load_style_bible(niche: str | None = None) -> str | None:
    """
    Load an existing Style Bible for use by the script generator.

    Args:
        niche: Target niche. If None, reads from pipeline_config.json.

    Returns:
        Style Bible content as a formatted string for injection into prompts,
        or None if no Style Bible exists.
    """
    config = load_pipeline_config()
    if niche is None:
        niche = config.get("analyzer", {}).get("style_bible_niche", config.get("niche", "general"))

    json_path = DATA_STYLE_BIBLES_DIR / f"{niche}_style_bible.json"
    if not json_path.exists():
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            sb = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Format as a concise prompt section
    parts = []

    hooks = sb.get("hook_patterns", {})
    if hooks.get("top_types"):
        top = hooks["top_types"][:3]
        types_str = ", ".join(f"{t['type']} ({t.get('frequency_pct', 0):.0f}%)" for t in top)
        parts.append(f"Top hook types: {types_str}")
        if hooks.get("avg_duration_s"):
            parts.append(f"Avg hook duration: {hooks['avg_duration_s']}s")

    visual = sb.get("visual_style", {})
    if visual.get("dominant_colors"):
        parts.append(f"Dominant colors: {', '.join(visual['dominant_colors'][:3])}")
    if visual.get("font_size_preference"):
        parts.append(f"Font size: {visual['font_size_preference']}")

    structure = sb.get("structure_patterns", {})
    if structure.get("avg_duration_s"):
        parts.append(f"Avg video duration: {structure['avg_duration_s']}s")
    if structure.get("pacing_notes"):
        parts.append(f"Pacing: {structure['pacing_notes']}")

    factors = sb.get("engagement_factors", [])
    if factors:
        top_factors = [f["factor"] for f in factors[:5]]
        parts.append(f"Top engagement factors: {', '.join(top_factors)}")

    recs = sb.get("top_recommendations", [])
    if recs:
        parts.append("Key recommendations:\n" + "\n".join(f"- {r}" for r in recs[:5]))

    if not parts:
        return None

    return "\n".join(parts)
