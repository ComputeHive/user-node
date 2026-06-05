"""
file_transfer_user.py – Shard transfer layer
================================================
send_data / receive_data normally use ZMQ to push/pull shard bytes
over TCP to/from storage nodes.

When BYPASS_UPLOAD_TRANSFER / BYPASS_DOWNLOAD_TRANSFER are True the
same function signatures are preserved but the network is replaced
with local file-copy operations:

  Upload:   shard  →  data/dev_host/<shard_id>
  Download: data/dev_host/<shard_id>  →  data/shards/<shard_id>

After every upload the segment index is (re-)written to
  data/dev_host/<original_filename>.index.json
so start_download (in dev mode) can find the shards later.
"""

import json
import os
from time import sleep
import zmq
import pickle
from .audits import generate_audits
from .cera import shard_done_uploading
from .dev_config import BYPASS_UPLOAD_TRANSFER, BYPASS_DOWNLOAD_TRANSFER
from .local_storage import dev_host_dir, update_shard_in_index

helper = None
semaphore = None


# =========================================================
# MODULE INIT
# =========================================================
def init_file_transfer_user(helper_obj, semaphore_obj):
    global helper, semaphore
    helper = helper_obj
    semaphore = semaphore_obj


# =========================================================
# UPLOAD
# =========================================================
def send_data(request: dict, start: bool, ui, progress_bar):
    """
    Upload a shard to a storage node.

    Dev mode: copies the shard file into data/dev_host/ and updates
    the per-file index so a later dev-mode download can find it.
    The progress bar is advanced in chunks identical to the real path.
    """
    if BYPASS_UPLOAD_TRANSFER:
        _dev_send(request, ui, progress_bar)
        return

    context = zmq.Context()
    client_socket = context.socket(zmq.PAIR)
    client_socket.connect("tcp://" + request["ip"] + ":" + str(request["port"]))
    print("Connected to host", "tcp://" + request["ip"] + ":" + str(request["port"]))

    frame = pickle.loads(client_socket.recv())
    print("Received start frame")

    success = True
    f = open(request["shard_id"], "rb")

    if not start:
        resume_frame = pickle.loads(client_socket.recv())
        f.seek(resume_frame["data"], 0)

    data = f.read(helper.send_chunk_size)
    client_socket.RCVTIMEO = helper.receive_timeout
    print("Start sending data to host")

    while data:
        try:
            client_socket.send(pickle.dumps({"type": "data", "data": data}))
            client_socket.recv()
            data = f.read(helper.send_chunk_size)
            progress_bar(helper.send_chunk_size)
        except Exception:
            print("Connection Lost – trying to reconnect")
            sleep(5)
            try:
                client_socket.close()
                client_socket = context.socket(zmq.PAIR)
                client_socket.connect("tcp://" + request["ip"] + ":" + str(request["port"]))
                client_socket.RCVTIMEO = helper.disconnect_timeout
                pickle.loads(client_socket.recv())
                resume_frame = pickle.loads(client_socket.recv())
                f.seek(resume_frame["data"], 0)
                client_socket.RCVTIMEO = helper.receive_timeout
                data = f.read(helper.send_chunk_size)
                progress_bar(helper.send_chunk_size)
            except Exception:
                print("Unable to reconnect, terminating connection")
                success = False
                break

    if success:
        client_socket.send(pickle.dumps({"type": "END"}))

    f.close()
    client_socket.close()
    _post_upload_bookkeeping(request, ui)


def _dev_send(request: dict, ui, progress_bar):
    """Local copy that stands in for a ZMQ upload."""
    shard_src = request["shard_id"]           # full path inside data/shards/
    shard_name = os.path.basename(shard_src)
    dev_host = dev_host_dir()
    shard_dst = os.path.join(dev_host, shard_name)

    print(f"[DEV] send_data: copying {shard_name} → data/dev_host/")

    shard_size = os.path.getsize(shard_src)
    copied = 0
    with open(shard_src, "rb") as src, open(shard_dst, "wb") as dst:
        while True:
            chunk = src.read(helper.send_chunk_size)
            if not chunk:
                break
            dst.write(chunk)
            copied += len(chunk)
            progress_bar(len(chunk))

    print(f"[DEV] send_data: {shard_name} saved ({shard_size} bytes)")

    # Update the per-file shard index so start_download can find it later
    transfer_obj = helper.read_transfer_file()
    if transfer_obj:
        original_filename = os.path.basename(transfer_obj.get("file_path", "unknown"))
        update_shard_in_index(
            original_filename, request, shard_name, shard_size, transfer_obj
        )
        print(
            f"[DEV] index updated: {original_filename}.index.json  "
            f"(seg={request.get('segment_number')}, shard={request.get('shard_index')})"
        )

    _post_upload_bookkeeping(request, ui)


def _post_upload_bookkeeping(request: dict, ui):
    """
    Common post-upload steps shared by the real and dev paths:
    generate audits, mark the shard done, notify the server (or
    dev no-op), and remove the connection from the connections file.
    """
    semaphore.acquire()
    try:
        audits = generate_audits(request["shard_id"])
        print(f"[upload] audits generated for shard {request['shard_index']} "
              f"of segment {request['segment_number']}")

        transfer_obj = helper.read_transfer_file()
        if transfer_obj:
            seg  = request["segment_number"]
            shard = request["shard_index"]
            transfer_obj["segments"][seg]["shards"][shard]["done_uploading"] = True
            helper.save_transfer_file(transfer_obj)

        shard_done_uploading(request["shard_id"], audits, ui)

        # Remove from connections file
        conn_path = helper.upload_connection_file
        if os.path.exists(conn_path) and os.path.getsize(conn_path) > 0:
            try:
                with open(conn_path, "r", encoding="utf-8") as jf:
                    connections = json.load(jf)
                if request in connections.get("connections", []):
                    connections["connections"].remove(request)
                with open(conn_path, "w", encoding="utf-8") as jf:
                    json.dump(connections, jf)
            except (json.JSONDecodeError, ValueError):
                pass
    finally:
        semaphore.release()

    print("[upload] shard done")


