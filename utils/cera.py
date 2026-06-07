"""
cera.py  –  API layer for the CERA backend
=========================================================
Every function checks the relevant BYPASS_* flag from dev_config
before making a network call.  When the flag is True the function
fulfils its contract using only local data / filesystem operations
so the rest of the app works exactly as in production.
"""

import requests
import json
import os

from utils.helper import Helper
from utils.local_storage import (
    dev_host_dir,
    load_index,
    list_stored_files,
    register_completed_upload,
    save_index,
)
from utils.dev_config import (
    BYPASS_LOGIN,
    BYPASS_CONTRACT,
    BYPASS_PRICE, DEV_PRICE_WEI,
    BYPASS_CREATE_FILE,
    BYPASS_GET_FILES, DEV_FAKE_FILES,
    BYPASS_UPLOAD_TRANSFER,
    BYPASS_DOWNLOAD_TRANSFER,
)

helper: Helper = None


# =========================================================
# MODULE INIT
# =========================================================
def init_cera(helper_obj: Helper):
    """Initialise the module with the shared Helper instance."""
    global helper
    helper = helper_obj


# =========================================================
# AUTH
# =========================================================
def user_login(username: str, password: str):
    """
    Authenticate the user.

    Dev mode: accepts any credentials and writes "dev_token" to the
    cache file so downstream calls that check helper.token work.
    """
    if BYPASS_LOGIN:
        _write_token("dev_token")
        print("[DEV] Login bypassed – token set to 'dev_token'")
        return

    try:
        response = requests.post(
            helper.host_url + "/users/signin",
            json={"username": username, "password": password},
        )
    except Exception:
        raise Exception(helper.server_not_responding)

    if response.status_code == 200:
        _write_token(response.json()["token"])
    else:
        raise Exception(response.text)


# =========================================================
# STATE
# =========================================================
def get_user_state(ui):
    """
    Return the user's current upload state string.

    Dev mode: always returns state_upload_file ("1") so the upload
    UI is fully enabled without a paid on-chain contract.
    """
    if BYPASS_CONTRACT:
        print(f"[DEV] get_user_state → '{helper.state_upload_file}'")
        return helper.state_upload_file

    return _api_get(
        helper.host_url + "/users/me/state",
        ui,
        lambda r: r.json()["state"],
    )


# =========================================================
# PRICING
# =========================================================
def get_price(contract_details: dict, ui):
    """
    Return the contract price in wei.

    Dev mode: returns DEV_PRICE_WEI without contacting the server.
    """
    if BYPASS_PRICE:
        print(f"[DEV] get_price → {DEV_PRICE_WEI} wei")
        return DEV_PRICE_WEI

    return _api_get(
        helper.host_url + "/users/me/files/pending/price",
        ui,
        lambda r: r.json()["price"],
        params={
            "download_count":     contract_details["download_count"],
            "duration_in_months": contract_details["duration_in_months"],
            "file_size":          contract_details["file_size"],
        },
    )


# =========================================================
# FILE MANAGEMENT
# =========================================================
def get_user_files(ui):
    """
    Return the list of files stored by the user.

    Dev mode: returns DEV_FAKE_FILES so the Show-Files page renders
    without a running backend.
    """
    if BYPASS_GET_FILES:
        stored = list_stored_files()
        if stored:
            print(f"[DEV] get_user_files → {len(stored)} local file(s)")
            return stored
        print(f"[DEV] get_user_files → {len(DEV_FAKE_FILES)} sample file(s)")
        return DEV_FAKE_FILES

    return _api_get(
        helper.host_url + "/users/me/files",
        ui,
        lambda r: r.json(),
    )


def create_file(contract_details: dict, ui):
    """
    Register a new file contract on the server.

    Dev mode: always returns True without an HTTP call.
    """
    if BYPASS_CREATE_FILE:
        print("[DEV] create_file → True")
        return True

    response = None
    try:
        token = helper.token
        if not token:
            worker_error_page("Please Login again", "", ui, ui.login_page)
            return False
        response = requests.post(
            helper.host_url + "/users/me/files",
            headers={"TOKEN": token},
            json=json.dumps(contract_details),
        )
    except Exception:
        worker_error_page("Error", helper.server_not_responding, ui)
        return False

    if response.status_code == 201:
        return True
    if response.status_code == 409:
        worker_error_page("Error", "This file is already stored.", ui)
        return False
    ui.stackedWidget.setCurrentWidget(ui.upload_main_page)
    return False


# =========================================================
# UPLOAD PIPELINE
# =========================================================
def get_pending_file_info(ui):
    """
    Return metadata for the pending upload (file size + per-segment
    shard descriptors with IPs / ports / shard IDs).

    Dev mode: builds the same metadata structure locally using the
    Helper's erasure-coding parameters.  Shard IDs use the real
    filenames that process_segment will create; ip/port are set to
    localhost values that dev send_data ignores.
    """
    if BYPASS_UPLOAD_TRANSFER:
        transfer_obj = helper.read_transfer_file()
        if not transfer_obj:
            worker_error_page("Error", "No pending transfer file found.", ui)
            return False

        file_path = transfer_obj.get("file_path")
        if not file_path or not os.path.exists(file_path):
            worker_error_page("Error", "Pending file not found on disk.", ui)
            return False

        file_size = os.stat(file_path).st_size
        segments, segments_count = helper.get_file_metadata(file_size)

        dev_segments = []
        for seg_idx, seg in enumerate(segments):
            k, m = seg["k"], seg["m"]
            shards = []
            for shard_no in range(m):
                shard_id = (
                    f"{helper.shard_filename}_{seg_idx}.{shard_no}_{m}.fec"
                )
                shards.append({
                    "shard_id":                shard_id,
                    "shard_no":                shard_no,
                    "segment_no":              seg_idx,
                    "ip_address":              "127.0.0.1",
                    "port":                    5555 + shard_no,
                    "shared_authentication_key": "dev_auth_key",
                    "done_uploading":          False,
                })
            dev_segments.append({
                "k":              k,
                "m":              m,
                "shard_size":     seg["shard_size"],
                "shards":         shards,
                "done_uploading": False,
                "processed":      False,
            })

        print(f"[DEV] get_pending_file_info → {segments_count} segment(s), file_size={file_size}")
        return {"file_size": file_size, "segments": dev_segments}

    return _api_get(
        helper.host_url + "/users/me/files/pending",
        ui,
        lambda r: r.json(),
    )


