"""
streaming file encryption using AES-256-GCM.

Security properties
───────────────────
  • AES-256-GCM          — authenticated encryption (IND-CCA2)
  • Argon2id KDF         — memory-hard, GPU/ASIC resistant
  • Chunked streaming    — constant memory regardless of file size
  • Full header AAD      — every header field authenticated by GCM tag
  • Per-chunk nonces     — nonce_i = base_nonce XOR little-endian(i); no reuse
  • Atomic writes        — .tmp → rename; no partial output on failure
  • Iteration DoS guard  — iteration / memory parameters validated on load
  • Version dispatch     — forward-compatible; old files readable after upgrades

Encrypted file layout (big-endian fixed-width header, then repeated chunks)
────────────────────────────────────────────────────────────────────────────

  FILE HEADER  (authenticated as AAD by every chunk's GCM tag)
  ┌─────────────────────────────────────────────┐
  │  4 B   magic        "GCRY"                  │
  │  2 B   version      u16  (currently 2)      │
  │  2 B   kdf_id       u16  (1 = Argon2id)     │
  │ 16 B   salt                                 │
  │ 12 B   base_nonce                           │
  │  4 B   time_cost    u32  (Argon2 t param)   │
  │  4 B   memory_cost  u32  (Argon2 m param)   │
  │  4 B   parallelism  u32  (Argon2 p param)   │
  │  4 B   chunk_size   u32  (plaintext bytes)  │
  │  8 B   original_size u64                    │
  └─────────────────────────────────────────────┘  total: 60 B

  CHUNK  (repeated; last chunk may be shorter)
  ┌─────────────────────────────────────────────┐
  │ 16 B   GCM auth tag                         │
  │  N B   ciphertext   (≤ chunk_size bytes)    │
  └─────────────────────────────────────────────┘

AAD passed to every GCM call = raw FILE HEADER bytes (all 60 B).
Tampering with any header field invalidates every chunk's tag.

Version history
───────────────
  v1 — PBKDF2-HMAC-SHA256, whole-file GCM (deprecated; read-only support)
  v2 — Argon2id, chunked streaming GCM  ← current write format
"""

from __future__ import annotations

import os
import struct
import logging
from pathlib import Path
from typing import Iterator

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag
from argon2.low_level import hash_secret_raw, Type

# ─────────────────────────────────────────────────────────────────────────────
# Public constants
# ─────────────────────────────────────────────────────────────────────────────

MAGIC           = b"GCRY"
VERSION         = 2          # current write version
KDF_ARGON2ID    = 1
KDF_PBKDF2      = 0          # v1 legacy

SALT_SIZE       = 16         # bytes
NONCE_SIZE      = 12         # bytes — GCM recommended
TAG_SIZE        = 16         # bytes — GCM 128-bit tag (maximum)
KEY_SIZE        = 32         # bytes — AES-256

# Argon2id defaults (OWASP 2023 interactive login baseline)
ARGON2_TIME_COST    = 3      # iterations
ARGON2_MEMORY_COST  = 65536  # KiB  (64 MiB)
ARGON2_PARALLELISM  = 4

# Argon2id parameter bounds — protect against DoS via crafted files
_ARGON2_TIME_MIN, _ARGON2_TIME_MAX       = 1,      16
_ARGON2_MEM_MIN,  _ARGON2_MEM_MAX        = 8192,   1_048_576   # 8 MiB – 1 GiB
_ARGON2_PAR_MIN,  _ARGON2_PAR_MAX        = 1,      64
_CHUNK_SIZE_MIN,  _CHUNK_SIZE_MAX        = 4096,   64 * 1024 * 1024

DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024   # 16 MiB plaintext per chunk

# v2 header: magic(4s) version(H) kdf_id(H) salt(16s) nonce(12s)
#            time_cost(I) memory_cost(I) parallelism(I) chunk_size(I) orig_size(Q)
_HDR_FMT  = f"!4sHH{SALT_SIZE}s{NONCE_SIZE}sIIIIQ"
HEADER_SIZE = struct.calcsize(_HDR_FMT)   # 60 bytes

