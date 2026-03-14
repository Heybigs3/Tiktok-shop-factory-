"""Tests for the account management system."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.dashboard.accounts import (
    load_accounts,
    get_account,
    create_account,
    update_account,
    delete_account,
    get_account_paths,
    get_account_config,
    save_account_config,
    _read_registry,
    _write_registry,
    _ensure_default,
)


@pytest.fixture
def accounts_env(tmp_path):
    """Patch ACCOUNTS_FILE and DATA_ACCOUNTS_DIR to use tmp_path."""
    accounts_file = tmp_path / "accounts.json"
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    with patch("src.dashboard.accounts.ACCOUNTS_FILE", accounts_file), \
         patch("src.dashboard.accounts.DATA_ACCOUNTS_DIR", accounts_dir), \
         patch("src.dashboard.accounts.PIPELINE_CONFIG_PATH", tmp_path / "pipeline_config.json"):
        # Write a minimal pipeline config
        (tmp_path / "pipeline_config.json").write_text(
            json.dumps({"niche": "skincare", "search_queries": ["skincare routine"]}),
            encoding="utf-8",
        )
        yield {
            "file": accounts_file,
            "dir": accounts_dir,
            "tmp": tmp_path,
        }


# ── Registry I/O ────────────────────────────────────────────────────────────


class TestRegistryIO:
    def test_read_empty_registry(self, accounts_env):
        """Returns empty list when accounts.json doesn't exist."""
        assert _read_registry() == []

    def test_write_and_read_registry(self, accounts_env):
        """Round-trip write/read preserves data."""
        data = [{"id": "test", "name": "Test"}]
        _write_registry(data)
        assert _read_registry() == data

    def test_ensure_default_creates_on_first_run(self, accounts_env):
        """Default account auto-created when registry is empty."""
        accounts = _ensure_default()
        assert len(accounts) == 1
        assert accounts[0]["id"] == "default"
        assert accounts[0]["is_default"] is True

    def test_ensure_default_idempotent(self, accounts_env):
        """Calling _ensure_default twice doesn't duplicate."""
        _ensure_default()
        accounts = _ensure_default()
        assert len(accounts) == 1


# ── CRUD ────────────────────────────────────────────────────────────────────


class TestLoadAccounts:
    def test_returns_list_with_default(self, accounts_env):
        accounts = load_accounts()
        assert isinstance(accounts, list)
        assert any(a["id"] == "default" for a in accounts)

    def test_default_has_niche_from_config(self, accounts_env):
        accounts = load_accounts()
        default = next(a for a in accounts if a["id"] == "default")
        assert default["niche"] == "skincare"


class TestGetAccount:
    def test_get_default(self, accounts_env):
        load_accounts()  # ensure default exists
        account = get_account("default")
        assert account is not None
        assert account["id"] == "default"

    def test_get_nonexistent(self, accounts_env):
        load_accounts()
        assert get_account("nonexistent") is None


class TestCreateAccount:
    def test_creates_account_with_id(self, accounts_env):
        account = create_account("Test Niche", "fitness")
        assert account["name"] == "Test Niche"
        assert account["niche"] == "fitness"
        assert account["is_default"] is False
        assert len(account["id"]) == 12

    def test_creates_directory_tree(self, accounts_env):
        account = create_account("Test", "beauty")
        paths = get_account_paths(account["id"])
        for p in paths.values():
            assert p.exists()

    def test_creates_config_file(self, accounts_env):
        account = create_account("Test", "cooking")
        config = get_account_config(account["id"])
        assert config["niche"] == "cooking"

    def test_appears_in_registry(self, accounts_env):
        account = create_account("New", "pets")
        accounts = load_accounts()
        assert any(a["id"] == account["id"] for a in accounts)

    def test_multiple_accounts(self, accounts_env):
        create_account("Acct1", "niche1")
        create_account("Acct2", "niche2")
        accounts = load_accounts()
        # default + 2 created
        assert len(accounts) == 3


