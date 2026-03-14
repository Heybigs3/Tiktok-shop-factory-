"""
style_overrides.py — Closes the feedback loop between analysis and rendering.

Reads the comparison report + Style Bible and produces concrete parameter
overrides that the renderer and script generator consume automatically.

This is the bridge between "knowing what's wrong" and "fixing it."

Usage:
    from src.analyzers.style_overrides import get_render_overrides, get_prompt_overrides
    overrides = get_render_overrides()   # dict of renderer parameters
    prompt_ctx = get_prompt_overrides()  # string to inject into generation prompt
"""

import json
from pathlib import Path

from src.utils.config import DATA_ANALYSIS_DIR, DATA_STYLE_BIBLES_DIR, load_pipeline_config


def _load_comparison_report() -> dict | None:
    """Load comparison_report.json if it exists."""
    path = DATA_ANALYSIS_DIR / "comparison_report.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_style_bible() -> dict | None:
    """Load the Style Bible JSON for the current niche."""
    config = load_pipeline_config()
    niche = config.get("analyzer", {}).get("style_bible_niche", config.get("niche", "general"))
    path = DATA_STYLE_BIBLES_DIR / f"{niche}_style_bible.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _extract_color_overrides(report: dict | None, bible: dict | None) -> dict:
    """Extract color recommendations from analysis data.

    Returns a dict with 'bg', 'text', 'accent' hex values (0x-prefixed for FFmpeg).
    """
    colors = {}

    # Prefer comparison report gaps (most actionable)
    if report:
        for gap in report.get("gaps", []):
            category = gap.get("category", "").lower()
            if "color" in category or "palette" in category:
                fix = gap.get("fix", "")
                scraped = gap.get("scraped_value", "")
                # Extract hex colors from the scraped_value or fix text
                import re
                hex_colors = re.findall(r"#([0-9a-fA-F]{6})", f"{scraped} {fix}")
                if len(hex_colors) >= 1:
                    colors["bg"] = f"0x{hex_colors[0]}"
                if len(hex_colors) >= 2:
                    colors["accent"] = f"0x{hex_colors[1]}"
                break

    # Fall back to Style Bible visual recommendations
    if not colors and bible:
        visual = bible.get("visual_style", {})
        dominant = visual.get("dominant_colors", [])
        accent = visual.get("accent_colors", [])
        if dominant:
            # Convert #hex to 0xhex for FFmpeg
            c = dominant[0].lstrip("#")
            if len(c) == 6:
                colors["bg"] = f"0x{c}"
        if accent:
            c = accent[0].lstrip("#")
            if len(c) == 6:
                colors["accent"] = f"0x{c}"

    # Default text to white if we have a bg override
    if colors.get("bg") and "text" not in colors:
        colors["text"] = "0xffffff"

    return colors


