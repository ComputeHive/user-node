"""
infrastructure/storage/local_index.py – Per-file shard index for dev/local mode.

Replaces the module-level functions in utils/local_storage.py with a
class that owns its own state and requires no global variables.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class LocalIndex:
    """Manages the JSON index files that track locally stored shards."""

    _INDEX_SUFFIX = ".index.json"

    def __init__(self, host_dir: str) -> None:
        os.makedirs(host_dir, exist_ok=True)
        self._host_dir = host_dir

    # ------------------------------------------------------------------
    # Index I/O
    # ------------------------------------------------------------------

    def _index_path(self, filename: str) -> str:
        return os.path.join(self._host_dir, f"{filename}{self._INDEX_SUFFIX}")

    def load(self, filename: str) -> tuple[dict | None, list | None]:
        """Return ``(meta, segments)``, supporting both legacy and current format."""
        path = self._index_path(filename)
        if not os.path.exists(path):
            return None, None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "segments" in data:
            meta = data.get("meta") or {}
            meta.setdefault("filename", filename)
            return meta, data["segments"]

        if isinstance(data, list):
            meta = {
                "filename": filename,
                "file_size": self._estimate_file_size(data),
                "download_count": 0,
            }
            return meta, data

        return None, None

    def save(self, filename: str, meta: dict, segments: list) -> None:
        payload = {
            "meta": {
                "filename": filename,
                "file_size": meta.get("file_size", self._estimate_file_size(segments)),
                "download_count": meta.get("download_count", 0),
            },
            "segments": segments,
        }
        with open(self._index_path(filename), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    def list_files(self) -> list[dict[str, Any]]:
        """Return metadata for all locally stored files."""
        files: list[dict[str, Any]] = []
        for name in os.listdir(self._host_dir):
            if not name.endswith(self._INDEX_SUFFIX):
                continue
            fname = name[: -len(self._INDEX_SUFFIX)]
            meta, segments = self.load(fname)
            if not segments:
                continue
            meta = meta or {}
            files.append({
                "filename": meta.get("filename", fname),
                "size": meta.get("file_size", self._estimate_file_size(segments)),
                "download_count": meta.get("download_count", 0),
            })
        files.sort(key=lambda x: x["filename"].lower())
        return files

    def update_shard(
        self,
        original_filename: str,
        request: dict,
        shard_name: str,
        shard_size: int,
        transfer_obj: dict | None,
    ) -> None:
        """Merge one uploaded shard into the index."""
        meta, segments = self.load(original_filename)
        if segments is None:
            segments = []
        if meta is None:
            meta = {"filename": original_filename, "file_size": 0, "download_count": 0}

        seg_no = request.get("segment_number", 0)
        shard_no = request.get("shard_index", 0)

        while len(segments) <= seg_no:
            segments.append({"shards": [], "k": 0, "m": 0, "shard_size": 0})

        seg = segments[seg_no]
        entry = {
            "shard_id": shard_name,
            "shard_no": shard_no,
            "segment_no": seg_no,
            "ip_address": "127.0.0.1",
            "port": 5555 + shard_no,
            "auth": "dev_auth_key",
        }

        replaced = any(
            (s["shard_no"] == shard_no and (seg["shards"].__setitem__(i, entry) or True))
            for i, s in enumerate(seg["shards"])
        )
        if not replaced:
            seg["shards"].append(entry)

        if transfer_obj and transfer_obj.get("segments") and len(transfer_obj["segments"]) > seg_no:
            src = transfer_obj["segments"][seg_no]
            seg["k"] = src.get("k", 2)
            seg["m"] = src.get("m", 3)
            seg["shard_size"] = src.get("shard_size", shard_size)

        if transfer_obj and transfer_obj.get("total_size_to_upload"):
            meta["file_size"] = transfer_obj.get("file_size") or meta.get("file_size", 0)
        if not meta.get("file_size"):
            meta["file_size"] = self._estimate_file_size(segments)

        self.save(original_filename, meta, segments)

    def register_completed_upload(self, filename: str, transfer_obj: dict | None) -> None:
        """Finalize index metadata after a full file upload completes."""
        meta, segments = self.load(filename)
        if segments is None:
            return
        if meta is None:
            meta = {"filename": filename, "download_count": 0}

        if transfer_obj:
            file_path = transfer_obj.get("file_path")
            if file_path and os.path.exists(file_path):
                meta["file_size"] = os.path.getsize(file_path)
            elif transfer_obj.get("total_size_to_upload"):
                meta["file_size"] = transfer_obj["total_size_to_upload"]

        self.save(filename, meta, segments)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_file_size(segments: list) -> int:
        total = 0
        for seg in segments:
            k = seg.get("k") or 2
            m = seg.get("m") or len(seg.get("shards", [])) or k
            total += (seg.get("shard_size") or 0) * m
        return total
