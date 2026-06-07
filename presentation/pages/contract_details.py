from __future__ import annotations

import json
import logging
import os

from PyQt5 import QtCore, QtWidgets

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


class ContractDetailsPage(QtWidgets.QWidget):
    go_to_upload_main_switch = QtCore.pyqtSignal()
    request_contract_switch = QtCore.pyqtSignal()

    def __init__(self, ui, container) -> None:
        super().__init__()
        self._ui = ui
        self._container = container
        self._file_path: str | None = None
        self._file_size: int = 0

        ui.contract_details_cancel_pb.clicked.connect(self.go_to_upload_main_switch.emit)
        ui.contract_details_request_pb.clicked.connect(self.request_contract_switch.emit)
        ui.contract_details_download_counts_spin_box.valueChanged.connect(self._calculate_price)
        ui.contract_details_months_spin_box.valueChanged.connect(self._calculate_price)

    def load(self, file_path: str) -> None:
        self._file_path = file_path
        self._file_size = os.stat(file_path).st_size
        self._ui.contract_details_file_size_label.setText(f"File Size: {_format_size(self._file_size)}")
        self._calculate_price()

    def _calculate_price(self) -> None:
        token = self._container.token_repo.load() or ""
        try:
            price_wei = self._container.api.get_price(
                token=token,
                download_count=self._ui.contract_details_download_counts_spin_box.value(),
                duration_months=self._ui.contract_details_months_spin_box.value(),
                file_size=self._file_size,
            )
        except Exception as exc:
            show_error(self._ui, "Error", str(exc))
            return
        eth = price_wei / 1_000_000_000_000_000_000
        self._ui.contract_details_price_label.setText(f"Price: {eth} ETH")

    def request_contract(self) -> None:
        if not self._file_path:
            return

        from core.erasure_params import compute_file_segments
        segments = compute_file_segments(self._file_size)

        contract = {
            "filename": os.path.basename(self._file_path),
            "file_size": self._file_size,
            "download_count": self._ui.contract_details_download_counts_spin_box.value(),
            "duration_in_months": self._ui.contract_details_months_spin_box.value(),
            "segments": [{"k": s.k, "m": s.m, "shard_size": s.shard_size} for s in segments],
            "segments_count": len(segments),
        }

        token = self._container.token_repo.load() or ""
        try:
            self._container.api.create_file(token, contract)
        except Exception as exc:
            show_error(self._ui, "Error", str(exc))
            return

        self._save_upload_info(contract, segments)
        self.go_to_upload_main_switch.emit()

    def _save_upload_info(self, contract: dict, segments) -> None:
        total_size = sum(s.shard_size * s.m for s in segments)
        state = {
            "file_path": self._file_path,
            "start_flag": True,
            "type": "upload",
            "progress": 0,
            "total_size_to_upload": total_size,
            "key": None,
        }
        self._container.upload_transfer_repo.save(state)
