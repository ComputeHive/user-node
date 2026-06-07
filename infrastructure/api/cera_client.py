"""
infrastructure/api/cera_client.py – HTTP client for the CERA backend.

This class only talks to the network. It raises exceptions on failure;
callers decide how to present errors to the user.

All dev-mode bypasses live in CeraClientDev (same interface).
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_TIMEOUT_S = 10


class AuthenticationError(Exception):
    """Raised when the server returns an auth-related error."""


class ApiError(Exception):
    """Raised for any non-auth server error."""


class CeraClient:
    """Production HTTP client. No UI, no global state."""

    def __init__(self, host_url: str) -> None:
        self._base = host_url.rstrip("/")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> str:
        """Return auth token on success; raise on failure."""
        try:
            resp = requests.post(
                f"{self._base}/users/signin",
                json={"username": username, "password": password},
                timeout=_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise ConnectionError("Check your internet connection") from exc

        if resp.status_code == 200:
            return resp.json()["token"]
        raise AuthenticationError(resp.text)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_user_state(self, token: str) -> str:
        return self._get(f"{self._base}/users/me/state", token, lambda r: r.json()["state"])

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def get_price(self, token: str, download_count: int, duration_months: int, file_size: int) -> int:
        return self._get(
            f"{self._base}/users/me/files/pending/price",
            token,
            lambda r: r.json()["price"],
            params={
                "download_count": download_count,
                "duration_in_months": duration_months,
                "file_size": file_size,
            },
        )

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def get_user_files(self, token: str) -> list[dict]:
        return self._get(f"{self._base}/users/me/files", token, lambda r: r.json())

    def create_file(self, token: str, contract_details: dict) -> None:
        """Register a new file contract. Raises ApiError on failure."""
        import json as _json

        try:
            resp = requests.post(
                f"{self._base}/users/me/files",
                headers={"TOKEN": token},
                json=_json.dumps(contract_details),
                timeout=_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise ConnectionError("Check your internet connection") from exc

        if resp.status_code == 201:
            return
        if resp.status_code == 409:
            raise ApiError("This file is already stored.")
        raise ApiError(resp.text)

    # ------------------------------------------------------------------
    # Upload pipeline
    # ------------------------------------------------------------------

    def get_pending_file_info(self, token: str) -> dict:
        return self._get(f"{self._base}/users/me/files/pending", token, lambda r: r.json())

    def shard_done_uploading(self, token: str, shard_id: str, audits: list) -> None:
        import os
        try:
            resp = requests.patch(
                f"{self._base}/users/me/files/pending/shards/done",
                json={"shard_id": os.path.basename(shard_id), "audits": audits},
                headers={"TOKEN": token},
                timeout=_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise ConnectionError("Check your internet connection") from exc

        if resp.status_code != 204:
            raise AuthenticationError("Session expired. Please log in again.")

    def file_done_uploading(self, token: str) -> None:
        self._patch(f"{self._base}/users/me/files/pending/done", token)

    # ------------------------------------------------------------------
    # Download pipeline
    # ------------------------------------------------------------------

    def start_download(self, token: str, filename: str) -> list[dict]:
        try:
            resp = requests.post(
                f"{self._base}/users/me/files/{filename}/downloads",
                headers={"TOKEN": token},
                timeout=_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise ConnectionError("Check your internet connection") from exc

        if resp.status_code == 200:
            return resp.json()["segments"]
        if resp.status_code in (404, 405):
            raise ApiError(resp.text)
        raise AuthenticationError("Session expired. Please log in again.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, token: str, extract, params: dict | None = None):
        try:
            resp = requests.get(url, params=params, headers={"TOKEN": token}, timeout=_TIMEOUT_S)
        except requests.RequestException as exc:
            raise ConnectionError("Check your internet connection") from exc

        if resp.status_code in (200, 204):
            return extract(resp)
        raise AuthenticationError("Session expired. Please log in again.")

    def _patch(self, url: str, token: str):
        try:
            resp = requests.patch(url, headers={"TOKEN": token}, timeout=_TIMEOUT_S)
        except requests.RequestException as exc:
            raise ConnectionError("Check your internet connection") from exc

        if resp.status_code not in (200, 204):
            raise AuthenticationError("Session expired. Please log in again.")
