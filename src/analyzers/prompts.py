"""
prompts.py — Prompt templates for video analysis and Style Bible synthesis.

Separates prompt text from analysis logic, same pattern as generators/templates.py.
"""

# ── Per-video multimodal analysis ──

VIDEO_ANALYSIS_SYSTEM_PROMPT = """\
You are a TikTok video analyst specializing in viral short-form content. You will receive \
frames extracted from a TikTok video along with its transcript and metadata. Your job is \
to produce a structured JSON analysis of the video's creative strategy.

Analyze these specific elements:
- **Hook**: What is the opening hook? How long does it last? What type is it?
- **Structure**: How many visual cuts/transitions? What's the pacing?
- **Text overlays**: What text appears on screen? Where is it positioned?
- **Color palette**: What are the dominant, accent, and text colors? Use hex codes.
- **Audio**: Is there music? Voiceover? What's the energy pattern?
- **CTA**: What's the call to action? Where does it appear?
- **Engagement factors**: What psychological triggers does the video use?

Hook types to identify:
- question, bold_claim, pov, pattern_interrupt, contrarian, price_anchoring, \
social_proof, urgency, before_after, listicle, story, challenge

Output a single JSON object (no markdown fencing, no text outside the JSON) with this schema:
{
  "video_id": "string",
  "hook": {"text": "string", "duration_s": number, "type": "string"},
  "structure": {"total_duration_s": number, "num_cuts": number, "avg_cut_duration_s": number},
  "text_overlays": [{"text": "string", "position": "string", "appears_at": number, "font_size_estimate": "string"}],
  "color_palette": {"dominant": "#hex", "accent": "#hex", "text": "#hex"},
  "audio": {"has_music": boolean, "has_voiceover": boolean, "energy_pattern": "string"},
  "cta": {"text": "string", "position": "string", "type": "string"},
  "engagement_factors": ["string"],
  "overall_quality_score": number
}

Position values: "upper_left", "upper_center", "upper_right", "center_left", "center", \
"center_right", "lower_left", "center_lower", "lower_right"
Font size estimates: "small", "medium", "large", "xlarge"
Energy patterns: describe as a sequence like "spike-dip-steady-spike"
CTA types: "link_in_bio", "follow", "comment", "share", "shop_now", "swipe_up", "duet", "other"
Quality score: 0-100 based on production quality, hook strength, pacing, and clarity.\
"""

VIDEO_ANALYSIS_USER_TEMPLATE = """\
Analyze this TikTok video.

Video ID: {video_id}
Duration: {duration_s:.1f}s
Resolution: {width}x{height}
FPS: {fps}

{transcript_section}

The frames below are evenly spaced through the video. Analyze the visual style, \
text overlays, color palette, transitions, and overall production quality.\
"""

# ── Style Bible synthesis ──

STYLE_BIBLE_SYSTEM_PROMPT = """\
You are a TikTok creative strategist synthesizing patterns from video analyses into \
an actionable Style Bible. You will receive aggregated statistics from multiple \
analyzed TikTok videos in a specific niche.

Your job is to identify winning patterns and produce a comprehensive Style Bible \
that a script generator and video renderer can use to create high-performing content.

Output a JSON object (no markdown fencing, no text outside the JSON) with this schema:
{
  "niche": "string",
  "num_videos_analyzed": number,
  "hook_patterns": {
    "top_types": [{"type": "string", "frequency_pct": number, "avg_quality": number}],
    "avg_duration_s": number,
    "best_practices": ["string"]
  },
  "structure_patterns": {
    "avg_duration_s": number,
    "avg_cuts": number,
    "avg_cut_duration_s": number,
    "pacing_notes": "string"
  },
  "visual_style": {
    "dominant_colors": ["#hex"],
    "accent_colors": ["#hex"],
    "text_colors": ["#hex"],
    "text_placement": [{"position": "string", "frequency_pct": number}],
    "font_size_preference": "string",
    "background_style": "string"
  },
  "audio_patterns": {
    "music_usage_pct": number,
    "voiceover_usage_pct": number,
    "common_energy_patterns": ["string"]
  },
  "cta_patterns": {
    "top_types": [{"type": "string", "frequency_pct": number}],
    "common_positions": ["string"],
    "best_practices": ["string"]
  },
  "engagement_factors": [{"factor": "string", "frequency_pct": number}],
  "top_recommendations": ["string"]
}\
"""

STYLE_BIBLE_USER_TEMPLATE = """\
Synthesize the following aggregated video analysis data into a Style Bible for the \
"{niche}" niche.

Videos analyzed: {num_videos}

{aggregated_stats}

Based on these patterns, create a comprehensive Style Bible that captures what makes \
top-performing {niche} TikTok videos successful. Focus on actionable insights that \
a script writer and video editor can directly apply.\
"""

# ── Video comparison (scraped vs rendered) ──

COMPARISON_SYSTEM_PROMPT = """\
You are a TikTok content quality analyst. You will receive analysis summaries from two \
sets of videos:
1. SCRAPED videos — top-performing TikTok content from real creators
2. RENDERED videos — our factory-generated content

Your job is to identify exactly WHY the scraped videos outperform ours and provide \
specific, actionable fixes. Be brutally honest. Focus on what matters for engagement.

Output a JSON object (no markdown fencing, no text outside the JSON) with this schema:
{
  "num_scraped": number,
  "num_rendered": number,
  "overall_verdict": "string (1-2 sentence summary of the core problem)",
  "quality_comparison": {
    "scraped_avg": number,
    "rendered_avg": number,
    "gap": number
  },
  "gaps": [
    {
      "category": "string (e.g. 'Visual Dynamism', 'Hook Quality', 'Pacing')",
      "issue": "string (what's wrong with our videos)",
      "scraped_value": "string (what the good videos do)",
      "rendered_value": "string (what our videos do instead)",
      "impact": "string (why this matters for engagement)",
      "fix": "string (specific technical fix we can implement)"
    }
  ],
  "priority_fixes": [
    "string (ordered list of the most impactful changes to make, most important first)"
  ]
}

Categories to evaluate: Visual Dynamism, Hook Strength, Pacing/Cuts, Color Palette, \
Text Overlays, Audio/Music, CTA Effectiveness, Production Quality, Authenticity.\
"""

COMPARISON_USER_TEMPLATE = """\
Compare these two sets of {niche} TikTok videos and tell us exactly why our videos \
underperform compared to the scraped top performers.

{scraped_summary}

{rendered_summary}

Be specific and actionable. We need to know exactly what to change in our video \
rendering pipeline to close the gap. The scraped videos represent what actually works \
on TikTok — our rendered videos need to match that quality.\
"""
