"""
infrastructure/filesystem.py – Disk bootstrap and cleanup utilities.

All filesystem side-effects are isolated here.  The rest of the app
works with path strings and calls these functions explicitly.
"""

from __future__ import annotations

import glob
import json
import logging
import os

from core.paths import AppPaths

logger = logging.getLogger(__name__)


def ensure_filesystem(paths: AppPaths) -> None:
    """Create required directories and seed cache files if absent."""
    _ensure_directories(paths)
    _ensure_cache_files(paths)


def _ensure_directories(paths: AppPaths) -> None:
    dirs = [
        paths.shards_dir,
        paths.segments_dir,
        paths.download_output_dir,
        paths.encryption_dir,
        paths.dev_host_dir,
        paths.cache_dir,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def _ensure_cache_files(paths: AppPaths) -> None:
    for file_path in (
        paths.cache_file,
        paths.upload_transfer_file,
        paths.download_transfer_file,
        paths.connections_file,
    ):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if not os.path.exists(file_path):
            _seed_cache_file(file_path)
        elif file_path == paths.connections_file:
            _repair_connections_file(file_path)


def _seed_cache_file(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        if path.endswith("connections.txt"):
            json.dump({"connections": []}, f)


def _repair_connections_file(path: str) -> None:
    """Overwrite the connections file if it contains invalid JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            json.load(f)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Repairing corrupt connections file: %s", path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"connections": []}, f)


# ---------------------------------------------------------------------------
# Cleanup helpers (called between upload/download operations)
# ---------------------------------------------------------------------------

def clear_directory(directory: str) -> None:
    """Delete all files inside *directory* (non-recursive)."""
    for path in glob.glob(os.path.join(directory, "*")):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def clear_segments_and_encrypted(paths: AppPaths) -> None:
    clear_directory(paths.segments_dir)
    clear_directory(paths.encryption_dir)


def clear_shards(paths: AppPaths) -> None:
    clear_directory(paths.shards_dir)
