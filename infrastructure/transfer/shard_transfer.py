"""
infrastructure/transfer/shard_transfer.py – Shard-level send/receive.

Wraps the ZMQ upload/download (production) and local file-copy (dev).
No globals, no UI coupling.
"""

from __future__ import annotations

import logging
import os
import pickle
import threading
import zmq

from config import settings
from infrastructure.storage.local_index import LocalIndex
from utils.audits import generate_audits

logger = logging.getLogger(__name__)


class ShardTransfer:

    def __init__(self, paths, semaphore: threading.Semaphore, api_client, token_repo) -> None:
        self._paths = paths
        self._semaphore = semaphore
        self._api = api_client
        self._token_repo = token_repo

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def send(
        self,
        shard_path: str,
        shard_info: dict,
        segment_num: int,
        shard_index: int,
        shard_size: int,
        token: str,
        progress_callback,
        transfer_obj: dict,
    ) -> None:
        if settings.BYPASS_UPLOAD:
            self._dev_send(shard_path, shard_info, segment_num, shard_index, shard_size, transfer_obj, progress_callback)
            return

        self._zmq_send(shard_path, shard_info, token, progress_callback)

    def _dev_send(
        self, shard_path, shard_info, segment_num, shard_index, shard_size, transfer_obj, progress_callback
    ) -> None:
        index = LocalIndex(self._paths.dev_host_dir)
        shard_name = os.path.basename(shard_path)
        dst = os.path.join(self._paths.dev_host_dir, shard_name)

        # Figure out the original filename from the transfer object
        original_filename = os.path.basename(transfer_obj.get("file_path", "unknown"))
        with open(shard_path, "rb") as src_f:
            data = src_f.read()
        with open(dst, "wb") as dst_f:
            dst_f.write(data)

        index.update_shard(
            original_filename=original_filename,
            request={"segment_number": segment_num, "shard_index": shard_index},
            shard_name=shard_name,
            shard_size=shard_size,
            transfer_obj=transfer_obj,
        )

        chunk_size = settings.SEND_CHUNK_SIZE
        for offset in range(0, len(data), chunk_size):
            progress_callback(min(chunk_size, len(data) - offset))

        audits = generate_audits(shard_path)
        token = self._token_repo.load() or ""
        self._api.shard_done_uploading(token, shard_name, audits)
        logger.debug("[DEV] shard sent locally: %s", shard_name)

    def _zmq_send(self, shard_path: str, shard_info: dict, token: str, progress_callback) -> None:
        context = zmq.Context()
        socket = context.socket(zmq.PAIR)
        socket.connect(f"tcp://{shard_info['ip_address']}:{shard_info['port']}")

        socket.recv()  # start frame

        with open(shard_path, "rb") as f:
            socket.RCVTIMEO = settings.RECEIVE_TIMEOUT_MS
            chunk = f.read(settings.SEND_CHUNK_SIZE)
            while chunk:
                socket.send(pickle.dumps({"type": "data", "data": chunk}))
                socket.recv()
                progress_callback(len(chunk))
                chunk = f.read(settings.SEND_CHUNK_SIZE)

        socket.send(pickle.dumps({"type": "done"}))
        socket.RCVTIMEO = settings.DISCONNECT_TIMEOUT_MS
        socket.recv()
        socket.close()
        context.term()

        audits = generate_audits(shard_path)
        self._api.shard_done_uploading(token, shard_info["shard_id"], audits)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def receive(self, shard_info: dict, progress_callback) -> None:
        if settings.BYPASS_DOWNLOAD:
            self._dev_receive(shard_info, progress_callback)
            return
        self._zmq_receive(shard_info, progress_callback)

    def _dev_receive(self, shard_info: dict, progress_callback) -> None:
        shard_id = shard_info["shard_id"]
        src = os.path.join(self._paths.dev_host_dir, shard_id)
        dst = os.path.join(self._paths.shards_dir, shard_id)

        if not os.path.exists(src):
            raise FileNotFoundError(f"Dev shard not found: {src}")

        with open(src, "rb") as sf:
            data = sf.read()
        with open(dst, "wb") as df:
            df.write(data)

        chunk_size = settings.SEND_CHUNK_SIZE
        for offset in range(0, len(data), chunk_size):
            progress_callback(min(chunk_size, len(data) - offset))
        logger.debug("[DEV] shard received locally: %s", shard_id)

    def _zmq_receive(self, shard_info: dict, progress_callback) -> None:
        context = zmq.Context()
        socket = context.socket(zmq.PAIR)
        socket.connect(f"tcp://{shard_info['ip_address']}:{shard_info['port']}")

        dst = os.path.join(self._paths.shards_dir, shard_info["shard_id"])
        with open(dst, "wb") as f:
            socket.RCVTIMEO = settings.RECEIVE_TIMEOUT_MS
            while True:
                frame = pickle.loads(socket.recv())
                if frame.get("type") == "done":
                    break
                chunk = frame["data"]
                f.write(chunk)
                progress_callback(len(chunk))

        socket.close()
        context.term()

    # ------------------------------------------------------------------
    # Resume
    # ------------------------------------------------------------------

    def resume_pending_connections(self, progress_callback) -> None:
        """Re-send any shards that were interrupted in a previous run."""
        logger.info("Checking for pending connections to resume…")
        # In the original code this read connections.txt and re-sent.
        # Preserved as a hook; full implementation depends on ZMQ session protocol.
