"""Tests for src/generators/script_generator.parse_scripts() — JSON parsing edge cases."""

import json

from src.generators.script_generator import parse_scripts


class TestParseCleanJSON:
    """parse_scripts with well-formed input."""

    def test_valid_json_array(self, sample_claude_response, sample_trending_hooks, sample_ad_hooks):
        scripts = parse_scripts(sample_claude_response, sample_trending_hooks, sample_ad_hooks)
        assert len(scripts) == 2
        assert all("script_id" in s for s in scripts)
        assert all("source_type" in s for s in scripts)
        assert all("estimated_duration_sec" in s for s in scripts)

    def test_markdown_fenced(self, sample_claude_response, sample_trending_hooks, sample_ad_hooks):
        fenced = f"```json\n{sample_claude_response}\n```"
        scripts = parse_scripts(fenced, sample_trending_hooks, sample_ad_hooks)
        assert len(scripts) == 2

    def test_preamble_before_json(self, sample_claude_response, sample_trending_hooks, sample_ad_hooks):
        with_preamble = f"Here are the scripts:\n{sample_claude_response}"
        scripts = parse_scripts(with_preamble, sample_trending_hooks, sample_ad_hooks)
        assert len(scripts) == 2


class TestSourceType:
    """source_type is set based on which hook lists are non-empty."""

    def test_mixed(self, sample_claude_response, sample_trending_hooks, sample_ad_hooks):
        scripts = parse_scripts(sample_claude_response, sample_trending_hooks, sample_ad_hooks)
        assert scripts[0]["source_type"] == "mixed"

    def test_trending_only(self, sample_claude_response, sample_trending_hooks):
        scripts = parse_scripts(sample_claude_response, sample_trending_hooks, [])
        assert scripts[0]["source_type"] == "trending"

    def test_ad_only(self, sample_claude_response, sample_ad_hooks):
        scripts = parse_scripts(sample_claude_response, [], sample_ad_hooks)
        assert scripts[0]["source_type"] == "ad"


class TestEdgeCases:
    """Error handling and duration calculation."""

    def test_invalid_json_returns_empty(self):
        scripts = parse_scripts("this is not json at all", [], [])
        assert scripts == []

    def test_duration_calculation(self):
        # 12 words total → 12 / 3 = 4 seconds
        raw = json.dumps([{
            "hook": "one two three",
            "body": "four five six seven eight nine",
            "cta": "ten eleven twelve",
            "style_notes": "fast",
        }])
        scripts = parse_scripts(raw, [], [])
        assert scripts[0]["estimated_duration_sec"] == 4
