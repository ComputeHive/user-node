"""
application/container.py – Dependency injection container.

Creates and wires every service exactly once.  The rest of the app
imports from here rather than constructing its own dependencies.
"""

from __future__ import annotations

import threading

from config import settings
from core.paths import AppPaths
from infrastructure.filesystem import ensure_filesystem
from infrastructure.token_repository import TokenRepository
from infrastructure.transfer_repository import TransferRepository


class AppContainer:
    """Holds the single shared instance of every service."""

    def __init__(self, base_data_dir: str | None = None) -> None:
        self.paths = AppPaths.from_base(base_data_dir)
        ensure_filesystem(self.paths)

        self.token_repo = TokenRepository(self.paths.cache_file)
        self.upload_transfer_repo = TransferRepository(self.paths.upload_transfer_file)
        self.download_transfer_repo = TransferRepository(self.paths.download_transfer_file)

        self._semaphore = threading.Semaphore()
        self._api_client = self._build_api_client()
        self._shard_transfer = self._build_shard_transfer()

        from application.upload_service import UploadService
        from application.download_service import DownloadService

        self.upload_service = UploadService(
            paths=self.paths,
            api_client=self._api_client,
            token_repo=self.token_repo,
            upload_transfer_repo=self.upload_transfer_repo,
            shard_transfer=self._shard_transfer,
        )
        self.download_service = DownloadService(
            paths=self.paths,
            api_client=self._api_client,
            token_repo=self.token_repo,
            download_transfer_repo=self.download_transfer_repo,
            shard_transfer=self._shard_transfer,
        )

    # ------------------------------------------------------------------
    # Convenience: authenticate
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> None:
        token = self._api_client.login(username, password)
        self.token_repo.save(token)

    def logout(self) -> None:
        self.token_repo.delete()

    # ------------------------------------------------------------------
    # Private factory methods
    # ------------------------------------------------------------------

    def _build_api_client(self):
        if settings.LOCAL_MODE:
            from infrastructure.api.cera_client_dev import CeraClientDev
            return CeraClientDev(
                paths=self.paths,
                token_repo=self.token_repo,
                upload_transfer_repo=self.upload_transfer_repo,
            )
        from infrastructure.api.cera_client import CeraClient
        return CeraClient(host_url=settings.HOST_URL)

    def _build_shard_transfer(self):
        from infrastructure.transfer.shard_transfer import ShardTransfer
        return ShardTransfer(
            paths=self.paths,
            semaphore=self._semaphore,
            api_client=self._api_client,
            token_repo=self.token_repo,
        )

    # ------------------------------------------------------------------
    # Shortcut accessors used by pages
    # ------------------------------------------------------------------

    @property
    def api(self):
        return self._api_client
