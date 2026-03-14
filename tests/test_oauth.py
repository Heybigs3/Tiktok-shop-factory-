"""Tests for src.publishers.oauth_server — token persistence and expiry logic."""

import json
import time

import pytest


# ── Token expiry (pure function) ──

class TestTokenExpiry:
    """is_token_expired() checks saved_at + expires_in against current time."""

    def test_not_expired(self):
        from src.publishers.oauth_server import is_token_expired

        token = {"saved_at": time.time(), "expires_in": 86400}
        assert is_token_expired(token) is False

    def test_expired(self):
        from src.publishers.oauth_server import is_token_expired

        token = {"saved_at": time.time() - 90000, "expires_in": 86400}
        assert is_token_expired(token) is True

    def test_within_buffer(self):
        """Token within the 5-minute buffer should count as expired."""
        from src.publishers.oauth_server import is_token_expired

        # 200 seconds left — inside the 300-second buffer
        token = {"saved_at": time.time() - 86200, "expires_in": 86400}
        assert is_token_expired(token) is True

    def test_missing_saved_at(self):
        """No saved_at defaults to 0 → always expired."""
        from src.publishers.oauth_server import is_token_expired

        token = {"expires_in": 86400}
        assert is_token_expired(token) is True


# ── Save / load round-trip ──

class TestSaveLoadToken:
    """_save_token and load_token persist to disk via TOKEN_FILE."""

    def test_roundtrip(self, tmp_path, monkeypatch):
        import src.publishers.oauth_server as oauth

        monkeypatch.setattr(oauth, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(oauth, "TOKEN_FILE", tmp_path / "tiktok_token.json")

        token = {"access_token": "abc123", "refresh_token": "xyz789", "expires_in": 86400}
        oauth._save_token(token)

        loaded = oauth.load_token()
        assert loaded["access_token"] == "abc123"
        assert loaded["refresh_token"] == "xyz789"

    def test_saved_at_added(self, tmp_path, monkeypatch):
        import src.publishers.oauth_server as oauth

        monkeypatch.setattr(oauth, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(oauth, "TOKEN_FILE", tmp_path / "tiktok_token.json")

        oauth._save_token({"access_token": "test"})
        loaded = oauth.load_token()
        assert "saved_at" in loaded
        assert isinstance(loaded["saved_at"], float)

    def test_load_nonexistent(self, tmp_path, monkeypatch):
        import src.publishers.oauth_server as oauth

        monkeypatch.setattr(oauth, "TOKEN_FILE", tmp_path / "nope.json")
        assert oauth.load_token() is None

    def test_load_corrupt(self, tmp_path, monkeypatch):
        import src.publishers.oauth_server as oauth

        bad_file = tmp_path / "tiktok_token.json"
        bad_file.write_text("{not valid json!!")
        monkeypatch.setattr(oauth, "TOKEN_FILE", bad_file)
        assert oauth.load_token() is None


# ── get_valid_token orchestration ──

class TestGetValidToken:

    def test_valid_returned(self, monkeypatch):
        import src.publishers.oauth_server as oauth

        fresh = {"access_token": "good", "saved_at": time.time(), "expires_in": 86400}
        monkeypatch.setattr(oauth, "load_token", lambda: fresh)
        result = oauth.get_valid_token()
        assert result["access_token"] == "good"

    def test_expired_triggers_refresh(self, monkeypatch):
        import src.publishers.oauth_server as oauth

        expired = {"access_token": "old", "refresh_token": "rt", "saved_at": 0, "expires_in": 1}
        refreshed = {"access_token": "new", "saved_at": time.time(), "expires_in": 86400}

        monkeypatch.setattr(oauth, "load_token", lambda: expired)
        monkeypatch.setattr(oauth, "refresh_access_token", lambda _: refreshed)
        result = oauth.get_valid_token()
        assert result["access_token"] == "new"

    def test_no_token_returns_none(self, monkeypatch):
        import src.publishers.oauth_server as oauth

        monkeypatch.setattr(oauth, "load_token", lambda: None)
        assert oauth.get_valid_token() is None
