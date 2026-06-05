"""
Application runtime configuration.

Set CERAMODE=1 (default) to run upload/download end-to-end without
a coordinator, payment flow, login API, or storage-node hosts. Set to 0 for
production behaviour against a real backend.
"""

from __future__ import annotations

import os


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Single master switch for offline / no-host operation
LOCAL_MODE: bool = env_bool("CERA_LOCAL_MODE", True)

LOCAL_DEV_TOKEN: str = os.environ.get("CERA_DEV_TOKEN", "dev_token")


def bootstrap_local_session(helper) -> None:
    """Ensure a cached token exists so production code paths that read helper.token work."""
    if helper.is_user_logged_in():
        return
    with open(helper.cache_file, "w", encoding="utf-8") as f:
        f.write(LOCAL_DEV_TOKEN)
    helper.token = LOCAL_DEV_TOKEN
