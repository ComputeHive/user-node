from __future__ import annotations

import json
import logging

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt

from config.settings import MAX_KEY_LENGTH
from presentation.controllers.worker import show_error

logger = logging.getLogger(__name__)

_UNITS = ["B", "KB", "MB", "GB"]
_KB = 1024


def _format_size(size_bytes: int) -> str:
    idx = 0
    value = float(size_bytes)
    while value / _KB >= 1 and idx < 3:
        value /= _KB
        idx += 1
    return f"{value:.3f} {_UNITS[idx]}"


class ShowFilesPage(QtWidgets.QWidget):
    back_to_main_switch = QtCore.pyqtSignal()
    logout_switch = QtCore.pyqtSignal()
    download_switch = QtCore.pyqtSignal()

    def __init__(self, ui, container) -> None:
        super().__init__()
        self._ui = ui
        self._container = container
        self._files: list[dict] = []
        self._selected_index: int | None = None
        self._key: str | None = None

        ui.show_files_back_pb.clicked.connect(self._on_back)
        ui.show_files_decryption_key_line_edit.textChanged[str].connect(self._on_key_changed)
        ui.show_files_download_pb.clicked.connect(self.download_switch.emit)
        ui.show_files_list_widget.clicked.connect(self._on_item_selected)

    def _on_back(self) -> None:
        self._selected_index = None
        self._key = None
        self._ui.show_files_decryption_key_line_edit.setText("")
        self.back_to_main_switch.emit()

    def _on_key_changed(self, text: str) -> None:
        self._key = text
        self._update_download_button()

    def _on_item_selected(self) -> None:
        row = self._ui.show_files_list_widget.currentRow()
        self._selected_index = row - 1  # row 0 is the header
        self._update_download_button()

    def _update_download_button(self) -> None:
        key_valid = bool(self._key) and len(self._key) <= MAX_KEY_LENGTH
        file_selected = self._selected_index is not None and self._selected_index >= 0
        self._ui.show_files_download_pb.setEnabled(key_valid and file_selected)

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    def load_files(self) -> None:
        token = self._container.token_repo.load() or ""
        try:
            files = self._container.api.get_user_files(token)
        except Exception as exc:
            show_error(self._ui, "Error", str(exc))
            return

        self._files = files or []
        list_widget = self._ui.show_files_list_widget
        list_widget.clear()

        if not self._files:
            self._ui.show_files_download_pb.setEnabled(False)
            self._ui.show_files_decryption_key_line_edit.setEnabled(False)
            QtWidgets.QListWidgetItem("No files stored", list_widget).setFlags(Qt.NoItemFlags)
            return

        self._ui.show_files_decryption_key_line_edit.setEnabled(True)
        QtWidgets.QListWidgetItem("File Name, Size, Download Count", list_widget).setFlags(Qt.NoItemFlags)

        for f in self._files:
            label = f"{f['filename']}, {_format_size(f['size'])}, {f['download_count']}"
            QtWidgets.QListWidgetItem(label, list_widget)

    def download(self, progress_bar) -> None:
        transfer = self._container.download_transfer_repo.load()

        if not transfer:
            if self._selected_index is None or not self._files:
                return
            selected = self._files[self._selected_index]
            filename = selected["filename"]
            progress_bar.set_size(selected["size"])
            state = {
                "filename": filename,
                "key": self._key,
                "shards_renamed": False,
                "type": "download",
                "progress": 0,
                "total_size_to_download": selected["size"],
                "start_flag": True,
            }
            self._container.download_transfer_repo.save(state)
        else:
            filename = transfer["filename"]
            progress_bar.set_size(transfer["total_size_to_download"])
            progress_bar(transfer["progress"], "download")

        key = self._key or (transfer or {}).get("key")
        try:
            self._container.download_service.download_file(filename, key, progress_bar)
        except Exception as exc:
            show_error(self._ui, "Download Error", str(exc))
