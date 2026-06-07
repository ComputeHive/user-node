"""
settings.py – All runtime configuration in one place.

Environment variables drive every flag. Sane defaults keep the app
usable in local/dev mode with no .env file at all.
"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Master offline switch
# ---------------------------------------------------------------------------
LOCAL_MODE: bool = _env_bool("CERA_LOCAL_MODE", True)

# ---------------------------------------------------------------------------
# Per-concern bypass flags (default to LOCAL_MODE unless overridden)
# ---------------------------------------------------------------------------
BYPASS_LOGIN: bool = _env_bool("CERA_BYPASS_LOGIN", LOCAL_MODE)
BYPASS_CONTRACT: bool = _env_bool("CERA_BYPASS_CONTRACT", LOCAL_MODE)
BYPASS_PRICE: bool = _env_bool("CERA_BYPASS_PRICE", LOCAL_MODE)
BYPASS_CREATE_FILE: bool = _env_bool("CERA_BYPASS_CREATE_FILE", LOCAL_MODE)
BYPASS_GET_FILES: bool = _env_bool("CERA_BYPASS_GET_FILES", LOCAL_MODE)
BYPASS_UPLOAD: bool = _env_bool("CERA_BYPASS_UPLOAD", LOCAL_MODE)
BYPASS_DOWNLOAD: bool = _env_bool("CERA_BYPASS_DOWNLOAD", LOCAL_MODE)

# ---------------------------------------------------------------------------
# Backend URLs
# ---------------------------------------------------------------------------
_raw_host = os.environ.get("CERA_HOST_URL", "http://localhost:5000/")
HOST_URL: str = _raw_host if _raw_host.endswith("/") else _raw_host + "/"
FRONTEND_URL: str = "http://localhost:3000/users"

# ---------------------------------------------------------------------------
# Dev-mode defaults
# ---------------------------------------------------------------------------
DEV_TOKEN: str = os.environ.get("CERA_DEV_TOKEN", "dev_token")
DEV_PRICE_WEI: int = 10_000_000_000_000_000  # 0.01 ETH

DEV_FAKE_FILES: list[dict] = [
    {"filename": "sample_photo.jpg", "size": 2_048_000, "download_count": 3},
    {"filename": "project_report.pdf", "size": 512_000, "download_count": 1},
]

# ---------------------------------------------------------------------------
# Transfer settings
# ---------------------------------------------------------------------------
SEND_CHUNK_SIZE: int = int(0.5 * 1024 * 1024)  # 500 KB
RECEIVE_TIMEOUT_MS: int = 8_000
DISCONNECT_TIMEOUT_MS: int = 1_000 * 60 * 60
UPLOAD_POLL_INTERVAL_S: float = 2.0
SEGMENT_SIZE: int = int(500 * 1024 * 1024)  # 500 MB

# ---------------------------------------------------------------------------
# Erasure coding
# ---------------------------------------------------------------------------
ERASURE_FACTOR: int = 1
MIN_DATA_SHARDS: int = 2

# ---------------------------------------------------------------------------
# Audit settings
# ---------------------------------------------------------------------------
AUDITS_DEFAULT_COUNT: int = 100

# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------
MIN_PRICE: float = 0.25
MAX_KEY_LENGTH: int = 32

# ---------------------------------------------------------------------------
# Error messages
# ---------------------------------------------------------------------------
SERVER_NOT_RESPONDING: str = "Check your internet connection"