# v1 legacy header (read-only)
_HDR_V1_FMT  = f"!4sH{SALT_SIZE}s{NONCE_SIZE}sIQ{TAG_SIZE}s"
_HDR_V1_SIZE = struct.calcsize(_HDR_V1_FMT)

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class CryptoError(Exception):
    """Raised on any encryption/decryption failure."""

class InvalidPasswordError(CryptoError):
    """Wrong password or corrupted/tampered file."""

class UnsupportedVersionError(CryptoError):
    """File was produced by a newer version of this library."""

# ─────────────────────────────────────────────────────────────────────────────
# Password policy
# ─────────────────────────────────────────────────────────────────────────────

MIN_PASSWORD_LENGTH = 8

def _validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise TypeError(f"Password must be str, got {type(password).__name__}.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )

# ─────────────────────────────────────────────────────────────────────────────
# KDF
# ─────────────────────────────────────────────────────────────────────────────

def _derive_key_argon2id(
    password: str,
    salt: bytes,
    time_cost: int,
    memory_cost: int,
    parallelism: int,
) -> bytes:
    """Memory-hard key derivation via Argon2id."""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=KEY_SIZE,
        type=Type.ID,
    )


def _derive_key_pbkdf2(password: str, salt: bytes, iterations: int) -> bytes:
    """Legacy PBKDF2-HMAC-SHA256 — used only when decrypting v1 files."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))

# ─────────────────────────────────────────────────────────────────────────────
# Nonce helpers
# ─────────────────────────────────────────────────────────────────────────────

def _chunk_nonce(base_nonce: bytes, index: int) -> bytes:
    """XOR the base nonce with the little-endian chunk index (96-bit counter)."""
    counter = index.to_bytes(NONCE_SIZE, "little")
    return bytes(a ^ b for a, b in zip(base_nonce, counter))

# ─────────────────────────────────────────────────────────────────────────────
# Plaintext chunk iterator
# ─────────────────────────────────────────────────────────────────────────────

def _iter_chunks(path: Path, chunk_size: int) -> Iterator[bytes]:
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            yield chunk

# ─────────────────────────────────────────────────────────────────────────────
# encrypt
# ─────────────────────────────────────────────────────────────────────────────

def encrypt(
    src: str | os.PathLike,
    dst: str | os.PathLike,
    password: str,
    *,
    time_cost: int    = ARGON2_TIME_COST,
    memory_cost: int  = ARGON2_MEMORY_COST,
    parallelism: int  = ARGON2_PARALLELISM,
    chunk_size: int   = DEFAULT_CHUNK_SIZE,
) -> None:
    """Encrypt *src* with *password* and write the result to *dst*.

    Encryption is fully streaming: memory usage is O(chunk_size), not O(file).
    The entire header is authenticated as AAD inside each chunk's GCM tag, so
    any tampering with version, KDF parameters, or sizes is detected.

    Args:
        src:          Path to the plaintext file.
        dst:          Path for the output encrypted file.
        password:     Passphrase; minimum 8 characters.
        time_cost:    Argon2id iteration count.
        memory_cost:  Argon2id memory in KiB (default 64 MiB).
        parallelism:  Argon2id lane count.
        chunk_size:   Plaintext bytes per GCM chunk (default 16 MiB).

    Raises:
        ValueError:        Password too short, or invalid parameter values.
        FileNotFoundError: *src* does not exist.
        CryptoError:       Internal failure.
        OSError:           I/O error.
    """
    _validate_password(password)
    src, dst = Path(src), Path(dst)

    if not src.is_file():
        raise FileNotFoundError(f"Source file not found: {src}")

    original_size = src.stat().st_size
    salt       = os.urandom(SALT_SIZE)
    base_nonce = os.urandom(NONCE_SIZE)

    logger.debug(
        "Deriving key via Argon2id (t=%d, m=%d, p=%d) …",
        time_cost, memory_cost, parallelism,
    )
    key = _derive_key_argon2id(password, salt, time_cost, memory_cost, parallelism)

    header = struct.pack(
        _HDR_FMT,
        MAGIC, VERSION, KDF_ARGON2ID,
        salt, base_nonce,
        time_cost, memory_cost, parallelism,
        chunk_size, original_size,
    )
    # AAD = entire header; binds every chunk's tag to all header fields.
    aad = header

    aesgcm    = AESGCM(key)
    tmp_dst   = dst.with_suffix(dst.suffix + ".tmp")

    try:
        with tmp_dst.open("wb") as out:
            out.write(header)
            for idx, plaintext_chunk in enumerate(_iter_chunks(src, chunk_size)):
                nonce = _chunk_nonce(base_nonce, idx)
                ct_and_tag = aesgcm.encrypt(nonce, plaintext_chunk, aad)
                # cryptography appends tag after ciphertext; store tag first for
                # easier streaming reads (reader knows tag size before ct size).
                tag = ct_and_tag[-TAG_SIZE:]
                ct  = ct_and_tag[:-TAG_SIZE]
                out.write(tag)
                out.write(ct)
                logger.debug("  chunk %d: %d bytes", idx, len(plaintext_chunk))

        tmp_dst.replace(dst)
    except Exception:
        tmp_dst.unlink(missing_ok=True)
        raise

    logger.info("Encrypted %s → %s  (%d bytes)", src, dst, original_size)

# ─────────────────────────────────────────────────────────────────────────────
# decrypt
# ─────────────────────────────────────────────────────────────────────────────

def decrypt(
    src: str | os.PathLike,
    dst: str | os.PathLike,
    password: str,
) -> None:
    """Decrypt *src* with *password* and write the plaintext to *dst*.

    Supports both v2 (Argon2id, chunked) and v1 (PBKDF2, whole-file) formats.
    Each chunk's GCM tag is verified before any plaintext is written.

    Args:
        src:      Path to the encrypted file.
        dst:      Path for the decrypted output file.
        password: Passphrase used during encryption.

    Raises:
        ValueError:            Password too short.
        FileNotFoundError:     *src* does not exist.
        InvalidPasswordError:  Wrong password or tampered/corrupt file.
        UnsupportedVersionError: File version newer than this library.
        CryptoError:           Other internal failure.
        OSError:               I/O error.
    """
    _validate_password(password)
    src, dst = Path(src), Path(dst)

    if not src.is_file():
        raise FileNotFoundError(f"Encrypted file not found: {src}")

    with src.open("rb") as fh:
        # Peek at magic + version before committing to a full header read.
        peek = fh.read(6)
        if len(peek) < 6:
            raise CryptoError("File too short to be a valid encrypted file.")
        magic, version = struct.unpack("!4sH", peek)

        if magic != MAGIC:
            raise CryptoError(
                f"Invalid magic {magic!r}; expected {MAGIC!r}. "
                "Is this a valid GCRY-encrypted file?"
            )

        if version == 2:
            _decrypt_v2(fh, dst, password, peek)
        elif version == 1:
            logger.warning("Decrypting legacy v1 file; consider re-encrypting.")
            _decrypt_v1(fh, dst, password, peek)
        else:
            raise UnsupportedVersionError(
                f"File version {version} is not supported by this library "
                f"(max supported: {VERSION}). Please upgrade."
            )


def _decrypt_v2(fh, dst: Path, password: str, peek: bytes) -> None:
    """Decrypt a v2 (Argon2id + chunked GCM) file."""
    remaining_header = fh.read(HEADER_SIZE - len(peek))
    if len(remaining_header) < HEADER_SIZE - len(peek):
        raise CryptoError("Truncated v2 header.")
    raw_header = peek + remaining_header

    (
        _magic, _version, kdf_id,
        salt, base_nonce,
        time_cost, memory_cost, parallelism,
        chunk_size, original_size,
    ) = struct.unpack(_HDR_FMT, raw_header)

    # ── Validate KDF parameters to prevent DoS via crafted file ──────────────
    if kdf_id != KDF_ARGON2ID:
        raise CryptoError(f"Unknown KDF id {kdf_id} in v2 file.")
    if not (_ARGON2_TIME_MIN <= time_cost    <= _ARGON2_TIME_MAX):
        raise CryptoError(f"time_cost {time_cost} out of safe range.")
    if not (_ARGON2_MEM_MIN  <= memory_cost  <= _ARGON2_MEM_MAX):
        raise CryptoError(f"memory_cost {memory_cost} out of safe range.")
    if not (_ARGON2_PAR_MIN  <= parallelism  <= _ARGON2_PAR_MAX):
        raise CryptoError(f"parallelism {parallelism} out of safe range.")
    if not (_CHUNK_SIZE_MIN  <= chunk_size   <= _CHUNK_SIZE_MAX):
        raise CryptoError(f"chunk_size {chunk_size} out of safe range.")

    logger.debug(
        "Deriving key via Argon2id (t=%d, m=%d, p=%d) …",
        time_cost, memory_cost, parallelism,
    )
    key    = _derive_key_argon2id(password, salt, time_cost, memory_cost, parallelism)
    aesgcm = AESGCM(key)
    aad    = raw_header   # same AAD as used during encryption

    tmp_dst       = dst.with_suffix(dst.suffix + ".tmp")
    written_bytes = 0
    idx           = 0

    try:
        with tmp_dst.open("wb") as out:
            while True:
                tag = fh.read(TAG_SIZE)
                if not tag:
                    break   # clean end of file
                if len(tag) < TAG_SIZE:
                    raise CryptoError(f"Truncated tag in chunk {idx}.")

                ct = fh.read(chunk_size)
                if not ct:
                    raise CryptoError(f"Missing ciphertext for chunk {idx}.")

                nonce = _chunk_nonce(base_nonce, idx)
                try:
                    plaintext = aesgcm.decrypt(nonce, ct + tag, aad)
                except InvalidTag:
                    raise InvalidPasswordError(
                        f"Authentication failed on chunk {idx}. "
                        "The file is corrupt, has been tampered with, "
                        "or the password is incorrect."
                    )

                out.write(plaintext)
                written_bytes += len(plaintext)
                idx += 1

        if written_bytes != original_size:
            tmp_dst.unlink(missing_ok=True)
            raise CryptoError(
                f"Decrypted size {written_bytes} does not match "
                f"recorded original size {original_size}."
            )

        tmp_dst.replace(dst)
    except Exception:
        tmp_dst.unlink(missing_ok=True)
        raise

    logger.info("Decrypted (v2) → %s  (%d bytes)", dst, written_bytes)


def _decrypt_v1(fh, dst: Path, password: str, peek: bytes) -> None:
    """Decrypt a legacy v1 (PBKDF2 + whole-file GCM) file.  Read-only support."""
    remaining = fh.read(_HDR_V1_SIZE - len(peek))
    raw_header = peek + remaining
    if len(raw_header) < _HDR_V1_SIZE:
        raise CryptoError("Truncated v1 header.")

    _magic, _version, salt, nonce, iterations, original_size, tag = \
        struct.unpack(_HDR_V1_FMT, raw_header)

    # Guard against pathological iteration counts even in legacy files
    if not (100_000 <= iterations <= 5_000_000):
        raise CryptoError(
            f"v1 iteration count {iterations} is outside the accepted range "
            "[100 000, 5 000 000]."
        )

    key    = _derive_key_pbkdf2(password, salt, iterations)
    aesgcm = AESGCM(key)
    ciphertext = fh.read()

    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
    except InvalidTag:
        raise InvalidPasswordError(
            "Authentication failed (v1 file). "
            "The file is corrupt, has been tampered with, "
            "or the password is incorrect."
        )

    if len(plaintext) != original_size:
        raise CryptoError(
            f"Decrypted size {len(plaintext)} ≠ recorded size {original_size} (v1)."
        )

    tmp_dst = dst.with_suffix(dst.suffix + ".tmp")
    try:
        tmp_dst.write_bytes(plaintext)
        tmp_dst.replace(dst)
    except Exception:
        tmp_dst.unlink(missing_ok=True)
        raise

    logger.info("Decrypted (v1 legacy) → %s  (%d bytes)", dst, len(plaintext))
