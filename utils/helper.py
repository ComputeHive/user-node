import os
import glob
import math
import json
from psutil import virtual_memory


class Helper:
    kilobyte = 1024
    megabyte = kilobyte * 1024
    gigabyte = megabyte * 1024

    def __init__(self):
        base = os.path.realpath("data")
        cache_dir = os.path.join(base, "cache")

        # -------------------------
        # Directories
        # -------------------------
        self.shards_directory_path = os.path.join(base, "shards")
        self.segments_directory_path = os.path.join(base, "segments")
        self.downloaded_output = os.path.join(base, "downloaded data")
        self.encryption_directory = os.path.join(base, "encrypted")

        # -------------------------
        # Cache files
        # -------------------------
        self.cache_file = os.path.join(cache_dir, "cera_cache")
        self.transfer_file = os.path.join(cache_dir, "cera_transfer.json")
        self.download_transfer_file = os.path.join(cache_dir, "download_cera_transfer.json")
        self.upload_connection_file = os.path.join(cache_dir, "connections.txt")

        # -------------------------
        # Other resources
        # -------------------------
        self.icon_path = os.path.realpath("gui/resources/cera_icon.png")

        self.shard_filename = "shard"
        self.segment_filename = "segment"

        self.send_chunk_size = int(0.5 * self.megabyte)
        self.receive_timeout = 8000
        self.disconnect_timeout = 1000 * 60 * 60

        # -------------------------
        # URLs / config
        # -------------------------
        self.host_url = os.environ.get("CERA_HOST_URL", "http://localhost:5000/")
        if not self.host_url.endswith("/"):
            self.host_url += "/"
        self.frontend_url = "http://localhost:3000/users"
        self.client_url_prefix = "users/"

        self.server_not_responding = "Check your internet connection"

        self.erasure_factor = 1
        self.minimum_data_shard = 2
        self.audits_default_count = 100
        self.upload_polling_time = 2
        self.min_price = 0.25

        self.state_upload_file = "1"
        self.state_upload_file_text = "Please enter your encryption key and start your upload"
        self.state_unpaid_pending_contract = "2"
        self.state_unpaid_pending_contract_text = "Please add balance to the contract to start uploading"
        self.state_create_contract = "3"
        self.state_create_contract_text = "You have seeds, please select a file to upload"
        self.state_no_seeds = "4"
        self.state_no_seeds_text = "You have to request a seed before you can select a file to upload"

        self.token = None

        # -------------------------
        # Segment size (test value)
        # -------------------------
        self.segment_size = int(500 * self.megabyte)

        # -------------------------
        # Ensure filesystem is ready
        # -------------------------
        self._ensure_filesystem()

    # =========================================================
    # FILESYSTEM BOOTSTRAP
    # =========================================================
    def _ensure_filesystem(self):
        dirs = [
            self.shards_directory_path,
            self.segments_directory_path,
            self.downloaded_output,
            self.encryption_directory,
            os.path.join(os.path.dirname(os.path.dirname(self.cache_file)), "dev_host"),
            os.path.dirname(self.cache_file),
        ]

        for d in dirs:
            os.makedirs(d, exist_ok=True)

        files = [
            self.cache_file,
            self.transfer_file,
            self.download_transfer_file,
            self.upload_connection_file,
        ]

        for f in files:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            if not os.path.exists(f):
                with open(f, "w", encoding="utf-8") as fh:
                    # connections file needs valid JSON; others start empty
                    if f == self.upload_connection_file:
                        json.dump({"connections": []}, fh)
            elif f == self.upload_connection_file:
                # Fix existing empty/corrupt connections file
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        json.load(fh)
                except (json.JSONDecodeError, ValueError):
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump({"connections": []}, fh)

    # =========================================================
    # FILE UTILITIES
    # =========================================================
    def get_encryption_file_path(self, filename):
        return os.path.realpath(
            os.path.join(self.encryption_directory, f"{filename}.enc")
        )

    # =========================================================
    # CLEANUP
    # =========================================================
    def reset_directories(self):
        for path in [self.segments_directory_path, self.encryption_directory]:
            for f in glob.glob(os.path.join(path, "*")):
                try:
                    os.remove(f)
                except FileNotFoundError:
                    pass

    def reset_shards(self):
        for f in glob.glob(os.path.join(self.shards_directory_path, "*")):
            try:
                os.remove(f)
            except FileNotFoundError:
                pass

    # =========================================================
    # TOKEN HANDLING
    # =========================================================
    def is_user_logged_in(self):
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                self.token = f.read().strip()
            return bool(self.token)
        except Exception:
            self.token = None
            return False

    def get_token(self):
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                self.token = f.read().strip()
        except Exception:
            self.token = None

    # =========================================================
    # ERASURE CODING
    # =========================================================
    def get_erasure_coding_parameters(self, file_size):
        file_size = file_size / 1024.0  # KB
        shard_size = 8  # KB

        while file_size / shard_size > self.minimum_data_shard:
            shard_size *= 2

        k = self.minimum_data_shard
        m = self.erasure_factor + k

        return k, m

    # =========================================================
    # METADATA
    # =========================================================
    def get_file_metadata(self, file_size):
        segments_count = math.ceil(int(file_size) / self.segment_size)

        segments = []

        for i in range(segments_count):
            segment_size = (
                self.segment_size
                if i < segments_count - 1
                else file_size - self.segment_size * (segments_count - 1)
            )

            k, m = self.get_erasure_coding_parameters(segment_size)

            shard_size = math.ceil(segment_size / k)

            segments.append({
                "k": k,
                "m": m,
                "shard_size": shard_size
            })

        return segments, segments_count

    # =========================================================
    # TRANSFER FILES
    # =========================================================
    def read_transfer_file(self):
        if not os.path.exists(self.transfer_file):
            return None

        try:
            with open(self.transfer_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    def save_transfer_file(self, transfer_dict):
        if not os.path.exists(self.transfer_file):
            raise Exception("Cache file deleted")

        with open(self.transfer_file, "w", encoding="utf-8") as f:
            json.dump(transfer_dict, f)

    def read_download_transfer_file(self):
        if not os.path.exists(self.download_transfer_file):
            return None

        try:
            with open(self.download_transfer_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    def save_download_transfer_file(self, transfer_dict):
        if not os.path.exists(self.download_transfer_file):
            raise Exception("Cache file deleted")

        with open(self.download_transfer_file, "w", encoding="utf-8") as f:
            json.dump(transfer_dict, f)