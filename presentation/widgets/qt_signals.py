"""
presentation/widgets/qt_signals.py – Thread-safe Qt signal helpers.

Workers run on background threads; Qt widgets must only be touched on
the main thread. These emitters marshal calls across the boundary.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget


class PageChangeEmitter(QObject):
    _trigger = pyqtSignal(QWidget)
    _text_trigger = pyqtSignal(str)

    def navigate_to(self, stacked_widget, page: QWidget) -> None:
        self._trigger.connect(stacked_widget.setCurrentWidget)
        self._trigger.emit(page)

    def set_text(self, label_widget, text: str) -> None:
        self._text_trigger.connect(label_widget.setText)
        self._text_trigger.emit(text)


class ErrorEmitter(QObject):
    _page_trigger = pyqtSignal(QWidget)
    _title_trigger = pyqtSignal(str)
    _body_trigger = pyqtSignal(str)

    def show_error(self, ui, title: str, body: str, return_page: QWidget | None = None) -> None:
        target = return_page or ui.stackedWidget.currentWidget()

        self._title_trigger.connect(ui.error_title.setText)
        self._title_trigger.emit(str(title))

        self._body_trigger.connect(ui.error_body.setText)
        self._body_trigger.emit(str(body))

        ui.error_source_page = target

        self._page_trigger.connect(ui.stackedWidget.setCurrentWidget)
        self._page_trigger.emit(ui.error_page)
