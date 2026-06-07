import os
import re
import logging
from contextlib import ExitStack

from zfec import filefec


logger = logging.getLogger(__name__)


def _get_file_size(file_path: str) -> int:
    return os.path.getsize(file_path)


def _build_shard_name(prefix: str, segment_number: int) -> str:
    return f"{prefix}_{segment_number}"


def _extract_shard_index(path: str) -> int:
    filename = os.path.basename(path)
    try:
        return int(filename.split(".")[1].split("_")[0])
    except (IndexError, ValueError):
        raise ValueError(f"Invalid shard filename format: {filename}")


def _is_valid_shard(filename: str, shard_name: str) -> bool:
    pattern = rf"^{re.escape(shard_name)}\.[0-9]+_[0-9]+\.fec$"
    return re.match(pattern, filename) is not None



def encode(
    file_path: str,
    directory_to_write_shards: str,
    segment_number: int,
    k_param: int,
    m_param: int,
    shard_prefix: str = "shard",
) -> None:

    if not 1 <= k_param <= m_param:
        raise ValueError("Invalid k/m parameters")

    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)

    os.makedirs(directory_to_write_shards, exist_ok=True)

    for f in os.listdir(directory_to_write_shards):
        os.remove(os.path.join(directory_to_write_shards, f))

    shard_name = _build_shard_name(shard_prefix, segment_number)

    file_size = _get_file_size(file_path)

    logger.info("Encoding %s (%d bytes)", file_path, file_size)

    with open(file_path, "rb") as f:
        data = f.read()

    filefec.encode_to_files(
        data,
        file_size,
        directory_to_write_shards,
        shard_name,
        k_param,
        m_param,
        suffix=".fec",
        overwrite=True,
        verbose=False,
    )


def decode(
    shards_directory: str,
    retrieved_segments_directory: str,
    segment_number: int,
    k: int,
    shard_prefix: str = "shard",
):

    if not os.path.isdir(shards_directory):
        raise FileNotFoundError(shards_directory)

    shard_name = _build_shard_name(shard_prefix, segment_number)

    shard_paths = [
        os.path.join(shards_directory, f)
        for f in os.listdir(shards_directory)
        if _is_valid_shard(f, shard_name)
    ]

    if len(shard_paths) < k:
        raise FileNotFoundError(
            f"Need {k}, found {len(shard_paths)} shards"
        )

    shard_paths = sorted(shard_paths, key=_extract_shard_index)[:k]

    os.makedirs(retrieved_segments_directory, exist_ok=True)

    segment_name = f"segment_{segment_number}"
    segment_path = os.path.join(retrieved_segments_directory, segment_name)

    logger.info("Decoding → %s", segment_path)

    with ExitStack() as stack:
        shard_handles = [stack.enter_context(open(p, "rb")) for p in shard_paths]
        output_handle = stack.enter_context(open(segment_path, "wb"))

        filefec.decode_from_files(output_handle, shard_handles, verbose=False)



