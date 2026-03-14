"""Tests for the content queue service."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.dashboard.queue_service import (
    load_queue,
    add_to_queue,
    update_queue_item,
    remove_from_queue,
    get_week_view,
    _queue_path,
    _save_queue,
)


@pytest.fixture
def queue_env(tmp_path):
    """Patch queue path to use tmp_path."""
    with patch("src.dashboard.queue_service.PROJECT_ROOT", tmp_path), \
         patch("src.dashboard.queue_service.DATA_ACCOUNTS_DIR", tmp_path / "accounts"):
        (tmp_path / "data").mkdir()
        (tmp_path / "accounts").mkdir()
        yield tmp_path


class TestLoadQueue:
    def test_empty_when_no_file(self, queue_env):
        assert load_queue("default") == []

    def test_loads_saved_data(self, queue_env):
        data = [{"queue_id": "test1", "status": "draft"}]
        _save_queue("default", data)
        assert load_queue("default") == data


class TestAddToQueue:
    def test_adds_item(self, queue_env):
        item = add_to_queue("default", script_id="abc123", scheduled_date="2026-03-15")
        assert item["script_id"] == "abc123"
        assert item["status"] == "scheduled"
        assert len(item["queue_id"]) == 12

    def test_draft_when_no_date(self, queue_env):
        item = add_to_queue("default", script_id="abc123")
        assert item["status"] == "draft"

    def test_persists_to_disk(self, queue_env):
        add_to_queue("default", script_id="test1")
        add_to_queue("default", script_id="test2")
        queue = load_queue("default")
        assert len(queue) == 2

    def test_hook_preview_stored(self, queue_env):
        item = add_to_queue("default", script_id="x", hook_preview="Stop scrolling!")
        assert item["hook_preview"] == "Stop scrolling!"


class TestUpdateQueueItem:
    def test_updates_date(self, queue_env):
        item = add_to_queue("default", script_id="abc")
        updated = update_queue_item("default", item["queue_id"], {"scheduled_date": "2026-04-01"})
        assert updated["scheduled_date"] == "2026-04-01"
        assert updated["status"] == "scheduled"

    def test_updates_status(self, queue_env):
        item = add_to_queue("default", script_id="abc", scheduled_date="2026-03-15")
        updated = update_queue_item("default", item["queue_id"], {"status": "posted"})
        assert updated["status"] == "posted"

    def test_returns_none_for_missing(self, queue_env):
        assert update_queue_item("default", "nonexistent", {"status": "done"}) is None


class TestRemoveFromQueue:
    def test_removes_item(self, queue_env):
        item = add_to_queue("default", script_id="abc")
        assert remove_from_queue("default", item["queue_id"]) is True
        assert load_queue("default") == []

    def test_returns_false_for_missing(self, queue_env):
        assert remove_from_queue("default", "nonexistent") is False


class TestWeekView:
    def test_returns_7_days(self, queue_env):
        week = get_week_view("default")
        assert len(week) == 7

    def test_items_placed_in_correct_day(self, queue_env):
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        target_date = monday + timedelta(days=2)  # Wednesday

        add_to_queue("default", script_id="abc", scheduled_date=target_date.isoformat())
        week = get_week_view("default", monday)
        assert len(week[target_date.isoformat()]) == 1

    def test_custom_start_date(self, queue_env):
        start = datetime(2026, 3, 16)  # A Monday
        week = get_week_view("default", start)
        dates = list(week.keys())
        assert dates[0] == "2026-03-16"
        assert dates[6] == "2026-03-22"

    def test_empty_days(self, queue_env):
        week = get_week_view("default")
        for items in week.values():
            assert items == []
