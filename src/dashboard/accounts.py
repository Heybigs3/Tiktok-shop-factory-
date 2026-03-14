"""accounts.py — Multi-account management with path resolution.

Each account gets isolated directories for data and output. The "default"
account maps to the existing top-level dirs (backward-compatible, no file moves).
New accounts get subdirectories under data/accounts/{id}/.

Account registry lives at data/accounts.json.
"""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.utils.config import (
    ACCOUNTS_FILE,
    DATA_ACCOUNTS_DIR,
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    DATA_SCRIPTS_DIR,
    OUTPUT_DIR,
    OUTPUT_IMAGES_DIR,
    OUTPUT_CLIPS_DIR,
    PIPELINE_CONFIG_PATH,
    PROJECT_ROOT,
    load_pipeline_config,
)


# ── Registry I/O ────────────────────────────────────────────────────────────

def _read_registry() -> list[dict]:
    """Read accounts.json. Returns empty list if missing."""
    if not ACCOUNTS_FILE.exists():
        return []
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_registry(accounts: list[dict]) -> None:
    """Write accounts list to accounts.json."""
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)


def _ensure_default() -> list[dict]:
    """Auto-create the default account on first run (migration)."""
    accounts = _read_registry()
    if any(a["id"] == "default" for a in accounts):
        return accounts

    default = {
        "id": "default",
        "name": "Default",
        "niche": load_pipeline_config().get("niche", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_default": True,
    }
    accounts.insert(0, default)
    _write_registry(accounts)
    return accounts


# ── CRUD ─────────────────────────────────────────────────────────────────────

def load_accounts() -> list[dict]:
    """Load all accounts. Auto-creates default on first call."""
    return _ensure_default()


def get_account(account_id: str) -> dict | None:
    """Get a single account by ID."""
    accounts = load_accounts()
    for a in accounts:
        if a["id"] == account_id:
            return a
    return None


def create_account(name: str, niche: str = "") -> dict:
    """Create a new account with its own directory tree and config."""
    accounts = load_accounts()
    account_id = uuid.uuid4().hex[:12]

    account = {
        "id": account_id,
        "name": name,
        "niche": niche,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_default": False,
    }

    # Create directory tree
    paths = get_account_paths(account_id)
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    # Copy root pipeline_config.json as template, update niche
    config = load_pipeline_config()
    if niche:
        config["niche"] = niche
    save_account_config(account_id, config)

    accounts.append(account)
    _write_registry(accounts)
    return account


def update_account(account_id: str, updates: dict) -> dict | None:
    """Update account fields. Returns updated account or None if not found."""
    accounts = load_accounts()
    for a in accounts:
        if a["id"] == account_id:
            # Don't allow changing id or is_default
            for key in ("name", "niche"):
                if key in updates:
                    a[key] = updates[key]
            _write_registry(accounts)
            return a
    return None


def delete_account(account_id: str) -> bool:
    """Delete an account. Blocks deletion of the default account."""
    if account_id == "default":
        return False

    accounts = load_accounts()
    original_len = len(accounts)
    accounts = [a for a in accounts if a["id"] != account_id]

    if len(accounts) == original_len:
        return False  # Not found

    _write_registry(accounts)

    # Remove account directory tree
    account_dir = DATA_ACCOUNTS_DIR / account_id
    if account_dir.exists():
        shutil.rmtree(account_dir, ignore_errors=True)

    return True


# ── Path resolution ──────────────────────────────────────────────────────────

def get_account_paths(account_id: str) -> dict[str, Path]:
    """Return directory paths for an account.

    Default account → existing global paths (backward-compatible).
    Other accounts → isolated subdirs under data/accounts/{id}/.
    """
    if account_id == "default":
        return {
            "data_raw_dir": DATA_RAW_DIR,
            "data_processed_dir": DATA_PROCESSED_DIR,
            "data_scripts_dir": DATA_SCRIPTS_DIR,
            "output_dir": OUTPUT_DIR,
            "output_images_dir": OUTPUT_IMAGES_DIR,
            "output_clips_dir": OUTPUT_CLIPS_DIR,
        }

    base = DATA_ACCOUNTS_DIR / account_id
    return {
        "data_raw_dir": base / "raw",
        "data_processed_dir": base / "processed",
        "data_scripts_dir": base / "scripts",
        "output_dir": base / "output" / "videos",
        "output_images_dir": base / "output" / "images",
        "output_clips_dir": base / "output" / "clips",
    }


# ── Per-account config ───────────────────────────────────────────────────────

def get_account_config(account_id: str) -> dict:
    """Load per-account pipeline_config.json. Default account uses root config."""
    if account_id == "default":
        return load_pipeline_config()

    config_path = DATA_ACCOUNTS_DIR / account_id / "pipeline_config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return load_pipeline_config()


def save_account_config(account_id: str, config: dict) -> None:
    """Save per-account pipeline_config.json. Default account saves to root."""
    if account_id == "default":
        config_path = PIPELINE_CONFIG_PATH
    else:
        config_dir = DATA_ACCOUNTS_DIR / account_id
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "pipeline_config.json"

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
