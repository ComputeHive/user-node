"""
application/download_service.py – Download pipeline use-case.

Mirror of UploadService: pure business logic, no Qt, no globals.
"""

from __future__ import annotations

import logging
import os

from infrastructure.transfer_repository import TransferRepository

logger = logging.getLogger(__name__)


class DownloadService:

    def __init__(
        self,
        paths,              # core.paths.AppPaths
        api_client,         # CeraClient | CeraClientDev
        token_repo,         # TokenRepository
        download_transfer_repo: TransferRepository,
        shard_transfer,     # ShardTransfer
    ) -> None:
        self._paths = paths
        self._api = api_client
        self._token_repo = token_repo
        self._download_repo = download_transfer_repo
        self._shard_transfer = shard_transfer

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def download_file(self, filename: str, key: str, progress_callback) -> None:
        """
        Download *filename* and decrypt with *key*.

        *progress_callback(bytes_done)* is called after each shard.
        """
        from infrastructure.filesystem import clear_segments_and_encrypted, clear_shards

        token = self._token_repo.load()
        if not token:
            raise PermissionError("Not authenticated. Please log in.")

        transfer_obj = self._download_repo.load()

        if not transfer_obj or transfer_obj.get("start_flag", True):
            transfer_obj = self._start_new_download(filename, key, token, transfer_obj, progress_callback)
        else:
            logger.info("Resuming download for '%s'", filename)
            progress_callback(transfer_obj["progress"])
            self._shard_transfer.resume_pending_connections(progress_callback)
            file_metadata = transfer_obj["file_metadata"]

        file_metadata = transfer_obj["file_metadata"]
        segments = file_metadata["segments"]

        self._rename_shards_for_decode(segments, transfer_obj)
        self._retrieve_file(key, file_metadata)

        clear_segments_and_encrypted(self._paths)
        clear_shards(self._paths)
        self._download_repo.delete()
        logger.info("Download of '%s' complete.", filename)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _start_new_download(
        self, filename: str, key: str, token: str, transfer_obj: dict | None, progress_callback
    ) -> dict:
        segments = self._api.start_download(token, filename)

        for segment in segments:
            for shard in segment["shards"]:
                self._shard_transfer.receive(
                    shard_info=shard,
                    progress_callback=progress_callback,
                )

        file_metadata = {"filename": filename, "segments": segments}
        new_transfer = {
            **(transfer_obj or {}),
            "start_flag": False,
            "file_metadata": file_metadata,
            "shards_renamed": False,
        }
        self._download_repo.save(new_transfer)
        return new_transfer

    def _rename_shards_for_decode(self, segments: list, transfer_obj: dict) -> None:
        # from config.settings import SEGMENT_SIZE

        if transfer_obj.get("shards_renamed"):
            return

        # from utils.helper import SHARD_FILENAME
        shard_filename = getattr(self._paths, "_shard_filename", "shard")

        for segment in segments:
            m = segment.get("m", len(segment["shards"]))
            for shard in segment["shards"]:
                src = os.path.join(self._paths.shards_dir, shard["shard_id"])
                dst = os.path.join(
                    self._paths.shards_dir,
                    f"shard_{shard['segment_no']}.{shard['shard_no']}_{m}.fec",
                )
                os.rename(src, dst)

        transfer_obj["shards_renamed"] = True
        self._download_repo.save(transfer_obj)

    def _retrieve_file(self, key: str, file_metadata: dict) -> None:
        from utils.erasure_coding import decode
        from utils.encryption import decrypt

        segments = file_metadata["segments"]

        for segment_num, segment in enumerate(segments):
            segment_name = f"segment_{segment_num}"
            logger.info("Decoding segment %d", segment_num)
            decode(self._paths.shards_dir, self._paths.encryption_dir, segment_num, segment["k"])
            logger.info("Decrypting segment %d", segment_num)
            decrypt(
                os.path.join(self._paths.encryption_dir, segment_name),
                os.path.join(self._paths.segments_dir, segment_name),
                key,
            )

        output_path = os.path.join(self._paths.download_output_dir, file_metadata["filename"])
        with open(output_path, "wb") as out:
            for part in sorted(os.listdir(self._paths.segments_dir)):
                part_path = os.path.join(self._paths.segments_dir, part)
                with open(part_path, "rb") as part_file:
                    while True:
                        block = part_file.read(1024 * 1024)
                        if not block:
                            break
                        out.write(block)

        logger.info("File written to '%s'", output_path)