# =========================================================
# DOWNLOAD
# =========================================================
def receive_data(request: dict, progress_bar):
    """
    Download a shard from a storage node.

    Dev mode: copies the shard from data/dev_host/ into data/shards/.
    """
    if BYPASS_DOWNLOAD_TRANSFER:
        _dev_receive(request, progress_bar)
        return

    # ---- production ZMQ path ----
    import zmq
    import pickle

    context = zmq.Context()
    client_socket = context.socket(zmq.PAIR)
    client_socket.connect("tcp://" + request["ip"] + ":" + str(request["port"]))
    print("Connected to host", "tcp://" + request["ip"] + ":" + str(request["port"]))

    pickle.loads(client_socket.recv())
    print("received start frame")

    shard_path = os.path.join(helper.shards_directory_path, request["shard_id"])

    if os.path.isfile(shard_path):
        file_size = os.path.getsize(shard_path)
        client_socket.send(pickle.dumps({"type": "resume", "data": file_size}))
        f = open(shard_path, "ab")
    else:
        f = open(shard_path, "wb")

    client_socket.RCVTIMEO = helper.receive_timeout
    while True:
        try:
            frame = pickle.loads(client_socket.recv())
            if frame["type"] == "data":
                f.write(frame["data"])
                progress_bar(helper.send_chunk_size, "download")
                client_socket.send(pickle.dumps({"type": "ACK"}))
            elif frame["type"] == "END":
                f.close()
                break
        except Exception:
            print("Disconnected – reconnecting")
            sleep(5)
            client_socket.close()
            client_socket = context.socket(zmq.PAIR)
            client_socket.connect("tcp://" + request["ip"] + ":" + str(request["port"]))
            client_socket.RCVTIMEO = helper.disconnect_timeout
            pickle.loads(client_socket.recv())
            f.close()
            file_size = os.path.getsize(shard_path)
            client_socket.send(pickle.dumps({"type": "resume", "data": file_size}))
            f = open(shard_path, "ab")
            client_socket.RCVTIMEO = helper.receive_timeout

    client_socket.close()
    _remove_connection(request)


def _dev_receive(request: dict, progress_bar):
    """Local copy that stands in for a ZMQ download."""
    shard_name = request["shard_id"]
    dev_host   = dev_host_dir()
    shard_src  = os.path.join(dev_host, shard_name)
    shard_dst  = os.path.join(helper.shards_directory_path, shard_name)

    if not os.path.exists(shard_src):
        raise FileNotFoundError(
            f"[DEV] receive_data: shard '{shard_name}' not found in data/dev_host/.\n"
            "Make sure you uploaded this file in dev mode first."
        )

    print(f"[DEV] receive_data: copying {shard_name} ← data/dev_host/")
    shard_size = os.path.getsize(shard_src)

    with open(shard_src, "rb") as src, open(shard_dst, "wb") as dst:
        while True:
            chunk = src.read(helper.send_chunk_size)
            if not chunk:
                break
            dst.write(chunk)
            progress_bar(len(chunk), "download")

    print(f"[DEV] receive_data: {shard_name} received ({shard_size} bytes)")
    _remove_connection(request)


# =========================================================
# CONNECTION TRACKING
# =========================================================
def check_old_connections(ui, progress_bar):
    """Resume any incomplete upload/download connections."""
    print("Checking old connections")
    conn_path = helper.upload_connection_file
    if not os.path.exists(conn_path) or os.path.getsize(conn_path) == 0:
        print("No pending connections.")
        return
    try:
        with open(conn_path, "r", encoding="utf-8") as jf:
            connections = json.load(jf)
    except (json.JSONDecodeError, OSError):
        print("Could not read connections file.")
        return

    for req in list(connections.get("connections", [])):
        req = dict(req)
        print("Reconnecting to", req.get("ip"), req.get("port"))
        if req.get("type") == "upload":
            send_data(req, False, ui, progress_bar)
        elif req.get("type") == "download":
            receive_data(req, progress_bar)


def add_connection(request: dict):
    """Append a new connection to the connections tracking file."""
    conn_path = helper.upload_connection_file
    try:
        if os.path.exists(conn_path) and os.path.getsize(conn_path) > 0:
            with open(conn_path, "r", encoding="utf-8") as jf:
                connections = json.load(jf)
        else:
            connections = {"connections": []}
        connections["connections"].append(request)
        with open(conn_path, "w", encoding="utf-8") as jf:
            json.dump(connections, jf)
    except (json.JSONDecodeError, OSError) as e:
        print(f"add_connection error: {e}")


def _remove_connection(request: dict):
    """Remove a completed connection from the tracking file."""
    conn_path = helper.upload_connection_file
    if not os.path.exists(conn_path) or os.path.getsize(conn_path) == 0:
        return
    try:
        with open(conn_path, "r", encoding="utf-8") as jf:
            connections = json.load(jf)
        if request in connections.get("connections", []):
            connections["connections"].remove(request)
        with open(conn_path, "w", encoding="utf-8") as jf:
            json.dump(connections, jf)
    except (json.JSONDecodeError, ValueError, OSError):
        pass
