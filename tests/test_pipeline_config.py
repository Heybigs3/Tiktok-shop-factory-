"""Tests for pipeline_config.json loading and scraper parameterization."""

import json

from src.utils.config import (
    PIPELINE_CONFIG_PATH,
    _DEFAULT_PIPELINE_CONFIG,
    load_pipeline_config,
)


class TestLoadPipelineConfig:
    """Tests for load_pipeline_config()."""

    def test_loads_from_file(self):
        """pipeline_config.json should exist and be loadable."""
        config = load_pipeline_config()
        assert isinstance(config, dict)
        assert "niche" in config

    def test_has_required_keys(self):
        config = load_pipeline_config()
        required = ["niche", "search_queries", "ad_keywords", "hashtags",
                     "max_results_per_query", "num_scripts"]
        for key in required:
            assert key in config, f"Missing key: {key}"

    def test_search_queries_is_list(self):
        config = load_pipeline_config()
        assert isinstance(config["search_queries"], list)
        assert len(config["search_queries"]) > 0

    def test_max_results_positive(self):
        config = load_pipeline_config()
        assert config["max_results_per_query"] > 0

    def test_num_scripts_positive(self):
        config = load_pipeline_config()
        assert config["num_scripts"] > 0

    def test_default_config_returned_when_missing(self, tmp_path, monkeypatch):
        """When pipeline_config.json doesn't exist, defaults are returned."""
        import src.utils.config as config_module
        monkeypatch.setattr(config_module, "PIPELINE_CONFIG_PATH", tmp_path / "nonexistent.json")
        result = config_module.load_pipeline_config()
        assert result == _DEFAULT_PIPELINE_CONFIG

    def test_config_file_is_valid_json(self):
        """pipeline_config.json should be valid JSON."""
        with open(PIPELINE_CONFIG_PATH, "r") as f:
            data = json.load(f)
        assert isinstance(data, dict)
