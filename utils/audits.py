"""
utils/audits.py – File integrity audit generation.

No global state: the default audit count is imported from settings.
"""

from __future__ import annotations

import hashlib
import os

from config.settings import AUDITS_DEFAULT_COUNT


def generate_audits(file_path: str, count: int = AUDITS_DEFAULT_COUNT) -> list[dict[str, str]]:
    """
    Generate *count* audit records for *file_path*.

    Each record contains:
    - ``salt``: 16 random bytes as a hex string.
    - ``hash``: MD5 of the file's MD5 combined with the salt.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(file_path, "rb") as f:
        base_hash = hashlib.md5(f.read())

    audits = []
    for _ in range(count):
        salt = os.urandom(16)
        audit_hash = base_hash.copy()
        audit_hash.update(salt)
        audits.append({"salt": salt.hex(), "hash": audit_hash.hexdigest()})

    return audits