def shard_done_uploading(shard_id: str, audits: list, ui):
    """
    Notify the server that a shard upload is complete.

    Dev mode: no-op (prints confirmation, returns True).
    """
    if BYPASS_UPLOAD_TRANSFER:
        print(f"[DEV] shard_done_uploading → {os.path.basename(shard_id)} (skipped)")
        return True

    response = None
    try:
        token = helper.token
        if not token:
            worker_error_page("Please Login again", "", ui, ui.login_page)
            return False
        response = requests.patch(
            helper.host_url + "/users/me/files/pending/shards/done",
            json={"shard_id": os.path.basename(shard_id), "audits": audits},
            headers={"TOKEN": token},
        )
    except Exception:
        worker_error_page("Error", helper.server_not_responding, ui)
        return False

    if response and response.status_code == 204:
        return True
    worker_error_page("Please Login again", "", ui, ui.login_page)
    return False


def file_done_uploading(ui, filename: str | None = None):
    """
    Notify the server that the entire file has been uploaded.

    Local mode: finalize dev_host index (optional filename if transfer cache is gone).
    """
    if BYPASS_UPLOAD_TRANSFER:
        transfer_obj = helper.read_transfer_file()
        fname = filename
        if not fname and transfer_obj and transfer_obj.get("file_path"):
            fname = os.path.basename(transfer_obj["file_path"])
        if fname:
            register_completed_upload(fname, transfer_obj)
            print(f"[DEV] file_done_uploading → index finalized for '{fname}'")
        else:
            print("[DEV] file_done_uploading → (skipped)")
        return True

    return _api_get(
        helper.host_url + "/users/me/files/pending/done",
        ui,
        lambda r: True,
        method="PATCH",
    )


# =========================================================
# DOWNLOAD PIPELINE
# =========================================================
def start_download(filename: str, ui):
    """
    Initiate a download and get the shard location list.

    Dev mode: scans data/dev_host/ for shards that were saved during
    a previous dev-mode upload of *filename* and returns the same
    metadata shape that the real server would return.
    """
    if BYPASS_DOWNLOAD_TRANSFER:
        _ = dev_host_dir()
        meta, segments = load_index(filename)
        if not segments:
            worker_error_page(
                "Error",
                f"No local shards found for '{filename}'.\n"
                "Upload the file first (LOCAL_MODE), then download it here.",
                ui,
            )
            return False

        if meta:
            meta["download_count"] = meta.get("download_count", 0) + 1
            save_index(filename, meta, segments)

        print(f"[DEV] start_download → loaded index for '{filename}'")
        return segments

    response = None
    try:
        token = helper.token
        if not token:
            worker_error_page("Please Login again", "", ui, ui.login_page)
            return False
        response = requests.post(
            helper.host_url + f"/users/me/files/{filename}/downloads",
            headers={"TOKEN": token},
        )
    except Exception:
        worker_error_page("Error", helper.server_not_responding, ui)
        return False

    if response.status_code == 200:
        return response.json()["segments"]
    if response.status_code in (404, 405):
        worker_error_page("Error", response.text, ui)
        return False
    worker_error_page("Please Login again", "", ui, ui.login_page)
    return False


# =========================================================
# ERROR UI HELPER
# =========================================================
def worker_error_page(title: str, body: str, gui, target=None):
    """
    Show an error on the UI error page.

    :param title:  Short error title.
    :param body:   Longer description.
    :param gui:    Ui_MainWindow instance.
    :param target: Page to return to after dismissal (defaults to
                   the current page).  When set, the cache file is
                   also deleted (forces re-login).
    """
    gui.error_body.setText(body)
    gui.error_title.setText(title)

    if target:
        gui.error_source_page = target
        try:
            os.remove(helper.cache_file)
        except OSError:
            pass
    else:
        gui.error_source_page = gui.stackedWidget.currentWidget()

    gui.stackedWidget.setCurrentWidget(gui.error_page)


# =========================================================
# INTERNAL HELPERS
# =========================================================
def _write_token(token: str):
    with open(helper.cache_file, "w", encoding="utf-8") as f:
        f.write(token)


def _api_get(url: str, ui, extract_fn, params=None, method: str = "GET"):
    """
    DRY wrapper for authenticated GET/PATCH requests.
    Returns extract_fn(response) on HTTP 200/204, False otherwise.
    """
    response = None
    try:
        token = helper.token
        if not token:
            worker_error_page("Please Login again", "", ui, ui.login_page)
            return False
        if method == "PATCH":
            response = requests.patch(url, headers={"TOKEN": token})
        else:
            response = requests.get(url, params=params, headers={"TOKEN": token})
    except Exception:
        worker_error_page("Error", helper.server_not_responding, ui)
        return False

    if response and response.status_code in (200, 204):
        return extract_fn(response)

    worker_error_page("Please Login again", "", ui, ui.login_page)
    return False