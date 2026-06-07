"""
application/upload_service.py – Upload pipeline use-case.

Coordinates encryption, erasure coding, and shard transfer.
Has no knowledge of Qt, no global state, and raises plain exceptions
on failure so callers can handle them appropriately.
"""

from __future__ import annotations

import logging
import os
import time

from infrastructure.transfer_repository import TransferRepository

logger = logging.getLogger(__name__)


class UploadService:
    """
    Orchestrates the full upload pipeline for a single file.

    Dependencies are injected so the class is easy to test and swap.
    """

    def __init__(
        self,
        paths,                  # core.paths.AppPaths
        api_client,             # infrastructure.api.CeraClient | CeraClientDev
        token_repo,             # infrastructure.token_repository.TokenRepository
        upload_transfer_repo: TransferRepository,
        shard_transfer,         # infrastructure.transfer.ShardTransfer
    ) -> None:
        self._paths = paths
        self._api = api_client
        self._token_repo = token_repo
        self._upload_repo = upload_transfer_repo
        self._shard_transfer = shard_transfer

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def upload_file(self, file_path: str, key: str, progress_callback) -> None:
        """
        Upload *file_path* encrypted with *key*.

        *progress_callback(bytes_done)* is called after each shard.
        Raises on unrecoverable error.
        """
        from infrastructure.filesystem import clear_segments_and_encrypted, clear_shards
        from utils.encryption import encrypt
        from utils.erasure_coding import encode

        start = time.time()
        token = self._token_repo.load()
        if not token:
            raise PermissionError("Not authenticated. Please log in.")

        server_info = self._api.get_pending_file_info(token)
        file_size = os.stat(file_path).st_size

        if file_size != server_info["file_size"]:
            raise ValueError("File has changed since the contract was created.")

        transfer_obj = self._upload_repo.load()

        if transfer_obj["start_flag"]:
            transfer_obj = self._initialise_transfer(transfer_obj, server_info, key)
        else:
            key = transfer_obj.get("key") or key
            self._shard_transfer.resume_pending_connections(progress_callback)

        progress_callback(transfer_obj["progress"])

        from config.settings import SEGMENT_SIZE
        self._upload_segments(file_path, key, transfer_obj, SEGMENT_SIZE, progress_callback)

        self._api.file_done_uploading(token)
        self._upload_repo.delete()
        clear_segments_and_encrypted(self._paths)
        clear_shards(self._paths)

        logger.info("Upload complete in %.1f s", time.time() - start)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _initialise_transfer(self, transfer_obj: dict, server_info: dict, key: str) -> dict:
        from infrastructure.filesystem import clear_segments_and_encrypted, clear_shards
        clear_shards(self._paths)
        clear_segments_and_encrypted(self._paths)

        transfer_obj["segments"] = [
            {**seg, "done_uploading": False, "processed": False}
            for seg in server_info["segments"]
        ]
        transfer_obj["key"] = key
        transfer_obj["start_flag"] = False
        self._upload_repo.save(transfer_obj)
        return transfer_obj

    def _upload_segments(
        self, file_path: str, key: str, transfer_obj: dict, chunk_size: int, progress_callback
    ) -> None:
        file_size = os.stat(file_path).st_size

        if file_size < chunk_size:
            # Single-segment file
            self._process_and_upload_segment(file_path, key, 0, transfer_obj, progress_callback)
            transfer_obj["segments"][0]["done_uploading"] = True
            self._upload_repo.save(transfer_obj)
            return

        # Multi-segment file
        with open(file_path, "rb") as fh:
            segment_num = 0
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                if not transfer_obj["segments"][segment_num]["done_uploading"]:
                    segment_path = os.path.join(
                        self._paths.segments_dir,
                        f"{segment_num}_{os.path.basename(file_path)}",
                    )
                    with open(segment_path, "wb") as sf:
                        sf.write(chunk)
                    self._process_and_upload_segment(
                        segment_path, key, segment_num, transfer_obj, progress_callback
                    )
                    transfer_obj["segments"][segment_num]["done_uploading"] = True
                    self._upload_repo.save(transfer_obj)
                else:
                    logger.debug("Segment %d already uploaded, skipping.", segment_num)
                segment_num += 1

    def _process_and_upload_segment(
        self, segment_path: str, key: str, segment_num: int, transfer_obj: dict, progress_callback
    ) -> None:
        from infrastructure.filesystem import clear_segments_and_encrypted, clear_shards
        from utils.encryption import encrypt
        from utils.erasure_coding import encode

        seg = transfer_obj["segments"][segment_num]

        if not seg["processed"]:
            logger.info("Segment %d: encrypting", segment_num)
            filename = os.path.basename(segment_path)
            enc_path = os.path.join(self._paths.encryption_dir, f"{filename}.enc")
            encrypt(segment_path, enc_path, key)

            logger.info("Segment %d: erasure coding", segment_num)
            encode(enc_path, self._paths.shards_dir, segment_num, seg["k"], seg["m"])

            logger.info("Segment %d: renaming shards", segment_num)
            self._rename_shards_to_server_ids(segment_num, seg)

            seg["processed"] = True
            self._upload_repo.save(transfer_obj)
        else:
            logger.debug("Segment %d already processed, resuming upload.", segment_num)

        token = self._token_repo.load()
        for shard_index, shard in enumerate(seg["shards"]):
            if shard["done_uploading"]:
                logger.debug("Shard %d.%d already uploaded, skipping.", segment_num, shard_index)
                continue
            self._shard_transfer.send(
                shard_path=os.path.join(self._paths.shards_dir, shard["shard_id"]),
                shard_info=shard,
                segment_num=segment_num,
                shard_index=shard_index,
                shard_size=seg["shard_size"],
                token=token,
                progress_callback=progress_callback,
                transfer_obj=transfer_obj,
            )

        clear_shards(self._paths)

    def _rename_shards_to_server_ids(self, segment_num: int, seg: dict) -> None:
        existing = sorted(os.listdir(self._paths.shards_dir))
        target_ids = [s["shard_id"] for s in seg["shards"]]
        if len(existing) != len(target_ids):
            raise ValueError(
                f"Shard count mismatch for segment {segment_num}: "
                f"expected {len(target_ids)}, found {len(existing)}"
            )
        for old_name, new_id in zip(existing, target_ids):
            os.rename(
                os.path.join(self._paths.shards_dir, old_name),
                os.path.join(self._paths.shards_dir, new_id),
            )
