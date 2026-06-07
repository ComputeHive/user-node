"""
core/user_state.py – Upload-state constants and their display text.

Keeps the magic strings in one place and makes state comparisons
readable throughout the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserState:
    code: str
    message: str


UPLOAD_READY = UserState("1", "Please enter your encryption key and start your upload")
UNPAID_CONTRACT = UserState("2", "Please add balance to the contract to start uploading")
CREATE_CONTRACT = UserState("3", "You have seeds, please select a file to upload")
NO_SEEDS = UserState("4", "You have to request a seed before you can select a file to upload")

ALL_STATES: dict[str, UserState] = {
    s.code: s for s in (UPLOAD_READY, UNPAID_CONTRACT, CREATE_CONTRACT, NO_SEEDS)
}


def from_code(code: str) -> UserState:
    """Return the matching UserState, falling back to UNPAID_CONTRACT."""
    return ALL_STATES.get(code, UNPAID_CONTRACT)
