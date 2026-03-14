"""Tests for src/generators/templates.py — prompt building and constants."""

from src.generators.templates import (
    CLAUDE_MODEL,
    MAX_TOKENS,
    SYSTEM_PROMPT,
    build_user_prompt,
)


class TestConstants:
    """Verify template constants are sane."""

    def test_claude_model_non_empty(self):
        assert CLAUDE_MODEL, "CLAUDE_MODEL must not be empty"

    def test_max_tokens_positive(self):
        assert MAX_TOKENS > 0, "MAX_TOKENS must be positive"

    def test_system_prompt_requires_json_array(self):
        assert "JSON array" in SYSTEM_PROMPT

    def test_system_prompt_requests_visual_hints(self):
        assert "visual_hints" in SYSTEM_PROMPT

    def test_system_prompt_requests_suggested_hashtags(self):
        assert "suggested_hashtags" in SYSTEM_PROMPT

    def test_system_prompt_mentions_sounds(self):
        assert "sound" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_shares(self):
        assert "share" in SYSTEM_PROMPT.lower()


class TestBuildUserPrompt:
    """Tests for build_user_prompt() output formatting."""

    def test_both_hook_types(self, sample_trending_hooks, sample_ad_hooks):
        prompt = build_user_prompt(sample_trending_hooks, sample_ad_hooks)
        assert "TRENDING" in prompt
        assert "AD HOOKS" in prompt
        # Play counts should be formatted
        assert "2.5M plays" in prompt

    def test_trending_only(self, sample_trending_hooks):
        prompt = build_user_prompt(sample_trending_hooks, [])
        assert "TRENDING" in prompt
        assert "AD HOOKS" not in prompt

    def test_ads_only(self, sample_ad_hooks):
        prompt = build_user_prompt([], sample_ad_hooks)
        assert "TRENDING" not in prompt
        assert "AD HOOKS" in prompt

    def test_empty_fallback(self):
        prompt = build_user_prompt([], [])
        assert "No specific hooks available" in prompt

    def test_num_scripts_in_prompt(self, sample_trending_hooks):
        prompt = build_user_prompt(sample_trending_hooks, [], num_scripts=3)
        assert "Generate 3" in prompt

    def test_hashtags_section(self, sample_trending_hooks, sample_ad_hooks, sample_hashtags):
        prompt = build_user_prompt(
            sample_trending_hooks, sample_ad_hooks,
            trending_hashtags=sample_hashtags,
        )
        assert "TRENDING HASHTAGS" in prompt
        assert "#skincare" in prompt
        assert "#glowup" in prompt

    def test_hashtags_view_count_formatted(self, sample_hashtags):
        prompt = build_user_prompt([], [], trending_hashtags=sample_hashtags)
        # 45B views for skincare
        assert "45.0B views" in prompt

    def test_no_hashtags_no_section(self, sample_trending_hooks):
        prompt = build_user_prompt(sample_trending_hooks, [])
        assert "TRENDING HASHTAGS" not in prompt

    def test_empty_hashtags_no_section(self, sample_trending_hooks):
        prompt = build_user_prompt(sample_trending_hooks, [], trending_hashtags=[])
        assert "TRENDING HASHTAGS" not in prompt

    def test_prompt_mentions_visual_hints(self, sample_trending_hooks):
        prompt = build_user_prompt(sample_trending_hooks, [])
        assert "visual_hints" in prompt

    def test_raw_format_fallback(self, sample_raw_apify_videos):
        """build_user_prompt works with raw Apify data (no hook_text field)."""
        prompt = build_user_prompt(sample_raw_apify_videos, [])
        assert "TRENDING" in prompt
        # Should extract text from raw 'text' field
        assert "Stop scrolling" in prompt
        # Should extract playCount
        assert "2.5M plays" in prompt

    def test_enriched_format_engagement(self):
        """Enriched hooks include engagement rate, duration, and author info."""
        enriched = [
            {
                "hook_text": "This changed my skin in 3 days",
                "stats": {"plays": 1000000, "engagement_rate": 0.05},
                "video_duration_sec": 18,
                "author": "skinpro",
                "author_fans": 250000,
            }
        ]
        prompt = build_user_prompt(enriched, [])
        assert "5.0% eng" in prompt
        assert "18s" in prompt
        assert "@skinpro" in prompt
        assert "250.0K fans" in prompt

    def test_ad_cta_text_field(self):
        """Ad hooks with cta_text (processed format) render correctly."""
        ads = [{"hook_text": "Buy this now", "cta_text": "Shop Now"}]
        prompt = build_user_prompt([], ads)
        assert "Shop Now" in prompt

    # ── Shares & comments in prompt ──

    def test_shares_in_prompt(self):
        hooks = [
            {
                "hook_text": "You need to see this trick",
                "stats": {"plays": 500000, "shares": 12000, "comments": 3000},
            }
        ]
        prompt = build_user_prompt(hooks, [])
        assert "12.0K shares" in prompt
        assert "3.0K comments" in prompt

    # ── Verified badge ──

    def test_verified_badge(self):
        hooks = [
            {
                "hook_text": "Verified creator hook text here",
                "stats": {"plays": 100000},
                "author": "dermguru",
                "author_fans": 1000000,
                "author_verified": True,
            }
        ]
        prompt = build_user_prompt(hooks, [])
        assert "@dermguru" in prompt
        assert "\u2713" in prompt  # checkmark

    # ── Full captions section ──

    def test_full_captions_section(self):
        hooks = [
            {
                "hook_text": "Stop scrolling!",
                "full_text": "Stop scrolling! This is the routine that cleared my skin in 2 weeks. Step one: double cleanse. Step two: niacinamide.",
                "stats": {"plays": 2000000},
            }
        ]
        prompt = build_user_prompt(hooks, [])
        assert "FULL CAPTIONS" in prompt
        assert "double cleanse" in prompt

    def test_no_captions_when_full_text_same_as_hook(self):
        hooks = [
            {
                "hook_text": "Short video caption",
                "full_text": "Short video caption",
                "stats": {"plays": 100},
            }
        ]
        prompt = build_user_prompt(hooks, [])
        assert "FULL CAPTIONS" not in prompt

    # ── Per-video hashtag analysis ──

    def test_hashtag_analysis_from_videos(self):
        hooks = [
            {"hook_text": "Hook one with good text", "stats": {"plays": 100}, "hashtags": ["skincare", "glowup"]},
            {"hook_text": "Hook two with good text", "stats": {"plays": 200}, "hashtags": ["skincare", "routine"]},
        ]
        prompt = build_user_prompt(hooks, [])
        assert "HASHTAGS USED BY TOP VIDEOS" in prompt
        assert "#skincare" in prompt
        assert "2 videos" in prompt

    def test_no_hashtag_analysis_without_data(self, sample_trending_hooks):
        prompt = build_user_prompt(sample_trending_hooks, [])
        assert "HASHTAGS USED BY TOP VIDEOS" not in prompt

    # ── Trending sounds section ──

    def test_trending_sounds_section(self):
        hooks = [
            {"hook_text": "Hook with music and text", "stats": {"plays": 100}, "music": "Chill Vibes - Artist"},
            {"hook_text": "Another hook text here", "stats": {"plays": 200}, "music": "Chill Vibes - Artist"},
        ]
        prompt = build_user_prompt(hooks, [])
        assert "TRENDING SOUNDS" in prompt
        assert "Chill Vibes - Artist" in prompt
        assert "2 videos" in prompt

    def test_no_sounds_section_with_original_audio(self):
        hooks = [
            {"hook_text": "Hook text content here only", "stats": {"plays": 100}, "music": "original sound"},
        ]
        prompt = build_user_prompt(hooks, [])
        assert "TRENDING SOUNDS" not in prompt

    def test_no_sounds_section_without_music(self, sample_trending_hooks):
        prompt = build_user_prompt(sample_trending_hooks, [])
        assert "TRENDING SOUNDS" not in prompt

    # ── Ad full text and spend ──

    def test_ad_full_text_in_prompt(self):
        ads = [
            {
                "hook_text": "This serum is amazing",
                "full_text": "This serum is amazing. It transformed my skin in just 3 days. Every dermatologist I know recommends it.",
                "cta_text": "Shop Now",
                "estimated_spend": 5000,
                "advertiser": "GlowBrand",
            }
        ]
        prompt = build_user_prompt([], ads)
        assert "GlowBrand" in prompt
        assert "$5.0K spend" in prompt
        assert "Full:" in prompt
        assert "dermatologist" in prompt

    def test_ad_no_full_text_when_short(self):
        ads = [{"hook_text": "Buy this now please", "full_text": "Buy this now please", "cta_text": "Shop"}]
        prompt = build_user_prompt([], ads)
        assert "Full:" not in prompt
