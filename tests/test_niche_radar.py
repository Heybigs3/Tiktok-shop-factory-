"""Tests for the Niche Radar — dynamic niche scanner and scorer."""

import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from src.scrapers.niche_radar import (
    NICHE_CATALOG,
    SCORING_WEIGHTS,
    QUICK_SCAN_NICHES,
    normalize_score,
    calc_engagement_score,
    calc_velocity_score,
    calc_gap_score,
    calc_momentum_score,
    score_niche,
    recommend_accounts,
    build_niche_config,
    display_results,
    MENU,
)


# ── Catalog tests ─────────────────────────────────────────────────────────────

class TestNicheCatalog:
    def test_niche_catalog_has_required_keys(self):
        """Each niche must have queries, hashtags, and kalodata_cat."""
        for niche_key, niche in NICHE_CATALOG.items():
            assert "queries" in niche, f"{niche_key} missing 'queries'"
            assert "hashtags" in niche, f"{niche_key} missing 'hashtags'"
            assert "kalodata_cat" in niche, f"{niche_key} missing 'kalodata_cat'"

    def test_niche_catalog_no_empty_values(self):
        """No empty strings or empty lists in catalog entries."""
        for niche_key, niche in NICHE_CATALOG.items():
            assert len(niche["queries"]) > 0, f"{niche_key} has empty queries"
            assert len(niche["hashtags"]) > 0, f"{niche_key} has empty hashtags"
            assert niche["kalodata_cat"], f"{niche_key} has empty kalodata_cat"
            for q in niche["queries"]:
                assert q.strip(), f"{niche_key} has blank query"
            for h in niche["hashtags"]:
                assert h.strip(), f"{niche_key} has blank hashtag"

    def test_niche_catalog_minimum_count(self):
        """Catalog should have at least 8 niches."""
        assert len(NICHE_CATALOG) >= 8

    def test_quick_scan_niches_are_valid(self):
        """Quick scan list should only contain valid catalog keys."""
        for key in QUICK_SCAN_NICHES:
            assert key in NICHE_CATALOG, f"Quick scan niche '{key}' not in catalog"


# ── Scoring weight tests ──────────────────────────────────────────────────────

