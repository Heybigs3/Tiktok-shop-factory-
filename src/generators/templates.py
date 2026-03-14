"""
templates.py — Prompt templates and constants for TikTok script generation.

Defines the system prompt (Claude's role) and user prompt builder that
formats scraped hooks into a generation request.

Constants:
  CLAUDE_MODEL — which Claude model to use for generation
  MAX_TOKENS — max response length for the API call
"""

from collections import Counter

# ── Model config ──
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # cheapest option while iterating on pipeline
MAX_TOKENS = 4096  # enough for ~10 scripts in JSON

# ── System prompt — defines Claude's role and output rules ──
SYSTEM_PROMPT = """\
You are a TikTok script writer specializing in viral short-form content. Your job \
is to generate scripts that hook viewers instantly and drive engagement.

Every script you write has exactly three parts:
- Hook: The opening line that stops the scroll. Must be under 10 words. Keep it punchy — top performers average 2-3 seconds.
- Body: The value delivery section. Length should match what works in this niche (see Style Intelligence below if available). Teach, reveal, or entertain.
- CTA: A single clear action — follow, comment, share, or click.

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

Data-driven rules:
- Study the full captions provided — match the body structure and pacing of top performers
- Use hashtags that actually appear on high-performing videos, not generic ones
- If trending sounds are listed, reference them in style_notes where relevant
- Verified creators with large followings have proven formats — lean into their patterns
- High share count = content people forward to friends (relatable/surprising)
- High comment count = content that sparks debate or questions (opinion/controversial)

Output rules:
- Return a JSON array of script objects
- Each object has keys: "hook", "body", "cta", "style_notes", "suggested_hashtags", "visual_hints"
- "style_notes" should include delivery tips (camera angle, text overlays, pacing, sound suggestion)
- "suggested_hashtags" is a list of 3-5 hashtags (without #) relevant to the script — prefer hashtags seen on top-performing videos
- "visual_hints" is an object with:
  - "mood": one of "warm", "cool", "energetic", "calm"
  - "key_overlay_text": a short stat or phrase to display as a text overlay (e.g. "40% more absorption")
  - "background_style": one of "gradient", "solid"
  - "target_duration_sec": intended total video duration in seconds (based on Style Intelligence if available, otherwise your best estimate for TikTok engagement)
- Do NOT wrap the JSON in markdown code fences
- Do NOT include any text outside the JSON array\
"""

# ── Product video system prompt — optimized for TikTok Shop purchase-driving scripts ──
PRODUCT_SYSTEM_PROMPT = """\
You are a TikTok Shop script writer specializing in product videos that drive purchases. \
Your scripts are designed for product showcase videos with real product visuals.

Every script you write has exactly three parts:
- Hook: Stop the scroll with a product-focused opener. Under 10 words. Keep it punchy — top performers average 2-3 seconds.
- Body: Demonstrate value — show benefits, social proof, price anchoring. Length should match what works in this niche (see Style Intelligence below if available).
- CTA: Drive to TikTok Shop — "Link in bio", "TikTok Shop", "Add to cart".

Proven product hook patterns:
- Price anchoring: "Was $49, now only $12"
- Social proof: "4.8 stars from 12K reviews"
- Urgency: "Only 3 left at this price"
- UGC discovery: "I found this on TikTok Shop and..."
- Problem-solution: "Struggling with [problem]? This fixed it"
- Comparison: "I tried the $80 version and the $12 version..."

Body rules:
- Lead with the strongest benefit, not features
- Include at least one social proof element (reviews, sales count, creator endorsement)
- Show price comparison or value proposition
- Keep it conversational — UGC style, not infomercial

Tone rules:
- Casual and conversational — write how people actually talk
- Gen-Z friendly — short sentences, direct, no fluff
- UGC authentic — "I found this" not "This product offers"
- Use "you" and "your" — speak directly to the viewer

Output rules:
- Return a JSON array of script objects
- Each object has keys: "hook", "body", "cta", "style_notes", "suggested_hashtags", "visual_hints", "product_id"
- "product_id": echo back the [ID: ...] value from the product list for the product this script is about
- "style_notes" should include delivery tips and product display guidance
- "suggested_hashtags" is a list of 3-5 hashtags (without #) — always include "aigc" and "tiktokshop", plus product-relevant tags
- "visual_hints" is an object with:
  - "mood": one of "warm", "cool", "energetic", "calm"
  - "key_overlay_text": price or key stat to display (e.g. "$12.99", "4.8★ 12K reviews")
  - "background_style": one of "gradient", "solid"
  - "video_style": one of "product_showcase", "ugc_showcase", "comparison", "screen_recording", "ugc_avatar"
  - "price_display": formatted price string (e.g. "$12.99")
  - "rating_display": formatted rating string (e.g. "4.8★ (12K)")
  - "target_duration_sec": intended total video duration in seconds (based on Style Intelligence if available, otherwise your best estimate for TikTok engagement)
- Do NOT wrap the JSON in markdown code fences
- Do NOT include any text outside the JSON array\
"""