def _extract_timing_overrides(report: dict | None, bible: dict | None) -> dict:
    """Extract timing recommendations: target duration, hook length, cut frequency."""
    timing = {}

    if report:
        for gap in report.get("gaps", []):
            category = gap.get("category", "").lower()
            fix = gap.get("fix", "")
            scraped = gap.get("scraped_value", "")

            if "hook" in category and "strength" in category:
                # Extract target hook duration from fix text
                # Prefer range like "2-3s" (take the lower bound) over single "3s"
                import re
                range_match = re.findall(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*s", fix)
                if range_match:
                    timing["target_hook_duration"] = float(range_match[0][0])
                else:
                    nums = re.findall(r"(\d+(?:\.\d+)?)\s*(?:s|sec)", fix)
                    if nums:
                        timing["target_hook_duration"] = float(nums[0])

            if "length" in category or "duration" in category:
                # Extract target video duration
                import re
                nums = re.findall(r"(\d+)-(\d+)\s*(?:s|sec)", fix)
                if nums:
                    timing["target_min_duration"] = int(nums[0][0])
                    timing["target_max_duration"] = int(nums[0][1])
                elif "scraped" in scraped.lower() or any(c.isdigit() for c in scraped):
                    nums = re.findall(r"(\d+(?:\.\d+)?)\s*s", scraped)
                    if nums:
                        timing["target_min_duration"] = int(float(nums[0]) * 0.8)
                        timing["target_max_duration"] = int(float(nums[0]) * 1.1)

            if "dynamism" in category or "cut" in category:
                import re
                # Match "15+ cuts", "15+ per video", "15 cuts" etc.
                nums = re.findall(r"(\d+)\+?\s*(?:cuts|cut|per video)", fix)
                if nums:
                    timing["target_cuts"] = int(nums[0])
                # Match "3-5s per cut", "3-5s each", "3-5s duration"
                cut_dur = re.findall(r"(\d+)-(\d+)\s*s\s*(?:per cut|each|duration|maximum)", fix)
                if cut_dur:
                    timing["target_cut_duration"] = float(cut_dur[0][0])

    # Fall back to Style Bible
    if not timing and bible:
        structure = bible.get("structure_patterns", {})
        if structure.get("avg_duration_s"):
            dur = structure["avg_duration_s"]
            timing["target_min_duration"] = int(dur * 0.8)
            timing["target_max_duration"] = int(dur * 1.1)

        hooks = bible.get("hook_patterns", {})
        if hooks.get("avg_duration_s"):
            timing["target_hook_duration"] = hooks["avg_duration_s"]

    return timing


def _extract_content_overrides(report: dict | None) -> dict:
    """Extract content recommendations: music, text overlays, CTA types."""
    content = {}

    if not report:
        return content

    for gap in report.get("gaps", []):
        category = gap.get("category", "").lower()
        fix = gap.get("fix", "")

        if "audio" in category or "music" in category:
            content["music_recommended"] = True

        if "text overlay" in category or "overlay" in category:
            import re
            nums = re.findall(r"(\d+)\+?\s*(?:per video|text overlay)", fix)
            if nums:
                content["target_text_overlays"] = int(nums[0])

        if "cta" in category:
            content["cta_recommendation"] = fix

    return content


def get_render_overrides() -> dict:
    """Get concrete renderer parameter overrides from analysis data.

    Returns a dict that the renderer can apply on top of its defaults:
    {
        "colors": {"bg": "0x8B7355", "text": "0xffffff", "accent": "0x22c85c"},
        "timing": {
            "target_hook_duration": 2.5,
            "target_min_duration": 55,
            "target_max_duration": 75,
            "target_cuts": 15,
            "target_cut_duration": 4.0,
        },
        "content": {
            "music_recommended": True,
            "target_text_overlays": 8,
            "cta_recommendation": "Use specific CTAs...",
        },
        "source": "comparison_report"  # or "style_bible" or "none"
    }
    """
    report = _load_comparison_report()
    bible = _load_style_bible()

    if not report and not bible:
        return {"source": "none"}

    overrides = {
        "colors": _extract_color_overrides(report, bible),
        "timing": _extract_timing_overrides(report, bible),
        "content": _extract_content_overrides(report),
        "source": "comparison_report" if report else "style_bible",
    }

    return overrides


def get_prompt_overrides() -> str | None:
    """Get a prompt section from comparison data to inject into script generation.

    This tells Claude what specific gaps to fix when writing new scripts, so the
    next batch directly addresses the comparison findings.

    Returns a formatted string, or None if no comparison data exists.
    """
    report = _load_comparison_report()
    if not report:
        return None

    gaps = report.get("gaps", [])
    priorities = report.get("priority_fixes", [])
    verdict = report.get("overall_verdict", "")

    if not gaps and not priorities:
        return None

    lines = [
        "## Video Comparison Intelligence (IMPORTANT — read carefully)",
        f"Our previous videos were compared against top-performing TikTok content.",
        f"Verdict: {verdict}" if verdict else "",
        "",
        "The following gaps were identified. Your scripts MUST address these:",
    ]

    for gap in gaps[:5]:
        category = gap.get("category", "")
        issue = gap.get("issue", "")
        fix = gap.get("fix", "")
        lines.append(f"- **{category}**: {issue}")
        if fix:
            lines.append(f"  FIX: {fix}")

    if priorities:
        lines.append("")
        lines.append("Priority fixes (in order of importance):")
        for i, fix in enumerate(priorities[:5], 1):
            lines.append(f"  {i}. {fix}")

    # Specific script-level instructions derived from common gaps
    lines.append("")
    lines.append("Script-level instructions based on analysis:")

    for gap in gaps:
        cat = gap.get("category", "").lower()
        fix = gap.get("fix", "")
        if "hook" in cat:
            lines.append("- Write shorter, punchier hooks (under 3 seconds to read aloud)")
            lines.append("- Vary hook types: use listicles, before/after, pattern interrupts — NOT just price anchoring")
        elif "length" in cat or "duration" in cat:
            lines.append("- Write LONGER body sections — aim for 60-75 seconds total when read aloud")
            lines.append("- Include multiple sub-points, demonstrations, or story beats in the body")
        elif "cta" in cat:
            lines.append(f"- {fix}")
        elif "content type" in cat or "diversity" in cat:
            lines.append("- Include before/after language, step-by-step demonstrations, routine walkthroughs")

    return "\n".join(line for line in lines if line is not None)
