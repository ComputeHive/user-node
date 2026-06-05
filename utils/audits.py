import hashlib
import os

from .helper import Helper

helper = Helper()


def generate_audits(file_path, audits_count=helper.audits_default_count):
    """
    Generate audit records for a file.

    Each audit consists of a randomly generated salt and the MD5 hash
    of the file's MD5 digest combined with that salt. The resulting
    audits can later be used to verify file integrity.

    Args:
        file_path (str): Path to the file for which audits will be generated.
        audits_count (int, optional): Number of audit records to generate.
            Defaults to ``helper.audits_default_count``.

    Returns:
        list[dict[str, str]]: A list of audit records. Each record contains:
            - ``salt``: Random 16-byte salt encoded as a hexadecimal string.
            - ``hash``: Hexadecimal MD5 digest associated with the salt.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        OSError: If the file cannot be opened or read.
    """
    with open(file_path, "rb") as f:
        base_hash = hashlib.md5(f.read())

    audits = []

    for _ in range(audits_count):
        salt = os.urandom(16)

        audit_hash = base_hash.copy()
        audit_hash.update(salt)

        audits.append({
            "salt": salt.hex(),
            "hash": audit_hash.hexdigest(),
        })

    return audits