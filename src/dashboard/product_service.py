"""product_service.py — Product status tracking per account.

Cross-references scraped products with scripts, images, videos, and queue
to show pipeline progress for each product.
"""

from pathlib import Path

from src.dashboard.accounts import get_account_paths
from src.dashboard.queue_service import load_queue
from src.utils.data_io import list_data_files, load_json


def list_products(account_id: str) -> list[dict]:
    """Load latest product data for an account."""
    paths = get_account_paths(account_id)
    raw_dir = paths["data_raw_dir"]

    files = list_data_files(raw_dir, "products")
    if not files:
        return []

    data = load_json(files[0])
    if not isinstance(data, list):
        return []

    return data


def get_product_status(account_id: str) -> list[dict]:
    """Cross-reference products with scripts/videos to get pipeline status.

    Returns list of dicts with: product info + has_script, has_images, has_video, is_queued.
    """
    products = list_products(account_id)
    if not products:
        return []

    paths = get_account_paths(account_id)

    # Build product_id → script_id mapping from script files
    product_to_script: dict[str, str] = {}
    scripts_with_product: set[str] = set()
    scripts_dir = paths["data_scripts_dir"]
    for f in list_data_files(scripts_dir, "scripts"):
        data = load_json(f)
        if isinstance(data, list):
            for s in data:
                pid = s.get("product_id", "")
                sid = s.get("script_id", "")
                if pid:
                    product_to_script[pid] = sid
                    scripts_with_product.add(pid)

    # Gather images — check both script-based dirs and product image files
    images_dir = paths["output_images_dir"]
    image_script_ids: set[str] = set()
    if images_dir.exists():
        image_script_ids = {p.name for p in images_dir.iterdir() if p.is_dir()}

    # Gather videos — match by script_id[:8] in filename
    output_dir = paths["output_dir"]
    video_stems: set[str] = set()
    if output_dir.exists():
        video_stems = {p.stem.split("_")[0] for p in output_dir.glob("*.mp4")}

    # Queue
    queue = load_queue(account_id)
    queued_scripts = {item.get("script_id", "") for item in queue}

    result = []
    for product in products:
        pid = str(product.get("id", product.get("product_id", "")))
        name = product.get("name", product.get("product_name", "Unknown"))

        # Chain: product_id → script_id → video/image lookup
        script_id = product_to_script.get(pid, "")
        short_sid = script_id[:8] if script_id else ""

        has_video = short_sid in video_stems if short_sid else False
        # Also check if video is named with product_id directly (new naming)
        if not has_video:
            has_video = any(pid in stem for stem in video_stems) if pid else False

        has_images = short_sid in image_script_ids if short_sid else False

        status = {
            **product,
            "product_id": pid,
            "product_name": name,
            "has_script": pid in scripts_with_product,
            "has_images": has_images,
            "has_video": has_video,
            "is_queued": script_id in queued_scripts if script_id else False,
        }
        result.append(status)

    return result


def get_product_stats(account_id: str) -> dict:
    """Aggregate product pipeline stats."""
    statuses = get_product_status(account_id)
    total = len(statuses)
    with_video = sum(1 for s in statuses if s["has_video"])
    needs_video = total - with_video

    return {
        "total": total,
        "with_video": with_video,
        "needs_video": needs_video,
    }
