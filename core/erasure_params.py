"""
core/erasure_params.py – Pure erasure-coding arithmetic.

No I/O, no imports from other app modules.  Easy to unit-test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from config.settings import ERASURE_FACTOR, MIN_DATA_SHARDS, SEGMENT_SIZE


@dataclass(frozen=True)
class SegmentParams:
    k: int          # minimum shards needed to reconstruct
    m: int          # total shards produced
    shard_size: int  # bytes per shard (ceiling)


def compute_erasure_params(segment_size_bytes: int) -> SegmentParams:
    """Return k/m/shard_size for a segment of *segment_size_bytes*."""
    k = MIN_DATA_SHARDS
    m = ERASURE_FACTOR + k
    shard_size = math.ceil(segment_size_bytes / k)
    return SegmentParams(k=k, m=m, shard_size=shard_size)


def compute_file_segments(file_size: int, segment_size: int = SEGMENT_SIZE) -> list[SegmentParams]:
    """
    Split *file_size* into segments and return erasure params for each.

    The last segment is sized to the remainder so the sum equals file_size.
    """
    segment_count = max(1, math.ceil(file_size / segment_size))
    result: list[SegmentParams] = []

    for i in range(segment_count):
        if i < segment_count - 1:
            this_segment_size = segment_size
        else:
            this_segment_size = file_size - segment_size * (segment_count - 1)
        result.append(compute_erasure_params(this_segment_size))

    return result
