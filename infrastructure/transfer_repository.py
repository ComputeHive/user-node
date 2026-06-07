"""
infrastructure/transfer_repository.py – Persist upload/download transfer state.

Keeps all JSON I/O for the transfer cache files in one place.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


class TransferRepository:
    def __init__(self, transfer_file: str) -> None:
        self._file = transfer_file

    def load(self) -> dict | None:
        if not os.path.exists(self._file):
            return None
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def save(self, state: dict) -> None:
        if not os.path.exists(self._file):
            raise FileNotFoundError(f"Transfer file missing: {self._file}")
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(state, f)

    def delete(self) -> None:
        try:
            os.remove(self._file)
        except OSError as exc:
            raise OSError(f"Could not delete transfer file: {self._file}") from exc
