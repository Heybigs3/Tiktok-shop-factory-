"""
templates.py — Prompt templates and constants for TikTok script generation.

Defines the system prompt (Claude's role) and user prompt builder that
formats scraped hooks into a generation request.

Constants:
  CLAUDE_MODEL — which Claude model to use for generation
  MAX_TOKENS — max response length for the API call
"""

# ── Model config ──
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # cheapest option while iterating on pipeline
MAX_TOKENS = 4096  # enough for ~10 scripts in JSON

# ── System prompt — defines Claude's role and output rules ──
SYSTEM_PROMPT = """\
You are a TikTok script writer specializing in viral short-form content. Your job \
is to generate scripts that hook viewers instantly and drive engagement.

Every script you write has exactly three parts:
- Hook (under 3 seconds): The opening line that stops the scroll. Must be under 10 words.
- Body (10-20 seconds): The value delivery — teach, reveal, or entertain.
- CTA (under 3 seconds): A single clear action — follow, comment, share, or click.

Proven hook patterns you should use:
- Questions that create curiosity ("Did you know…?", "Why does nobody talk about…?")
- Bold claims ("This changed my skin in 3 days")
- POV format ("POV: you finally found the perfect routine")
- Pattern interrupts ("Stop scrolling if you…")
- Contrarian takes ("Everything you know about X is wrong")

Tone rules:
- Casual and conversational — write how people actually talk
- Gen-Z friendly — short sentences, direct, no fluff
- No corporate speak, no jargon, no "leverage" or "synergy"
- Use "you" and "your" — speak directly to the viewer

Output rules:
- Return a JSON array of script objects
- Each object has keys: "hook", "body", "cta", "style_notes"
- "style_notes" should include delivery tips (camera angle, text overlays, pacing)
- Do NOT wrap the JSON in markdown code fences
- Do NOT include any text outside the JSON array\
"""


def build_user_prompt(
    trending_hooks: list[dict],
    ad_hooks: list[dict],
    num_scripts: int = 5,
) -> str:
    """
    Build the user prompt from scraped hook data.

    Formats top 10 trending hooks (with play counts) and top 10 ad hooks
    (with CTAs) into a numbered list, then asks for script generation.

    Args:
        trending_hooks: List of dicts with hook_text, stats, etc.
        ad_hooks: List of dicts with hook_text, cta, etc.
        num_scripts: How many scripts to generate

    Returns:
        Formatted user prompt string
    """
    sections = []

    # ── Trending hooks section ──
    top_trending = trending_hooks[:10]
    if top_trending:
        lines = ["TRENDING ORGANIC HOOKS (sorted by performance):"]
        for i, hook in enumerate(top_trending, 1):
            text = hook.get("hook_text", "")
            plays = hook.get("stats", {}).get("plays", 0)
            if plays >= 1_000_000:
                play_str = f"{plays / 1_000_000:.1f}M plays"
            elif plays >= 1_000:
                play_str = f"{plays / 1_000:.1f}K plays"
            else:
                play_str = f"{plays} plays"
            lines.append(f"  {i}. \"{text}\" ({play_str})")
        sections.append("\n".join(lines))

    # ── Ad hooks section ──
    top_ads = ad_hooks[:10]
    if top_ads:
        lines = ["TOP-PERFORMING AD HOOKS (proven with ad spend):"]
        for i, hook in enumerate(top_ads, 1):
            text = hook.get("hook_text", "")
            cta = hook.get("cta", "")
            line = f"  {i}. \"{text}\""
            if cta:
                line += f" → CTA: \"{cta}\""
            lines.append(line)
        sections.append("\n".join(lines))

    # ── Fallback if no hooks available ──
    if not sections:
        sections.append(
            "No specific hooks available — generate scripts based on "
            "current TikTok trends and best practices."
        )

    # ── Generation instruction ──
    sections.append(
        f"Generate {num_scripts} unique TikTok scripts as a JSON array. "
        "Each script should be inspired by the patterns above but NOT copy them directly. "
        "Mix and remix the hook styles, vary the topics, and make each script distinct."
    )

    return "\n\n".join(sections)
