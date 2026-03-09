"""Tests for src/utils/data_io — JSON save/load round-trips with tmp_path."""

import re
import time

from src.utils.data_io import list_data_files, load_json, load_latest, save_json


class TestSaveLoad:
    """Round-trip save and load."""

    def test_roundtrip(self, tmp_data_dir):
        data = [{"key": "value", "num": 42}]
        path = save_json(data, "test", tmp_data_dir)
        loaded = load_json(path)
        assert loaded == data

    def test_timestamped_filename(self, tmp_data_dir):
        path = save_json([], "myprefix", tmp_data_dir)
        pattern = r"^myprefix_\d{4}-\d{2}-\d{2}_\d{6}\.json$"
        assert re.match(pattern, path.name), f"Filename {path.name!r} doesn't match expected pattern"


class TestListAndLatest:
    """Filtering and latest-file logic."""

    def test_list_filters_by_prefix(self, tmp_data_dir):
        save_json([], "alpha", tmp_data_dir)
        time.sleep(1.1)  # ensure different timestamp
        save_json([], "alpha", tmp_data_dir)
        save_json([], "beta", tmp_data_dir)
        assert len(list_data_files(tmp_data_dir, "alpha")) == 2

    def test_load_latest_returns_newest(self, tmp_data_dir):
        save_json([{"v": 1}], "data", tmp_data_dir)
        time.sleep(1.1)  # ensure different timestamp
        save_json([{"v": 2}], "data", tmp_data_dir)
        latest = load_latest(tmp_data_dir, "data")
        assert latest == [{"v": 2}]

    def test_load_latest_no_match(self, tmp_data_dir):
        result = load_latest(tmp_data_dir, "nonexistent")
        assert result is None
