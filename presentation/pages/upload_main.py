from __future__ import annotations

import os
import time
import webbrowser

from PyQt5 import QtCore, QtWidgets

from config.settings import LOCAL_MODE, MAX_KEY_LENGTH, UPLOAD_POLL_INTERVAL_S
from core.user_state import from_code, UPLOAD_READY, CREATE_CONTRACT, NO_SEEDS
from presentation.controllers.worker import show_error


class UploadMainPage(QtWidgets.QWidget):
    back_to_main_switch = QtCore.pyqtSignal()
    contract_details_switch = QtCore.pyqtSignal(str)
    start_uploading_switch = QtCore.pyqtSignal()

    def __init__(self, ui, container) -> None:
        super().__init__()
        self._ui = ui
        self._container = container
        self._selected_file: str | None = None
        self._key: str | None = None

        ui.upload_main_back_pb.clicked.connect(self.back_to_main_switch.emit)
        ui.upload_main_initiate_contract_pb.clicked.connect(self._on_initiate_contract)
        ui.upload_main_start_uploading_pb.clicked.connect(self.start_uploading_switch.emit)
        ui.upload_main_encryption_key_line_edit.textChanged[str].connect(self._on_key_changed)
        ui.upload_main_request_contract_pb.clicked.connect(self._on_request_contract)
        ui.upload_main_pay_contract_pb.clicked.connect(self._on_request_contract)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_initiate_contract(self) -> None:
        filename, _ = QtWidgets.QFileDialog.getOpenFileName()
        if filename:
            self._selected_file = filename
            self.contract_details_switch.emit(filename)

    def _on_request_contract(self) -> None:
        if LOCAL_MODE:
            self._on_initiate_contract()
        else:
            webbrowser.open_new(self._container.paths._frontend_url if hasattr(self._container.paths, "_frontend_url") else "http://localhost:3000/users")

    def _on_key_changed(self, text: str) -> None:
        self._key = text
        valid = 0 < len(text) <= MAX_KEY_LENGTH
        self._ui.upload_main_start_uploading_pb.setEnabled(valid)

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    def poll_state(self) -> None:
        """Poll user state and update UI controls. Runs on background thread."""
        self._selected_file = None
        token = self._container.token_repo.load() or ""

        while (
            not self._ui.about_to_close
            and self._ui.stackedWidget.currentWidget() == self._ui.upload_main_page
        ):
            try:
                raw_state = self._container.api.get_user_state(token)
            except Exception as exc:
                show_error(self._ui, "Error", str(exc))
                return

            state = from_code(raw_state)
            self._apply_state(state)
            time.sleep(UPLOAD_POLL_INTERVAL_S)

    def start_uploading(self, progress_bar) -> None:
        """Start or resume upload. Runs on background thread."""
        transfer = self._container.upload_transfer_repo.load()
        if not transfer:
            self._ui.stackedWidget.setCurrentWidget(self._ui.main_page)
            return

        file_path = transfer.get("file_path")
        total_size = transfer.get("total_size_to_upload")
        key = self._key or transfer.get("key")

        if not file_path or not total_size or not key:
            self._ui.stackedWidget.setCurrentWidget(self._ui.main_page)
            return

        progress_bar.set_size(total_size)
        try:
            self._container.upload_service.upload_file(file_path, key, progress_bar)
        except Exception as exc:
            show_error(self._ui, "Upload Error", str(exc))

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _apply_state(self, state) -> None:
        ui = self._ui
        key_len = len(ui.upload_main_encryption_key_line_edit.text())
        key_valid = 0 < key_len <= MAX_KEY_LENGTH

        if state is UPLOAD_READY:
            transfer = self._container.upload_transfer_repo.load()
            has_pending = transfer and not transfer.get("start_flag", True)
            ui.upload_main_start_uploading_pb.setText("Resume Uploading" if has_pending else "Start Uploading")
            ui.upload_main_start_uploading_pb.setEnabled(key_valid)
            ui.upload_main_encryption_key_line_edit.setEnabled(True)
            ui.upload_main_initiate_contract_pb.setEnabled(False)
            ui.upload_main_pay_contract_pb.setEnabled(False)

        elif state is CREATE_CONTRACT:
            ui.upload_main_start_uploading_pb.setEnabled(False)
            ui.upload_main_encryption_key_line_edit.setEnabled(False)
            ui.upload_main_initiate_contract_pb.setEnabled(True)
            ui.upload_main_pay_contract_pb.setEnabled(False)

        elif state is NO_SEEDS:
            ui.upload_main_start_uploading_pb.setEnabled(False)
            ui.upload_main_encryption_key_line_edit.setEnabled(False)
            ui.upload_main_initiate_contract_pb.setEnabled(False)
            ui.upload_main_pay_contract_pb.setEnabled(False)

        else:  # UNPAID_CONTRACT
            ui.upload_main_start_uploading_pb.setEnabled(False)
            ui.upload_main_encryption_key_line_edit.setEnabled(False)
            ui.upload_main_initiate_contract_pb.setEnabled(False)
            ui.upload_main_pay_contract_pb.setEnabled(True)

        ui.upload_main_status_label.setText(state.message)