class TestUpdateAccount:
    def test_update_name(self, accounts_env):
        account = create_account("Old Name", "niche")
        updated = update_account(account["id"], {"name": "New Name"})
        assert updated["name"] == "New Name"

    def test_update_niche(self, accounts_env):
        account = create_account("Test", "old")
        updated = update_account(account["id"], {"niche": "new"})
        assert updated["niche"] == "new"

    def test_update_nonexistent_returns_none(self, accounts_env):
        load_accounts()
        assert update_account("nonexistent", {"name": "X"}) is None

    def test_cannot_change_id(self, accounts_env):
        account = create_account("Test", "niche")
        original_id = account["id"]
        updated = update_account(original_id, {"id": "hacked"})
        assert updated["id"] == original_id

    def test_persists_to_disk(self, accounts_env):
        account = create_account("Test", "niche")
        update_account(account["id"], {"name": "Updated"})
        # Re-read from disk
        reloaded = get_account(account["id"])
        assert reloaded["name"] == "Updated"


class TestDeleteAccount:
    def test_delete_existing(self, accounts_env):
        account = create_account("ToDelete", "niche")
        assert delete_account(account["id"]) is True
        assert get_account(account["id"]) is None

    def test_delete_removes_directory(self, accounts_env):
        account = create_account("ToDelete", "niche")
        account_dir = accounts_env["dir"] / account["id"]
        assert account_dir.exists()
        delete_account(account["id"])
        assert not account_dir.exists()

    def test_cannot_delete_default(self, accounts_env):
        load_accounts()
        assert delete_account("default") is False
        assert get_account("default") is not None

    def test_delete_nonexistent(self, accounts_env):
        load_accounts()
        assert delete_account("nonexistent") is False


# ── Path resolution ─────────────────────────────────────────────────────────


class TestAccountPaths:
    def test_default_uses_global_dirs(self):
        """Default account maps to existing top-level directories."""
        from src.utils.config import DATA_RAW_DIR, DATA_SCRIPTS_DIR, OUTPUT_DIR
        paths = get_account_paths("default")
        assert paths["data_raw_dir"] == DATA_RAW_DIR
        assert paths["data_scripts_dir"] == DATA_SCRIPTS_DIR
        assert paths["output_dir"] == OUTPUT_DIR

    def test_non_default_uses_subdirs(self, accounts_env):
        paths = get_account_paths("abc123")
        assert "abc123" in str(paths["data_raw_dir"])
        assert "abc123" in str(paths["output_dir"])

    def test_all_six_paths_present(self):
        paths = get_account_paths("any_id")
        expected_keys = {
            "data_raw_dir", "data_processed_dir", "data_scripts_dir",
            "output_dir", "output_images_dir", "output_clips_dir",
        }
        assert set(paths.keys()) == expected_keys


# ── Per-account config ──────────────────────────────────────────────────────


class TestAccountConfig:
    def test_default_reads_root_config(self, accounts_env):
        config = get_account_config("default")
        assert config["niche"] == "skincare"

    def test_save_and_load_config(self, accounts_env):
        account = create_account("Test", "niche")
        new_config = {"niche": "fitness", "search_queries": ["gym workout"]}
        save_account_config(account["id"], new_config)
        loaded = get_account_config(account["id"])
        assert loaded["niche"] == "fitness"
        assert loaded["search_queries"] == ["gym workout"]

    def test_save_default_config(self, accounts_env):
        save_account_config("default", {"niche": "updated"})
        # Read the file directly since load_pipeline_config uses its own path
        config_path = accounts_env["tmp"] / "pipeline_config.json"
        with open(config_path, "r") as f:
            config = json.load(f)
        assert config["niche"] == "updated"

    def test_missing_config_falls_back(self, accounts_env):
        """Non-existent account config falls back to root config."""
        config = get_account_config("nonexistent_id")
        assert config["niche"] == "skincare"
