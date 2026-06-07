"""
core/paths.py – All filesystem paths as a single, injected value object.

No logic lives here. Constructing AppPaths does not touch the disk.
Use infrastructure.filesystem.ensure_filesystem(paths) to create the
directories and seed files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppPaths:
    # Directories
    shards_dir: str
    segments_dir: str
    download_output_dir: str
    encryption_dir: str
    dev_host_dir: str
    cache_dir: str

    # Cache files
    cache_file: str
    upload_transfer_file: str
    download_transfer_file: str
    connections_file: str

    # Assets
    icon_path: str

    @classmethod
    def from_base(cls, base: str | None = None) -> "AppPaths":
        """Build standard paths relative to *base* (defaults to ``data/``)."""
        root = os.path.realpath(base or "data")
        cache_dir = os.path.join(root, "cache")
        return cls(
            shards_dir=os.path.join(root, "shards"),
            segments_dir=os.path.join(root, "segments"),
            download_output_dir=os.path.join(root, "downloaded data"),
            encryption_dir=os.path.join(root, "encrypted"),
            dev_host_dir=os.path.join(root, "dev_host"),
            cache_dir=cache_dir,
            cache_file=os.path.join(cache_dir, "cera_cache"),
            upload_transfer_file=os.path.join(cache_dir, "cera_transfer.json"),
            download_transfer_file=os.path.join(cache_dir, "download_cera_transfer.json"),
            connections_file=os.path.join(cache_dir, "connections.txt"),
            icon_path=os.path.realpath("gui/resources/cera_icon.png"),
        )
