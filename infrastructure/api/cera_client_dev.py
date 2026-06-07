"""
infrastructure/api/cera_client_dev.py – Offline stand-in for CeraClient.

Implements the same public interface but fulfils every contract from
the local filesystem.  Swap this for CeraClient in the factory
(infrastructure/api/__init__.py) to go fully offline.
"""

from __future__ import annotations

import logging
import os

from config.settings import DEV_PRICE_WEI, DEV_FAKE_FILES, DEV_TOKEN
from core.erasure_params import compute_file_segments
from core.paths import AppPaths
from infrastructure.storage.local_index import LocalIndex
from infrastructure.token_repository import TokenRepository
from infrastructure.transfer_repository import TransferRepository

logger = logging.getLogger(__name__)


class CeraClientDev:

    def __init__(
        self,
        paths: AppPaths,
        token_repo: TokenRepository,
        upload_transfer_repo: TransferRepository,
        shard_filename: str = "shard",
    ) -> None:
        self._paths = paths
        self._token_repo = token_repo
        self._upload_transfer_repo = upload_transfer_repo
        self._shard_filename = shard_filename

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> str:
        logger.debug("[DEV] login bypassed for '%s'", username)
        return DEV_TOKEN

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_user_state(self, token: str) -> str:
        from core.user_state import UPLOAD_READY
        logger.debug("[DEV] get_user_state → %s", UPLOAD_READY.code)
        return UPLOAD_READY.code

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def get_price(self, token: str, download_count: int, duration_months: int, file_size: int) -> int:
        logger.debug("[DEV] get_price → %d wei", DEV_PRICE_WEI)
        return DEV_PRICE_WEI

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def get_user_files(self, token: str) -> list[dict]:
        index = LocalIndex(self._paths.dev_host_dir)
        stored = index.list_files()
        if stored:
            logger.debug("[DEV] get_user_files → %d local file(s)", len(stored))
            return stored
        logger.debug("[DEV] get_user_files → %d sample file(s)", len(DEV_FAKE_FILES))
        return DEV_FAKE_FILES

    def create_file(self, token: str, contract_details: dict) -> None:
        logger.debug("[DEV] create_file bypassed")

    # ------------------------------------------------------------------
    # Upload pipeline
    # ------------------------------------------------------------------

    def get_pending_file_info(self, token: str) -> dict:
        transfer_obj = self._upload_transfer_repo.load()
        if not transfer_obj:
            raise FileNotFoundError("No pending transfer file found.")

        file_path = transfer_obj.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError("Pending file not found on disk.")

        file_size = os.stat(file_path).st_size
        segment_params_list = compute_file_segments(file_size)

        dev_segments = []
        for seg_idx, sp in enumerate(segment_params_list):
            shards = [
                {
                    "shard_id": f"{self._shard_filename}_{seg_idx}.{shard_no}_{sp.m}.fec",
                    "shard_no": shard_no,
                    "segment_no": seg_idx,
                    "ip_address": "127.0.0.1",
                    "port": 5555 + shard_no,
                    "shared_authentication_key": "dev_auth_key",
                    "done_uploading": False,
                }
                for shard_no in range(sp.m)
            ]
            dev_segments.append({
                "k": sp.k,
                "m": sp.m,
                "shard_size": sp.shard_size,
                "shards": shards,
                "done_uploading": False,
                "processed": False,
            })

        logger.debug("[DEV] get_pending_file_info → %d segment(s), file_size=%d", len(dev_segments), file_size)
        return {"file_size": file_size, "segments": dev_segments}

    def shard_done_uploading(self, token: str, shard_id: str, audits: list) -> None:
        logger.debug("[DEV] shard_done_uploading → %s (skipped)", os.path.basename(shard_id))

    def file_done_uploading(self, token: str) -> None:
        transfer_obj = self._upload_transfer_repo.load()
        fname = None
        if transfer_obj and transfer_obj.get("file_path"):
            fname = os.path.basename(transfer_obj["file_path"])
        if fname:
            index = LocalIndex(self._paths.dev_host_dir)
            index.register_completed_upload(fname, transfer_obj)
            logger.debug("[DEV] file_done_uploading → index finalized for '%s'", fname)
        else:
            logger.debug("[DEV] file_done_uploading → skipped (no filename)")

    # ------------------------------------------------------------------
    # Download pipeline
    # ------------------------------------------------------------------

    def start_download(self, token: str, filename: str) -> list[dict]:
        index = LocalIndex(self._paths.dev_host_dir)
        _, segments = index.load(filename)
        if not segments:
            raise FileNotFoundError(
                f"No local shards found for '{filename}'.\n"
                "Upload the file first (LOCAL_MODE), then download it here."
            )
        logger.debug("[DEV] start_download → loaded index for '%s'", filename)
        return segments
