"""
presentation/widgets/progress_bar.py – Thread-safe progress bar wrapper.

Receives byte counts and forwards them to the Qt progress widget via
signals, persisting progress to the transfer repository for resumption.
"""

from __future__ import annotations

import threading

from PyQt5.QtCore import QObject, pyqtSignal


class _ProgressSignal(QObject):
    trigger = pyqtSignal(int)

    def emit_value(self, progress_bar_widget, value: int) -> None:
        self.trigger.connect(progress_bar_widget.setValue)
        self.trigger.emit(value)


class ProgressBar:
    """
    Call instance with byte count to advance the bar.

    Usage::

        bar = ProgressBar(qt_progress_bar_widget, upload_transfer_repo)
        bar.set_size(file_size_bytes)
        bar(chunk_bytes)           # upload
        bar(chunk_bytes, "download")
    """

    def __init__(self, qt_widget, transfer_repo=None, transfer_type: str = "upload") -> None:
        self._widget = qt_widget
        self._repo = transfer_repo          # TransferRepository | None
        self._default_type = transfer_type
        self._seen_kb: float = 0.0
        self._lock = threading.Lock()
        self._signal = _ProgressSignal()

    def set_size(self, size_bytes: int) -> None:
        size_kb = size_bytes // 1024
        self._widget.setRange(0, size_kb)

    def __call__(self, bytes_amount: int, transfer_type: str | None = None) -> None:
        kind = transfer_type or self._default_type
        with self._lock:
            self._seen_kb += bytes_amount / 1024

            if self._repo:
                state = self._repo.load()
                if state:
                    if state["progress"] <= self._seen_kb:
                        state["progress"] = self._seen_kb
                        self._repo.save(state)
                    else:
                        self._seen_kb = state["progress"]

            self._signal.emit_value(self._widget, int(self._seen_kb))
