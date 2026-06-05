# User-Node (CERA client)

PyQt5 desktop client for encrypting files, erasure-coding them into shards, and uploading or downloading via the Decentorage network.

## Local mode (no host, login, or payment)

By default the app runs in **local mode** so you can exercise the full pipeline without a coordinator, contract payment, or storage nodes:

| Step | What happens |
|------|----------------|
| Upload | Shards are copied to `data/dev_host/` instead of ZMQ |
| Download | Shards are read back from `data/dev_host/` |
| Login / contract / price | Bypassed; app opens on the main screen |

1. Run the app: `python main.py`
2. **Upload files** → pick a file → set contract details → **Request** (no browser in local mode) → enter encryption key (1–32 chars) → **Start Uploading**
3. **Show my files** → select your uploaded file → enter the same key → **Download**

Reconstructed files appear under `data/downloaded data/`.

### Turn off local mode (production)

```powershell
$env:CERA_MODE="0"
python main.py
```

Or set `CERA_LOCAL_MODE=0` in your environment. Configure `helper.host_url` in `utils/helper.py` for your API.

### Optional overrides

See `.env.example`. Per-feature bypass flags (`CERA_BYPASS_LOGIN`, etc.) default to the value of `CERA_LOCAL_MODE`.

## Setup

```bash
pip install -r requirements.txt
# zfec wheel from pyproject.toml / poetry if using erasure coding
python main.py
```

## Layout

- `utils/` — API (`cera.py`), transfer (`file_transfer_user.py`), crypto pipeline (`file_handler.py`)
- `data/dev_host/` — local shard store and per-file `*.index.json` indices (local mode)
- `pages/` — PyQt UI screens