def _fmt_number(n: int) -> str:
    """Format a large number as 1.2M, 3.5K, etc."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _build_trending_section(trending_hooks: list[dict]) -> list[str]:
    """Build the trending hooks section lines for the prompt."""
    top = trending_hooks[:10]
    if not top:
        return []

    lines = ["TRENDING ORGANIC HOOKS (sorted by performance):"]
    for i, hook in enumerate(top, 1):
        # Backward-compatible: handle both processed and raw formats
        text = hook.get("hook_text") or (hook.get("text", "") or hook.get("description", ""))[:100]
        plays = hook.get("stats", {}).get("plays", 0) or hook.get("playCount", 0) or hook.get("plays", 0)

        # Build metadata parts
        parts = [f"{_fmt_number(plays)} plays"]

        engagement = hook.get("stats", {}).get("engagement_rate", 0)
        if engagement:
            parts.append(f"{engagement * 100:.1f}% eng")

        shares = hook.get("stats", {}).get("shares", 0)
        if shares:
            parts.append(f"{_fmt_number(shares)} shares")

        comments = hook.get("stats", {}).get("comments", 0)
        if comments:
            parts.append(f"{_fmt_number(comments)} comments")

        duration = hook.get("video_duration_sec", 0)
        if duration:
            parts.append(f"{duration}s")

        # Author info with verified badge
        author = hook.get("author", "")
        author_fans = hook.get("author_fans", 0)
        verified = hook.get("author_verified", False)
        if author:
            author_str = f"@{author}"
            if verified:
                author_str += " \u2713"
            if author_fans:
                author_str += f" [{_fmt_number(author_fans)} fans]"
            parts.append(author_str)

        meta = ", ".join(parts)
        lines.append(f"  {i}. \"{text}\" ({meta})")

    return lines


def _build_captions_section(trending_hooks: list[dict]) -> list[str]:
    """Build the full captions section — shows body structure of top performers."""
    # Only include hooks that have full_text longer than the hook itself
    captions = []
    for hook in trending_hooks[:10]:
        full = hook.get("full_text", "")
        hook_text = hook.get("hook_text", "")
        if full and len(full) > len(hook_text) + 20:
            plays = hook.get("stats", {}).get("plays", 0)
            captions.append((full, plays))

    if not captions:
        return []

    # Show top 5 captions
    lines = ["FULL CAPTIONS FROM TOP VIDEOS (study the body structure and pacing):"]
    for i, (text, plays) in enumerate(captions[:5], 1):
        # Truncate very long captions
        display = text[:300] + "..." if len(text) > 300 else text
        lines.append(f"  {i}. [{_fmt_number(plays)} plays] \"{display}\"")

    return lines


def _build_hashtag_analysis(trending_hooks: list[dict]) -> list[str]:
    """Aggregate hashtags from top-performing videos to show what winners actually tag."""
    tag_counter: Counter[str] = Counter()
    for hook in trending_hooks:
        for tag in hook.get("hashtags", []):
            # Handle both string tags and dict tags (raw Apify format)
            if isinstance(tag, dict):
                tag = tag.get("name", "") or tag.get("hashtag", "")
            if tag:
                tag_counter[str(tag).lower()] += 1

    if not tag_counter:
        return []

    # Show tags that appear on 2+ videos, or top 10
    common = tag_counter.most_common(10)
    lines = ["HASHTAGS USED BY TOP VIDEOS (frequency across scraped results):"]
    for tag, count in common:
        lines.append(f"  #{tag} (used by {count} video{'s' if count > 1 else ''})")

    return lines


def _build_sounds_section(trending_hooks: list[dict]) -> list[str]:
    """Extract trending sounds/music from top-performing videos."""
    sounds: Counter[str] = Counter()
    for hook in trending_hooks:
        music = hook.get("music", "")
        if music and music.lower() not in ("original sound", "original audio", ""):
            sounds[music] += 1

    if not sounds:
        return []

    lines = ["TRENDING SOUNDS (reference in style_notes if relevant):"]
    for sound, count in sounds.most_common(5):
        lines.append(f"  \"{sound}\" (used by {count} video{'s' if count > 1 else ''})")

    return lines


def _build_ads_section(ad_hooks: list[dict]) -> list[str]:
    """Build the ad hooks section lines for the prompt."""
    top = ad_hooks[:10]
    if not top:
        return []

    lines = ["TOP-PERFORMING AD HOOKS (proven with ad spend):"]
    for i, hook in enumerate(top, 1):
        # Backward-compatible: handle both processed and raw formats
        text = hook.get("hook_text") or (hook.get("text", "") or hook.get("adText", ""))[:100]
        cta = hook.get("cta_text", "") or hook.get("cta", "")

        parts = []
        spend = hook.get("estimated_spend", 0)
        if spend:
            parts.append(f"${_fmt_number(spend)} spend")

        advertiser = hook.get("advertiser", "")
        if advertiser:
            parts.append(advertiser)

        line = f"  {i}. \"{text}\""
        if parts:
            line += f" ({', '.join(parts)})"
        if cta:
            line += f" \u2192 CTA: \"{cta}\""

        # Show full ad text if longer than hook (body structure for ads)
        full = hook.get("full_text", "")
        if full and len(full) > len(text) + 20:
            display = full[:200] + "..." if len(full) > 200 else full
            line += f"\n     Full: \"{display}\""

        lines.append(line)

    return lines


def _build_global_hashtags_section(trending_hashtags: list[dict] | None) -> list[str]:
    """Build the trending hashtags section from the hashtag scraper."""
    if not trending_hashtags:
        return []

    lines = ["TRENDING HASHTAGS (use these in suggested_hashtags):"]
    for tag in trending_hashtags[:15]:
        name = tag.get("name", "") or tag.get("hashtag", "")
        views = tag.get("viewCount", 0) or tag.get("views", 0)
        if views >= 1_000_000_000:
            view_str = f"{views / 1_000_000_000:.1f}B views"
        elif views >= 1_000_000:
            view_str = f"{views / 1_000_000:.1f}M views"
        elif views >= 1_000:
            view_str = f"{views / 1_000:.1f}K views"
        else:
            view_str = f"{views} views"
        lines.append(f"  #{name} ({view_str})")

    return lines


def build_user_prompt(
    trending_hooks: list[dict],
    ad_hooks: list[dict],
    num_scripts: int = 5,
    trending_hashtags: list[dict] | None = None,
    niche: str = "",
) -> str:
    """
    Build the user prompt from scraped hook data.

    Formats top 10 trending hooks with full metadata (plays, engagement,
    shares, comments, duration, author, verified status), full captions
    from top performers, per-video hashtag analysis, trending sounds,
    ad hooks with spend and full text, and global trending hashtags.

    Args:
        trending_hooks: List of dicts with hook_text, stats, etc.
        ad_hooks: List of dicts with hook_text, cta, etc.
        num_scripts: How many scripts to generate
        trending_hashtags: List of hashtag dicts with name, viewCount, etc.
        niche: Target niche (e.g., "skincare"). Keeps scripts on-topic.

    Returns:
        Formatted user prompt string
    """
    sections = []

    # ── Niche context ──
    if niche:
        sections.append(
            f"NICHE: {niche}\n"
            f"All scripts must be relevant to the {niche} niche. "
            f"Use language, references, and pain points specific to {niche} audiences."
        )

    # ── Trending hooks with full metadata ──
    trending_lines = _build_trending_section(trending_hooks)
    if trending_lines:
        sections.append("\n".join(trending_lines))

    # ── Full captions — body structure inspiration ──
    caption_lines = _build_captions_section(trending_hooks)
    if caption_lines:
        sections.append("\n".join(caption_lines))

    # ── Per-video hashtag analysis ──
    tag_lines = _build_hashtag_analysis(trending_hooks)
    if tag_lines:
        sections.append("\n".join(tag_lines))

    # ── Trending sounds ──
    sound_lines = _build_sounds_section(trending_hooks)
    if sound_lines:
        sections.append("\n".join(sound_lines))

    # ── Ad hooks with spend and full text ──
    ad_lines = _build_ads_section(ad_hooks)
    if ad_lines:
        sections.append("\n".join(ad_lines))

    # ── Global trending hashtags from hashtag scraper ──
    global_tag_lines = _build_global_hashtags_section(trending_hashtags)
    if global_tag_lines:
        sections.append("\n".join(global_tag_lines))

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
        "Mix and remix the hook styles, vary the topics, and make each script distinct. "
        "Use hashtags that appeared on top-performing videos when relevant. "
        "Include suggested_hashtags and visual_hints in every script."
    )

    return "\n\n".join(sections)


def _fmt_price(price: float) -> str:
    """Format a price as $X.XX or $X if no cents."""
    if price == int(price):
        return f"${int(price)}"
    return f"${price:.2f}"


def _build_products_section(products: list[dict]) -> list[str]:
    """Build the product data section for the product prompt."""
    if not products:
        return []

    lines = ["TOP-PERFORMING PRODUCTS (sorted by revenue — write scripts about these):"]
    for i, p in enumerate(products[:10], 1):
        title = p.get("title", "Unknown Product")
        price = p.get("price", 0)
        revenue = p.get("revenue_estimate", 0)
        sales = p.get("sales_volume", 0)
        trend = p.get("trend_direction", "flat")
        category = p.get("category", "")

        parts = []
        if price:
            parts.append(_fmt_price(price))
        if revenue:
            parts.append(f"${_fmt_number(revenue)} revenue")
        if sales:
            parts.append(f"{_fmt_number(sales)} sales")
        if trend != "flat":
            parts.append(f"trend: {trend}")
        if category:
            parts.append(category)

        meta = ", ".join(parts) if parts else "no data"
        pid = p.get("product_id", "")
        lines.append(f'  {i}. [ID: {pid}] "{title}" ({meta})')

        # Include top video links for competitive intelligence
        videos = p.get("top_video_links", [])
        if videos:
            lines.append(f"     Top-performing videos for this product:")
            for v in videos[:3]:
                lines.append(f"       - {v}")
            lines.append(f"     Study these videos' hooks and styles when writing scripts for this product.")

    return lines


def build_product_prompt(
    products: list[dict],
    hooks: list[dict] | None = None,
    hashtags: list[dict] | None = None,
    niche: str = "",
    num_scripts: int = 5,
) -> str:
    """
    Build a user prompt for product-focused script generation.

    Args:
        products: List of product dicts from Kalodata scraper
        hooks: Optional trending hooks for style inspiration
        hashtags: Optional trending hashtags
        niche: Target niche
        num_scripts: Number of scripts to generate

    Returns:
        Formatted user prompt string
    """
    sections = []

    # ── Niche context ──
    if niche:
        sections.append(
            f"NICHE: {niche}\n"
            f"All scripts must feature products from the {niche} niche. "
            f"Use language and pain points specific to {niche} audiences."
        )

    # ── Product data ──
    product_lines = _build_products_section(products)
    if product_lines:
        sections.append("\n".join(product_lines))

    # ── Optional trending hooks for style inspiration ──
    if hooks:
        top_hooks = hooks[:5]
        lines = ["TRENDING HOOK STYLES (use these patterns, but adapt for the products above):"]
        for i, hook in enumerate(top_hooks, 1):
            text = hook.get("hook_text") or (hook.get("text", "") or hook.get("description", ""))[:80]
            plays = hook.get("stats", {}).get("plays", 0) or hook.get("playCount", 0)
            lines.append(f"  {i}. \"{text}\" ({_fmt_number(plays)} plays)")
        sections.append("\n".join(lines))

    # ── Trending hashtags ──
    if hashtags:
        tag_lines = _build_global_hashtags_section(hashtags)
        if tag_lines:
            sections.append("\n".join(tag_lines))

    # ── Fallback ──
    if not sections:
        sections.append(
            "No specific product data available — generate product-focused scripts "
            "based on current TikTok Shop trends and best practices."
        )

    # ── Generation instruction ──
    sections.append(
        f"Generate exactly {len(products)} scripts — one per product from the list above. "
        "Each script MUST feature a different product. Do NOT skip any product and do NOT "
        "write multiple scripts about the same product. "
        "Echo back the product's [ID: ...] value in the product_id field. "
        "Include price anchoring, social proof, and urgency in the body. "
        "Include suggested_hashtags (always include 'tiktokshop') and visual_hints with "
        "video_style, price_display, rating_display, and target_duration_sec in every script."
    )

    return "\n\n".join(sections)
