"""Tests for the product service."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.dashboard.product_service import (
    list_products,
    get_product_status,
    get_product_stats,
)
from src.dashboard.accounts import get_account_paths


@pytest.fixture
def product_env(tmp_path):
    """Set up fake account paths with product data."""
    raw_dir = tmp_path / "raw"
    scripts_dir = tmp_path / "scripts"
    output_dir = tmp_path / "output" / "videos"
    images_dir = tmp_path / "output" / "images"
    clips_dir = tmp_path / "output" / "clips"

    for d in [raw_dir, scripts_dir, output_dir, images_dir, clips_dir]:
        d.mkdir(parents=True)

    paths = {
        "data_raw_dir": raw_dir,
        "data_processed_dir": tmp_path / "processed",
        "data_scripts_dir": scripts_dir,
        "output_dir": output_dir,
        "output_images_dir": images_dir,
        "output_clips_dir": clips_dir,
    }

    with patch("src.dashboard.product_service.get_account_paths", return_value=paths), \
         patch("src.dashboard.product_service.load_queue", return_value=[]):
        yield {
            "paths": paths,
            "raw_dir": raw_dir,
            "scripts_dir": scripts_dir,
            "output_dir": output_dir,
            "images_dir": images_dir,
        }


class TestListProducts:
    def test_empty_when_no_files(self, product_env):
        assert list_products("default") == []

    def test_loads_products(self, product_env):
        products = [
            {"id": "p1", "name": "Vitamin C Serum"},
            {"id": "p2", "name": "Moisturizer"},
        ]
        (product_env["raw_dir"] / "products_2026-03-12_120000.json").write_text(
            json.dumps(products), encoding="utf-8"
        )
        result = list_products("default")
        assert len(result) == 2
        assert result[0]["name"] == "Vitamin C Serum"


class TestProductStatus:
    def test_status_with_no_scripts_or_videos(self, product_env):
        products = [{"id": "p1", "name": "Serum"}]
        (product_env["raw_dir"] / "products_2026-03-12_120000.json").write_text(
            json.dumps(products), encoding="utf-8"
        )
        statuses = get_product_status("default")
        assert len(statuses) == 1
        assert statuses[0]["has_script"] is False
        assert statuses[0]["has_video"] is False
        assert statuses[0]["is_queued"] is False

    def test_status_with_matching_script_and_video(self, product_env):
        """Video found via product_id → script_id → video filename chain."""
        products = [{"id": "p1", "name": "Serum"}]
        (product_env["raw_dir"] / "products_2026-03-12_120000.json").write_text(
            json.dumps(products), encoding="utf-8"
        )
        # Create a script with product_id linkage
        scripts = [{"script_id": "abc12345-0000-0000-0000-000000000000", "product_id": "p1"}]
        (product_env["scripts_dir"] / "scripts_2026-03-12_120000.json").write_text(
            json.dumps(scripts), encoding="utf-8"
        )
        # Create a video named by script_id[:8]
        (product_env["output_dir"] / "abc12345_p1.mp4").write_bytes(b"\x00" * 100)

        statuses = get_product_status("default")
        assert statuses[0]["has_script"] is True
        assert statuses[0]["has_video"] is True

    def test_status_with_matching_image(self, product_env):
        """Images found via product_id → script_id → image directory."""
        products = [{"id": "p1", "name": "Serum"}]
        (product_env["raw_dir"] / "products_2026-03-12_120000.json").write_text(
            json.dumps(products), encoding="utf-8"
        )
        # Create a script with product_id linkage
        scripts = [{"script_id": "abc12345-0000-0000-0000-000000000000", "product_id": "p1"}]
        (product_env["scripts_dir"] / "scripts_2026-03-12_120000.json").write_text(
            json.dumps(scripts), encoding="utf-8"
        )
        # Create an image directory named by script_id[:8]
        img_dir = product_env["images_dir"] / "abc12345"
        img_dir.mkdir()
        (img_dir / "scene_00.png").write_bytes(b"\x00" * 100)

        statuses = get_product_status("default")
        assert statuses[0]["has_images"] is True


class TestProductStats:
    def test_empty_stats(self, product_env):
        stats = get_product_stats("default")
        assert stats == {"total": 0, "with_video": 0, "needs_video": 0}

    def test_stats_with_products(self, product_env):
        products = [
            {"id": "p1", "name": "Serum"},
            {"id": "p2", "name": "Cream"},
        ]
        (product_env["raw_dir"] / "products_2026-03-12_120000.json").write_text(
            json.dumps(products), encoding="utf-8"
        )
        # Create a script linking product to video
        scripts = [{"script_id": "abc12345-0000-0000-0000-000000000000", "product_id": "p1"}]
        (product_env["scripts_dir"] / "scripts_2026-03-12_120000.json").write_text(
            json.dumps(scripts), encoding="utf-8"
        )
        (product_env["output_dir"] / "abc12345_p1.mp4").write_bytes(b"\x00" * 100)

        stats = get_product_stats("default")
        assert stats["total"] == 2
        assert stats["with_video"] == 1
        assert stats["needs_video"] == 1
