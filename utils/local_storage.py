"""
Local stand-in for storage nodes when LOCAL_MODE is enabled.

Shards are copied to data/dev_host/ instead of ZMQ upload. Per-file indices
(data/dev_host/<filename>.index.json) drive dev-mode downloads and the file list.
"""

from __future__ import annotations

import json
import os
from typing import Any


def dev_host_dir() -> str:
    path = os.path.join(os.path.realpath("data"), "dev_host")
    os.makedirs(path, exist_ok=True)
    return path


def index_path(filename: str) -> str:
    return os.path.join(dev_host_dir(), f"{filename}.index.json")


def _estimate_file_size(segments: list) -> int:
    total = 0
    for seg in segments:
        k = seg.get("k") or 2
        m = seg.get("m") or len(seg.get("shards", [])) or k
        shard_size = seg.get("shard_size") or 0
        total += shard_size * m
    return total


def load_index(filename: str) -> tuple[dict | None, list | None]:
    """
    Return (meta, segments). Supports legacy list-only index files.
    """
    path = index_path(filename)
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
            "file_size": _estimate_file_size(data),
            "download_count": 0,
        }
        return meta, data

    return None, None


def save_index(filename: str, meta: dict, segments: list) -> None:
    payload = {
        "meta": {
            "filename": filename,
            "file_size": meta.get("file_size", _estimate_file_size(segments)),
            "download_count": meta.get("download_count", 0),
        },
        "segments": segments,
    }
    with open(index_path(filename), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def list_stored_files() -> list[dict[str, Any]]:
    """Files that were uploaded in local mode (have an index in dev_host)."""
    host = dev_host_dir()
    files: list[dict[str, Any]] = []

    for name in os.listdir(host):
        if not name.endswith(".index.json"):
            continue
        filename = name[: -len(".index.json")]
        meta, segments = load_index(filename)
        if not segments:
            continue
        meta = meta or {}
        files.append({
            "filename": meta.get("filename", filename),
            "size": meta.get("file_size", _estimate_file_size(segments)),
            "download_count": meta.get("download_count", 0),
        })

    files.sort(key=lambda x: x["filename"].lower())
    return files


def update_shard_in_index(
    original_filename: str,
    request: dict,
    shard_name: str,
    shard_size: int,
    transfer_obj: dict | None,
) -> None:
    """Merge one uploaded shard into the per-file index."""
    meta, segments = load_index(original_filename)
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

    replaced = False
    for i, s in enumerate(seg["shards"]):
        if s.get("shard_no") == shard_no:
            seg["shards"][i] = entry
            replaced = True
            break
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
        meta["file_size"] = _estimate_file_size(segments)

    save_index(original_filename, meta, segments)


def register_completed_upload(filename: str, transfer_obj: dict | None) -> None:
    """Finalize index metadata after a full file upload."""
    meta, segments = load_index(filename)
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

    save_index(filename, meta, segments)
