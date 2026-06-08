# CERA User Node

A desktop client for the CERA distributed storage network. Users can upload files to the network with client-side encryption and erasure coding, then retrieve them from any machine using their decryption key.

---

## How it works

Before a file leaves the machine it goes through three steps:

1. **Encryption** — AES-256-GCM with an Argon2id-derived key. The password never leaves the device; the server only ever sees ciphertext.
2. **Erasure coding** — the encrypted file is split into *m* shards using [zfec](https://github.com/tahoe-lafs/zfec). Any *k* of those shards are sufficient to reconstruct the file, so the network can tolerate losing up to *m − k* storage nodes.
3. **Upload** — shards are streamed over ZMQ directly to the storage nodes listed in the signed contract.

Download reverses the process: collect *k* shards → decode → decrypt → write to `data/downloaded data/`.

---

## Requirements

- Python **3.10 or 3.11**
- [Poetry](https://python-poetry.org/) (recommended) **or** pip

---

## Installation

### With Poetry (recommended)

```bash
git clone https://github.com/ComputeHive/user-node.git
cd User-Node
poetry install
```

### With pip

```bash
pip install -r requirements.txt
# zfec is vendored; install it separately:
pip install libraries/zfec-1.5.5+1.g0bee9e7.zip
```

---

## Running

```bash
# Poetry
poetry run python main.py

# Plain Python
python main.py
```

The app starts in **local mode** by default (see [Configuration](#configuration)), so no backend or storage nodes are required. You can upload and download files entirely on your own machine.

---

## Configuration

All settings are controlled by environment variables. Copy `.env.example` to `.env` and adjust as needed.

| Variable | Default | Description |
|---|---|---|
| `CERA_LOCAL_MODE` | `1` | `1` = fully offline; `0` = connect to real backend and storage nodes |
| `CERA_HOST_URL` | `http://localhost:5000/` | Coordinator API base URL (production only) |
| `CERA_DEV_TOKEN` | `dev_token` | Token written to cache when local mode skips login |
| `CERA_BYPASS_LOGIN` | `LOCAL_MODE` | Skip the login API call |
| `CERA_BYPASS_CONTRACT` | `LOCAL_MODE` | Skip on-chain contract state check |
| `CERA_BYPASS_PRICE` | `LOCAL_MODE` | Return a fixed dev price instead of calling the API |
| `CERA_BYPASS_CREATE_FILE` | `LOCAL_MODE` | Skip file contract registration |
| `CERA_BYPASS_GET_FILES` | `LOCAL_MODE` | Read local index instead of the file list API |
| `CERA_BYPASS_UPLOAD` | `LOCAL_MODE` | Copy shards to `data/dev_host/` instead of ZMQ upload |
| `CERA_BYPASS_DOWNLOAD` | `LOCAL_MODE` | Read shards from `data/dev_host/` instead of ZMQ download |

Individual `CERA_BYPASS_*` variables override `CERA_LOCAL_MODE`, so you can disable specific integrations while keeping the rest live.

---

## Usage

### Local mode (default)

1. Launch the app — it opens directly to the main menu.
2. Click **Upload Files** → browse for a file → set contract parameters → enter an encryption key (max 32 characters) → **Start Uploading**.
3. When the upload completes, click **Show Files** → select the file → enter the same key → **Download** to retrieve it.

Downloaded files are saved to `data/downloaded data/`.

### Production mode

Set `CERA_LOCAL_MODE=0` and point `CERA_HOST_URL` at a running coordinator. The upload flow adds a contract creation step: the coordinator returns the list of storage node addresses, and shards are streamed directly to those nodes over ZMQ.

---

## Project structure

```
User-Node/
├── main.py                              Entry point — builds AppContainer, launches PageController
├── config/
│   └── settings.py                      All env-var config (LOCAL_MODE, BYPASS_* flags, URLs)
├── core/
│   ├── erasure_params.py                Pure erasure-coding arithmetic (k, m); no I/O
│   ├── paths.py                         AppPaths value object — all runtime directory/file paths
│   └── user_state.py                    Upload-state constants and their display strings
├── application/
│   ├── container.py                     DI container — constructs and wires every service once
│   ├── upload_service.py                Upload pipeline use-case (encrypt → encode → transfer)
│   └── download_service.py             Download pipeline use-case (fetch shards → decode → decrypt)
├── infrastructure/
│   ├── api/
│   │   ├── cera_client.py               Production HTTP client for the CERA coordinator
│   │   └── cera_client_dev.py           Offline stand-in — fulfils the same interface from disk
│   ├── storage/
│   │   └── local_index.py               Per-file shard index for dev/local mode
│   ├── transfer/
│   │   └── shard_transfer.py            ZMQ shard send/receive (falls back to file-copy in dev mode)
│   ├── filesystem.py                    Disk bootstrap — creates runtime directories on first run
│   ├── token_repository.py              Read/write the auth token cache file
│   └── transfer_repository.py          Persist upload/download transfer state (JSON)
├── presentation/
│   ├── controllers/
│   │   ├── page_controller.py           Navigation hub — owns the main window and page stack
│   │   └── worker.py                    Background task runner (QThreadPool)
│   ├── pages/
│   │   ├── login.py
│   │   ├── main.py
│   │   ├── upload_main.py
│   │   ├── show_files.py
│   │   ├── contract_details.py
│   │   └── transition.py
│   └── widgets/
│       ├── progress_bar.py              Thread-safe Qt progress bar (byte-count → signal)
│       └── qt_signals.py               Signal helpers that marshal calls to the main thread
├── utils/
│   ├── encryption.py                    AES-256-GCM streaming encryption / decryption
│   ├── erasure_coding.py                zfec encode/decode wrappers
│   └── audits.py                        File integrity audit generation
├── gui/
│   ├── ui.py                            Qt Designer generated UI bindings
│   ├── cera.ui                          Qt Designer source file
│   ├── cera_logo.qrc                    Qt resource file (logo assets)
│   └── resources/                       Icons and images
├── cera_logo_rc.py                      Compiled Qt resource module (generated from .qrc)
├── data/                                Runtime data (git-ignored)
│   ├── cache/                           Auth token and transfer state
│   ├── shards/                          In-progress erasure coded shards
│   ├── segments/                        In-progress file segments
│   ├── encrypted/                       In-progress encrypted segments
│   ├── dev_host/                        Local shard store (local mode only)
│   └── downloaded data/                 Completed downloads
├── libraries/
│   └── zfec-1.5.5+1.g0bee9e7.zip       Vendored zfec wheel
├── test.py                              End-to-end pipeline test (encrypt → encode → decode → decrypt)
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

## Encryption details

Files are encrypted with **AES-256-GCM** using a key derived from the user's password via **Argon2id** (memory-hard, GPU/ASIC resistant). The encrypted file format is:

```
HEADER (60 bytes, authenticated as AAD by every chunk)
  magic         "GCRY"
  version       u16
  kdf_id        u16   (1 = Argon2id)
  salt          16 B
  base_nonce    12 B
  time_cost     u32
  memory_cost   u32
  parallelism   u32
  chunk_size    u32
  original_size u64

CHUNKS (repeated)
  GCM auth tag  16 B
  ciphertext    ≤ chunk_size B
```

Per-chunk nonces are derived as `base_nonce XOR little-endian(chunk_index)`, so nonces are never reused. Tampering with any header field invalidates every chunk's authentication tag.

---

## Erasure coding details

Each file is split into segments (default 500 MB each). Every segment is erasure-coded independently with [zfec](https://github.com/tahoe-lafs/zfec). The default parameters are:

- **k = 2** — minimum shards needed to reconstruct
- **m = k + 1 = 3** — total shards produced

This means one storage node can go offline without losing the file. Both k and m scale with the network contract parameters.

---

## Dependencies

| Package | Purpose |
|---|---|
| PyQt5 | Desktop GUI |
| pyzmq | Shard transfer to/from storage nodes |
| cryptography | AES-256-GCM, PBKDF2 |
| argon2-cffi | Argon2id key derivation |
| pycryptodome | Legacy crypto support |
| zfec (vendored) | Erasure coding |
| requests | Coordinator API HTTP client |
| psutil | Memory info for segment sizing |