class TestScoringWeights:
    def test_scoring_weights_sum_to_one(self):
        """All scoring weights must sum to 1.0."""
        total = sum(SCORING_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, not 1.0"

    def test_scoring_weights_all_positive(self):
        """Each weight must be positive."""
        for name, weight in SCORING_WEIGHTS.items():
            assert weight > 0, f"Weight '{name}' is not positive"


# ── Normalize tests ───────────────────────────────────────────────────────────

class TestNormalize:
    def test_normalize_score_clamps_to_range(self):
        assert normalize_score(-10) == 0.0
        assert normalize_score(150) == 100.0
        assert normalize_score(50) == 50.0

    def test_normalize_score_boundaries(self):
        assert normalize_score(0) == 0.0
        assert normalize_score(100) == 100.0


# ── Engagement score tests ────────────────────────────────────────────────────

def _make_video(plays=100_000, likes=5000, comments=200, shares=300, create_time=None):
    """Helper to create a fake Apify video dict."""
    video = {
        "playCount": plays,
        "diggCount": likes,
        "shareCount": shares,
        "commentCount": comments,
    }
    if create_time is not None:
        video["createTime"] = create_time
    return video


class TestEngagementScore:
    def test_score_niche_empty_videos_returns_zero(self):
        """No videos → engagement score = 0."""
        assert calc_engagement_score([]) == 0.0

    def test_score_niche_high_engagement_scores_high(self):
        """Videos with 10%+ engagement should score close to 100."""
        videos = [_make_video(plays=100_000, likes=8000, comments=1000, shares=1000)] * 5
        score = calc_engagement_score(videos)
        assert score >= 70, f"High engagement scored only {score}"

    def test_low_engagement_scores_low(self):
        """Videos with <0.5% engagement should score low."""
        videos = [_make_video(plays=1_000_000, likes=100, comments=10, shares=5)] * 5
        score = calc_engagement_score(videos)
        assert score <= 15, f"Low engagement scored {score}"

    def test_medium_engagement(self):
        """3% engagement rate → score around 50."""
        # 3% of 100k = 3000 total interactions
        videos = [_make_video(plays=100_000, likes=2500, comments=300, shares=200)] * 5
        score = calc_engagement_score(videos)
        assert 40 <= score <= 60, f"Medium engagement scored {score}"


# ── Velocity score tests ─────────────────────────────────────────────────────

class TestVelocityScore:
    def test_velocity_empty_videos(self):
        assert calc_velocity_score([]) == 0.0

    def test_velocity_recent_videos_score_higher(self):
        """Videos from the last 48h should score higher than old ones."""
        now = datetime.now(timezone.utc).timestamp()

        recent = [_make_video(plays=100_000, likes=5000, comments=200, shares=300,
                              create_time=now - 3600)]  # 1 hour ago
        old = [_make_video(plays=100_000, likes=5000, comments=200, shares=300,
                           create_time=now - 604800)]  # 7 days ago

        recent_score = calc_velocity_score(recent)
        old_score = calc_velocity_score(old)
        assert recent_score > old_score, f"Recent ({recent_score}) should beat old ({old_score})"

    def test_velocity_no_timestamp_uses_neutral(self):
        """Videos without createTime get neutral weighting."""
        videos = [_make_video(plays=100_000, likes=5000, comments=200, shares=300)]
        score = calc_velocity_score(videos)
        assert score > 0, "Should still produce a score without timestamps"


# ── Gap score tests ───────────────────────────────────────────────────────────

class TestGapScore:
    def test_gap_score_no_products_neutral(self):
        """No Kalodata data → 50 (neutral)."""
        assert calc_gap_score([], None) == 50.0
        assert calc_gap_score([], []) == 50.0

    def test_gap_score_high_demand_low_supply(self):
        """Many products, few viral videos → high gap score."""
        videos = [_make_video(plays=50_000)]  # Below 100k threshold
        products = [{"name": f"Product {i}"} for i in range(10)]
        score = calc_gap_score(videos, products)
        assert score >= 60, f"High demand/low supply scored only {score}"

    def test_gap_score_low_demand_high_supply(self):
        """Few products, many viral videos → low gap score."""
        videos = [_make_video(plays=500_000) for _ in range(10)]  # 10 viral videos
        products = [{"name": "Only product"}]
        score = calc_gap_score(videos, products)
        assert score <= 40, f"Low demand/high supply scored {score}"


# ── Momentum score tests ─────────────────────────────────────────────────────

class TestMomentumScore:
    def test_momentum_no_hashtags(self):
        assert calc_momentum_score([]) == 0.0

    def test_momentum_no_previous_data_neutral(self):
        """First scan → 50 (neutral)."""
        hashtags = [{"name": "skincare", "viewCount": 1_000_000}]
        assert calc_momentum_score(hashtags, None) == 50.0

    def test_momentum_growing_hashtags_score_higher(self):
        """Growing hashtag views → score above 50."""
        current = [{"name": "skincare", "viewCount": 1_200_000}]
        previous = [{"name": "skincare", "viewCount": 1_000_000}]  # 20% growth
        score = calc_momentum_score(current, previous)
        assert score > 50, f"Growing hashtags scored only {score}"

    def test_momentum_declining_hashtags_score_lower(self):
        """Declining hashtag views → score below 50."""
        current = [{"name": "skincare", "viewCount": 800_000}]
        previous = [{"name": "skincare", "viewCount": 1_000_000}]  # -20% decline
        score = calc_momentum_score(current, previous)
        assert score < 40, f"Declining hashtags scored {score}"


# ── Score niche (integration of sub-scores) ──────────────────────────────────

class TestScoreNiche:
    def test_score_niche_returns_all_subscores(self):
        """Scored result must include all 4 sub-scores."""
        scan = {"niche": "skincare", "videos": [], "hashtags": [], "products": []}
        with patch("src.scrapers.niche_radar.load_latest", return_value=None):
            result = score_niche(scan)

        assert "scores" in result
        for key in ["engagement", "velocity", "gap", "momentum"]:
            assert key in result["scores"], f"Missing sub-score: {key}"

    def test_score_niche_total_is_weighted_sum(self):
        """Total score must be the weighted sum of sub-scores."""
        scan = {
            "niche": "skincare",
            "videos": [_make_video()] * 5,
            "hashtags": [{"name": "skincare", "viewCount": 1_000_000}],
            "products": [],
        }
        with patch("src.scrapers.niche_radar.load_latest", return_value=None):
            result = score_niche(scan)

        scores = result["scores"]
        expected_total = (
            SCORING_WEIGHTS["engagement"] * scores["engagement"]
            + SCORING_WEIGHTS["velocity"] * scores["velocity"]
            + SCORING_WEIGHTS["gap"] * scores["gap"]
            + SCORING_WEIGHTS["momentum"] * scores["momentum"]
        )
        assert abs(result["total_score"] - round(expected_total, 1)) < 0.2

    def test_score_niche_includes_reasoning(self):
        """Result must include a reasoning string."""
        scan = {"niche": "skincare", "videos": [], "hashtags": [], "products": []}
        with patch("src.scrapers.niche_radar.load_latest", return_value=None):
            result = score_niche(scan)
        assert "reasoning" in result
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 0


# ── Recommendations ──────────────────────────────────────────────────────────

class TestRecommendAccounts:
    @pytest.fixture
    def scored_niches(self):
        """5 scored niches with different categories and scores."""
        return [
            {"niche": "skincare", "kalodata_cat": "Beauty", "total_score": 80, "reasoning": "High engagement"},
            {"niche": "haircare", "kalodata_cat": "Beauty", "total_score": 75, "reasoning": "Good velocity"},
            {"niche": "kitchen_gadgets", "kalodata_cat": "Home", "total_score": 70, "reasoning": "Great gap"},
            {"niche": "fitness_gear", "kalodata_cat": "Sports", "total_score": 65, "reasoning": "Growing"},
            {"niche": "pet_products", "kalodata_cat": "Pet", "total_score": 60, "reasoning": "Steady"},
        ]

    def test_recommend_accounts_returns_n(self, scored_niches):
        result = recommend_accounts(scored_niches, num_accounts=3)
        assert len(result) == 3

    def test_recommend_accounts_diversity(self, scored_niches):
        """Top 3 should span different kalodata_cat values."""
        result = recommend_accounts(scored_niches, num_accounts=3)
        categories = [r["kalodata_cat"] for r in result]
        assert len(set(categories)) == len(categories), f"Duplicate categories: {categories}"

    def test_recommend_accounts_sorted_by_score(self, scored_niches):
        """Results should be ordered by score (highest first)."""
        result = recommend_accounts(scored_niches, num_accounts=3)
        scores = [r["total_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_recommend_accounts_with_fewer_niches_than_n(self):
        """Graceful when fewer niches than requested."""
        niches = [
            {"niche": "skincare", "kalodata_cat": "Beauty", "total_score": 80, "reasoning": "Good"},
        ]
        result = recommend_accounts(niches, num_accounts=3)
        assert len(result) == 1

    def test_recommend_accounts_includes_reasoning(self, scored_niches):
        result = recommend_accounts(scored_niches, num_accounts=3)
        for r in result:
            assert "reasoning" in r
            assert isinstance(r["reasoning"], str)

    def test_recommend_accounts_skips_zero_score(self):
        """Niches with zero score should be filtered out."""
        niches = [
            {"niche": "skincare", "kalodata_cat": "Beauty", "total_score": 80, "reasoning": "Good"},
            {"niche": "haircare", "kalodata_cat": "Beauty", "total_score": 0, "reasoning": "No data"},
        ]
        result = recommend_accounts(niches, num_accounts=3)
        assert all(r["total_score"] > 0 for r in result)

    def test_recommend_accounts_empty_input(self):
        assert recommend_accounts([]) == []


# ── Config generation ────────────────────────────────────────────────────────

class TestBuildNicheConfig:
    def test_build_niche_config_has_required_sections(self):
        config = build_niche_config("skincare")
        assert "search_queries" in config
        assert "ad_keywords" in config
        assert "hashtags" in config
        assert "niche" in config
        assert "product_sources" in config

    def test_build_niche_config_uses_scan_data(self):
        scan_data = {"top_hooks": ["Stop scrolling", "You need this"]}
        config = build_niche_config("skincare", scan_data=scan_data)
        assert "reference_hooks" in config
        assert config["reference_hooks"] == ["Stop scrolling", "You need this"]

    def test_build_niche_config_valid_json(self):
        config = build_niche_config("kitchen_gadgets")
        # Should be JSON-serializable
        serialized = json.dumps(config)
        parsed = json.loads(serialized)
        assert parsed["niche"] == "kitchen_gadgets"

    def test_build_niche_config_tts_defaults(self):
        config = build_niche_config("skincare")
        assert "tts" in config
        assert "enabled" in config["tts"]

    def test_build_niche_config_unknown_niche(self):
        config = build_niche_config("nonexistent_niche")
        assert config == {}

    def test_build_niche_config_niche_specific_values(self):
        """Config should use catalog values, not hardcoded defaults."""
        config = build_niche_config("pet_products")
        assert config["niche"] == "pet_products"
        assert "pet product tiktok viral" in config["search_queries"]
        assert "pettok" in config["hashtags"]


# ── Account setup tests ──────────────────────────────────────────────────────

class TestSetupAccounts:
    def test_setup_accounts_creates_accounts(self):
        """Mock accounts.create_account should be called for each recommendation."""
        recommendations = [
            {"niche": "skincare", "kalodata_cat": "Beauty", "total_score": 80, "reasoning": "Good", "top_hooks": []},
            {"niche": "kitchen_gadgets", "kalodata_cat": "Home", "total_score": 70, "reasoning": "Great", "top_hooks": []},
        ]

        mock_account = {"id": "abc123", "name": "Test", "niche": "skincare", "is_default": False}

        with patch("src.dashboard.accounts.create_account", return_value=mock_account) as mock_create, \
             patch("src.dashboard.accounts.save_account_config") as mock_save:
            from src.scrapers.niche_radar import setup_accounts
            result = setup_accounts(recommendations)

        assert mock_create.call_count == 2
        assert mock_save.call_count == 2

    def test_setup_accounts_saves_configs(self):
        """Each created account should get a niche-specific config saved."""
        recommendations = [
            {"niche": "skincare", "kalodata_cat": "Beauty", "total_score": 80, "reasoning": "Good", "top_hooks": ["hook1"]},
        ]

        mock_account = {"id": "xyz789", "name": "Skincare", "niche": "skincare", "is_default": False}

        with patch("src.dashboard.accounts.create_account", return_value=mock_account) as mock_create, \
             patch("src.dashboard.accounts.save_account_config") as mock_save:
            from src.scrapers.niche_radar import setup_accounts
            setup_accounts(recommendations)

        # Verify config was saved with the account ID
        mock_save.assert_called_once()
        saved_id = mock_save.call_args[0][0]
        saved_config = mock_save.call_args[0][1]
        assert saved_id == "xyz789"
        assert saved_config["niche"] == "skincare"


# ── CLI/display tests ────────────────────────────────────────────────────────

class TestDisplay:
    def test_cli_menu_options_exist(self):
        """Menu should have all expected options."""
        assert "1" in MENU
        assert "2" in MENU
        assert "3" in MENU
        assert "4" in MENU
        assert "5" in MENU
        assert "6" in MENU

    def test_display_results_table(self):
        """display_results should not crash with sample data."""
        results = [
            {
                "niche": "skincare",
                "total_score": 75.0,
                "scores": {"engagement": 80, "velocity": 70, "gap": 50, "momentum": 60},
                "reasoning": "High engagement. Recent viral activity.",
            },
        ]
        # Should not raise
        display_results(results)

    def test_display_results_empty(self):
        """display_results should handle empty list gracefully."""
        display_results([])


# ── Integration tests (live API) ─────────────────────────────────────────────

@pytest.mark.integration
class TestLiveScans:
    def test_scan_niche_live(self):
        """Live Apify scan for one niche — requires APIFY_API_TOKEN."""
        from src.scrapers.niche_radar import scan_niche
        result = scan_niche("skincare", max_results=3)
        assert result["niche"] == "skincare"
        assert isinstance(result["videos"], list)
        assert result["scanned_at"]

    def test_scan_all_niches_quick_live(self):
        """Live quick scan — requires APIFY_API_TOKEN."""
        from src.scrapers.niche_radar import scan_all_niches
        results = scan_all_niches(quick=True)
        assert len(results) > 0
        assert all("total_score" in r for r in results)
