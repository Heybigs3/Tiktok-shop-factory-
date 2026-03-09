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
