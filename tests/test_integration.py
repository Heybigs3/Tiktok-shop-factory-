"""Integration tests — require a live ANTHROPIC_API_KEY. Auto-skipped without one."""

import pytest

from src.generators.script_generator import generate_scripts, run
from src.utils.config import DATA_SCRIPTS_DIR
from src.utils.data_io import list_data_files


@pytest.mark.integration
class TestLiveAPI:
    """These tests call the real Claude API and are skipped without a key."""

    def test_generate_scripts_returns_valid_list(self):
        trending = [{"hook_text": "Test hook", "stats": {"plays": 1000}, "author": "test"}]
        scripts = generate_scripts(trending, [], num_scripts=2)
        assert isinstance(scripts, list)
        assert len(scripts) >= 1
        assert all(k in scripts[0] for k in ("hook", "body", "cta", "script_id"))

    def test_full_run_pipeline(self):
        scripts = run(num_scripts=1)
        assert isinstance(scripts, list)
        assert len(scripts) >= 1
        # Verify a file was created
        files = list_data_files(DATA_SCRIPTS_DIR, "scripts")
        assert len(files) >= 1
