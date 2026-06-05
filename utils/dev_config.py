"""
Development / offline flags — driven by LOCAL_MODE (see app_config.py).

When LOCAL_MODE is True (default), the app runs without coordinator login,
contract payment, or storage-node hosts. Encryption, erasure coding, and
file assembly still run as in production.

Set CERA_LOCAL_MODE=0 to use the real backend and ZMQ storage nodes.
Individual BYPASS_* env vars can override the master switch per concern.
"""

from .app_config import LOCAL_MODE, env_bool

# Master switch applies to all bypasses unless overridden
BYPASS_LOGIN: bool = env_bool("CERA_BYPASS_LOGIN", LOCAL_MODE)
BYPASS_CONTRACT: bool = env_bool("CERA_BYPASS_CONTRACT", LOCAL_MODE)
BYPASS_PRICE: bool = env_bool("CERA_BYPASS_PRICE", LOCAL_MODE)
BYPASS_CREATE_FILE: bool = env_bool("CERA_BYPASS_CREATE_FILE", LOCAL_MODE)
BYPASS_GET_FILES: bool = env_bool("CERA_BYPASS_GET_FILES", LOCAL_MODE)
BYPASS_UPLOAD_TRANSFER: bool = env_bool("CERA_BYPASS_UPLOAD", LOCAL_MODE)
BYPASS_DOWNLOAD_TRANSFER: bool = env_bool("CERA_BYPASS_DOWNLOAD", LOCAL_MODE)

DEV_PRICE_WEI: int = 10_000_000_000_000_000  # 0.01 ETH (local pricing display only)

# Sample entries only used when no local uploads exist yet
DEV_FAKE_FILES: list = [
    {"filename": "sample_photo.jpg", "size": 2_048_000, "download_count": 3},
    {"filename": "project_report.pdf", "size": 512_000, "download_count": 1},
]
