"""
infrastructure/token_repository.py – Read/write the authentication token.

Abstracts the cache-file I/O so callers never open files themselves.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class TokenRepository:
    def __init__(self, cache_file: str) -> None:
        self._cache_file = cache_file

    def load(self) -> str | None:
        """Return the stored token, or None if absent/empty."""
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
            return token or None
        except OSError:
            return None

    def save(self, token: str) -> None:
        with open(self._cache_file, "w", encoding="utf-8") as f:
            f.write(token)

    def delete(self) -> None:
        try:
            os.remove(self._cache_file)
        except OSError:
            pass

    def exists(self) -> bool:
        return bool(self.load())
