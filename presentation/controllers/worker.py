"""
presentation/controllers/worker.py – Background task runner.

Runs a callable on Qt's thread pool, optionally showing a loading
screen before and navigating to a target page after.

Key improvement over original: no Helper instantiation; error display
goes through the injected ErrorEmitter so it's testable.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from PyQt5.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget

from presentation.widgets.qt_signals import PageChangeEmitter, ErrorEmitter

logger = logging.getLogger(__name__)


class Worker(QRunnable):
    """Run *fn* on a background thread with an optional loading screen."""

    def __init__(
        self,
        fn: Callable,
        ui=None,
        target_page: QWidget | None = None,
        loading_text: str = "",
    ) -> None:
        super().__init__()
        self.fn = fn
        self.ui = ui
        self.target_page = target_page
        self.loading_text = loading_text

        self._show_loading = bool(target_page and ui and loading_text)
        if self._show_loading:
            self._return_page = ui.stackedWidget.currentWidget()
            self._navigator = PageChangeEmitter()

    @pyqtSlot()
    def run(self) -> None:
        if self._show_loading:
            self._navigator.set_text(self.ui.loading_text, self.loading_text)
            self._navigator.navigate_to(self.ui.stackedWidget, self.ui.loading_page)

        try:
            result = self.fn()
        except Exception as exc:
            logger.exception("Worker task failed: %s", exc)
            _show_error(self.ui, "Error", str(exc))
            if self._show_loading:
                self._navigator.navigate_to(self.ui.stackedWidget, self._return_page)
            return

        if self._show_loading:
            page = self._return_page if result == "failure" else self.target_page
            self._navigator.navigate_to(self.ui.stackedWidget, page)


def run_in_background(fn: Callable, ui, target_page: QWidget | None = None, loading_text: str = "") -> None:
    """Convenience wrapper: submit *fn* to the UI's thread pool."""
    worker = Worker(fn, ui, target_page, loading_text)
    ui.thread_pool.start(worker)


def _show_error(ui, title: str, body: str, return_page: QWidget | None = None) -> None:
    """Thread-safe error display. Blocks until the user dismisses the error."""
    ui.worker_waiting = True
    emitter = ErrorEmitter()
    emitter.show_error(ui, title, body, return_page)
    while ui.worker_waiting:
        time.sleep(0.1)
    time.sleep(0.1)


# Public alias used by page code that needs to show errors from background threads
show_error = _show_error
