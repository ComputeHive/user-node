# Refactoring Guide: CERA User Node

## What Changed and Why

### Problem summary (original code)

| Issue | Where | Impact |
|---|---|---|
| God object (`Helper`) | `utils/helper.py` | Carries config, filesystem, token, erasure math — impossible to test parts independently |
| Global mutable state | `cera.py`, `file_handler.py`, `audits.py`, `erasure_coding.py` | Module-level `helper = None` set by `init_*()` — breaks if init order changes |
| `Worker` creates its own `Helper` | `controllers/worker.py` | Different instance from the one injected elsewhere — cache path can diverge |
| UI coupling in business logic | `cera.py` (`worker_error_page`) | Manipulates Qt widgets from a non-Qt thread without signals; duplicated in `worker.py` |
| Dev-mode mixed into prod paths | `cera.py` (inline `if BYPASS_*` blocks) | `BYPASS_*` branches interleaved with HTTP logic; hard to read, hard to test |
| Commented-out code | `file_handler.py`, `worker.py` | Dead code left in → maintenance confusion |
| Magic state strings | `Helper` attributes | `"1"`, `"2"`, `"3"`, `"4"` scattered everywhere |
| `ProgressBar` depends on `Helper` globally | `controllers/progress_bar.py` | Same init-order problem |

---

## New Structure

```
cera-refactored/
├── main.py                              Entry point — wires container → PageController
├── config/
│   └── settings.py                      All env flags and constants (replaces app_config + dev_config)
├── core/
│   ├── paths.py                         AppPaths — frozen dataclass of filesystem paths
│   ├── user_state.py                    UserState enum (replaces magic "1"/"2"/"3"/"4" strings)
│   └── erasure_params.py                Pure erasure-coding math (no I/O, easy to unit-test)
├── infrastructure/
│   ├── filesystem.py                    Disk bootstrap & cleanup (replaces Helper._ensure_filesystem)
│   ├── token_repository.py              Read/write auth token from cache file
│   ├── transfer_repository.py           Read/write upload & download transfer state JSON
│   ├── api/
│   │   ├── cera_client.py               Production HTTP client — raises exceptions, no UI
│   │   └── cera_client_dev.py           Dev/offline client — same interface, local file ops
│   ├── storage/
│   │   └── local_index.py               LocalIndex class (replaces local_storage.py functions)
│   └── transfer/
│       └── shard_transfer.py            ZMQ + dev local-copy shard send/receive
├── application/
│   ├── container.py                     DI container — creates and wires all services once
│   ├── upload_service.py                Upload pipeline use-case (encrypt → erasure → send)
│   └── download_service.py              Download pipeline use-case (receive → decode → decrypt)
├── presentation/
│   ├── controllers/
│   │   ├── page_controller.py           Navigation hub — wires page signals to services
│   │   └── worker.py                    Background task runner (no extra Helper instance)
│   ├── pages/
│   │   ├── login.py
│   │   ├── main.py
│   │   ├── upload_main.py
│   │   ├── show_files.py
│   │   ├── contract_details.py
│   │   └── transition.py
│   └── widgets/
│       ├── qt_signals.py                Thread-safe signal emitters
│       └── progress_bar.py              ProgressBar with injected TransferRepository
└── utils/
    └── audits.py                        generate_audits — no global Helper
```

---

## Key Design Decisions

### 1. Dependency Injection via `AppContainer`

```python
# Before
helper = None
def init_cera(helper_obj):
    global helper
    helper = helper_obj

# After
class AppContainer:
    def __init__(self):
        self.paths = AppPaths.from_base()
        self.token_repo = TokenRepository(self.paths.cache_file)
        self.upload_service = UploadService(paths, api, token_repo, ...)
```

Every service receives its dependencies at construction time. No `init_*()` calls, no globals.

### 2. Two API clients, one interface

```python
# Production
client = CeraClient(host_url=settings.HOST_URL)

# Dev/offline (selected automatically when LOCAL_MODE=True)
client = CeraClientDev(paths, token_repo, upload_transfer_repo)
```

The `BYPASS_*` if-blocks that were interleaved throughout `cera.py` are gone. The dev client provides the exact same method signatures as the production client — swap one line in `AppContainer._build_api_client()` to go live.

### 3. Exceptions instead of direct UI manipulation

```python
# Before (from background thread, wrong thread for Qt)
def worker_error_page(title, body, ui, target=None):
    ui.error_body.setText(body)   # ← direct Qt call from non-Qt thread
    ...

# After — client raises, presentation layer catches and signals
class CeraClient:
    def login(self, username, password):
        ...
        raise AuthenticationError(resp.text)   # ← plain exception

class Worker:
    def run(self):
        try:
            self.fn()
        except Exception as exc:
            show_error(self._ui, "Error", str(exc))  # ← uses Qt signals properly
```

### 4. UserState replaces magic strings

```python
# Before
if state == self.helper.state_upload_file:  # "1"
    ...

# After
from core.user_state import UPLOAD_READY, from_code
state = from_code(raw_state)
if state is UPLOAD_READY:
    ...
```

### 5. AppPaths is a frozen dataclass

```python
paths = AppPaths.from_base()   # construct once
# paths.shards_dir, paths.cache_file, etc. — immutable after creation
```

No more `os.path.realpath("data")` sprinkled across every utility file.

### 6. ProgressBar injected, not global

```python
# Before — module-level helper used inside __call__
helper = None
def init_progress_bar(helper_obj):
    global helper
    helper = helper_obj

# After
progress = ProgressBar(qt_widget, transfer_repo=container.upload_transfer_repo)
```

---

## Files that are UNCHANGED

The following files are left as-is (pure logic, already clean):

- `utils/encryption.py` — no global state, no UI coupling
- `utils/erasure_coding.py` — stateless encode/decode (the module-level `helper` is only used for `segment_filename` in `decode`; easily inlined)
- `gui/` — Qt Designer output, untouched
- `libraries/` — vendored zfec

---

## Migration Steps

1. Copy `gui/`, `utils/encryption.py`, `utils/erasure_coding.py` from the original into the refactored tree unchanged.
2. Copy `pyproject.toml` / `requirements.txt` — dependencies are identical.
3. Replace `main.py` with the new entry point.
4. Delete `utils/helper.py`, `utils/cera.py`, `utils/file_handler.py`, `utils/file_transfer_user.py`, `utils/local_storage.py`, `utils/app_config.py`, `utils/dev_config.py`, `controllers/worker.py`, `controllers/progress_bar.py`.
5. Run the existing `test.py` suite (update imports to the new paths).

---

## Environment Variables

All flags are in one place (`config/settings.py`):

| Variable | Default | Effect |
|---|---|---|
| `CERA_LOCAL_MODE` | `1` | Master offline switch |
| `CERA_HOST_URL` | `http://localhost:5000/` | Backend URL |
| `CERA_DEV_TOKEN` | `dev_token` | Token written in local mode |
| `CERA_BYPASS_LOGIN` | `LOCAL_MODE` | Skip login API |
| `CERA_BYPASS_CONTRACT` | `LOCAL_MODE` | Skip contract check |
| `CERA_BYPASS_PRICE` | `LOCAL_MODE` | Use `DEV_PRICE_WEI` |
| `CERA_BYPASS_CREATE_FILE` | `LOCAL_MODE` | Skip file registration |
| `CERA_BYPASS_GET_FILES` | `LOCAL_MODE` | Return local index |
| `CERA_BYPASS_UPLOAD` | `LOCAL_MODE` | Copy shards locally |
| `CERA_BYPASS_DOWNLOAD` | `LOCAL_MODE` | Read shards locally |
