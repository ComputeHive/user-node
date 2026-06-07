"""
presentation/controllers/page_controller.py – Application navigation hub.

Owns the main window and routes signals from pages to the correct
navigation action. All business logic stays in application services.
"""

from __future__ import annotations

import logging
import os

from PyQt5 import QtWidgets
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QThreadPool

from gui.ui import Ui_MainWindow
from presentation.controllers.worker import run_in_background
from presentation.widgets.progress_bar import ProgressBar
from presentation.widgets.qt_signals import PageChangeEmitter

logger = logging.getLogger(__name__)


class PageController:

    def __init__(self, container) -> None:
        """
        :param container: application.container.AppContainer
        """
        self._container = container
        paths = container.paths

        # ------------------------------------------------------------------
        # Window
        # ------------------------------------------------------------------
        self._window = QtWidgets.QWidget()
        self._window.setWindowIcon(QIcon(paths.icon_path))
        self._window.setWindowTitle("CERA Client Application")

        self._ui = Ui_MainWindow()
        self._ui.about_to_close = False
        self._ui.setupUi(self._window)
        self._ui.thread_pool = QThreadPool()
        self._ui.worker_waiting = False
        self._ui.waiting_spinner.start()

        # ------------------------------------------------------------------
        # Pages
        # ------------------------------------------------------------------
        from presentation.pages.login import LoginPage
        from presentation.pages.main import MainPage
        from presentation.pages.upload_main import UploadMainPage
        from presentation.pages.show_files import ShowFilesPage
        from presentation.pages.contract_details import ContractDetailsPage
        from presentation.pages.transition import TransitionPage

        self._login = LoginPage(self._ui, container)
        self._main = MainPage(self._ui)
        self._upload_main = UploadMainPage(self._ui, container)
        self._show_files = ShowFilesPage(self._ui, container)
        self._contract_details = ContractDetailsPage(self._ui, container)
        self._transition = TransitionPage(self._ui)

        # ------------------------------------------------------------------
        # Initial page
        # ------------------------------------------------------------------
        from config.settings import LOCAL_MODE
        if LOCAL_MODE or container.token_repo.exists():
            self._ui.stackedWidget.setCurrentWidget(self._ui.main_page)
        else:
            self._ui.stackedWidget.setCurrentWidget(self._ui.login_page)

        # ------------------------------------------------------------------
        # Signal wiring
        # ------------------------------------------------------------------
        self._ui.error_ok_pb.clicked.connect(self._on_error_dismissed)

        self._main.logout_switch.connect(self._on_logout)
        self._main.show_my_files_switch.connect(self._on_show_files)
        self._main.upload_files_switch.connect(self._on_upload_main)

        self._show_files.back_to_main_switch.connect(self._on_main)
        self._show_files.logout_switch.connect(self._on_logout)
        self._show_files.download_switch.connect(lambda: self._on_start_download("Downloading File.."))

        self._upload_main.back_to_main_switch.connect(self._on_main)
        self._upload_main.contract_details_switch.connect(self._on_contract_details)
        self._upload_main.start_uploading_switch.connect(lambda: self._on_start_upload("Uploading file.."))

        self._contract_details.go_to_upload_main_switch.connect(self._on_upload_main)
        self._contract_details.request_contract_switch.connect(self._on_create_contract)

        self._transition.okay_switch.connect(self._on_main)

        # ------------------------------------------------------------------
        # Auto-resume interrupted transfers
        # ------------------------------------------------------------------
        self._maybe_resume_upload()
        self._maybe_resume_download()

        self._window.show()

    # ------------------------------------------------------------------
    # Navigation slots
    # ------------------------------------------------------------------

    def _on_main(self) -> None:
        self._ui.stackedWidget.setCurrentWidget(self._ui.main_page)

    def _on_logout(self) -> None:
        self._container.logout()
        self._ui.stackedWidget.setCurrentWidget(self._ui.login_page)

    def _on_upload_main(self) -> None:
        self._ui.stackedWidget.setCurrentWidget(self._ui.upload_main_page)
        run_in_background(self._upload_main.poll_state, self._ui)

    def _on_show_files(self) -> None:
        run_in_background(
            self._show_files.load_files,
            self._ui,
            self._ui.show_files_page,
            "Loading files..",
        )

    def _on_contract_details(self, file_path: str) -> None:
        run_in_background(
            lambda: self._contract_details.load(file_path),
            self._ui,
            self._ui.contract_details_page,
            "Loading file details..",
        )

    def _on_start_upload(self, msg: str) -> None:
        self._ui.progress_bar_page_label.setText(msg)
        self._ui.progress_bar_page_progress_bar.setValue(0)
        self._ui.stackedWidget.setCurrentWidget(self._ui.progress_bar_page)
        progress = ProgressBar(
            self._ui.progress_bar_page_progress_bar,
            transfer_repo=self._container.upload_transfer_repo,
        )
        run_in_background(
            lambda: self._upload_main.start_uploading(progress),
            self._ui,
        )

    def _on_create_contract(self) -> None:
        run_in_background(
            self._contract_details.request_contract,
            self._ui,
            self._ui.upload_main_page,
            "Creating contract..",
        )

    def _on_start_download(self, msg: str) -> None:
        self._ui.progress_bar_page_label.setText(msg)
        self._ui.progress_bar_page_progress_bar.setValue(0)
        self._ui.stackedWidget.setCurrentWidget(self._ui.progress_bar_page)
        progress = ProgressBar(
            self._ui.progress_bar_page_progress_bar,
            transfer_repo=self._container.download_transfer_repo,
            transfer_type="download",
        )
        run_in_background(
            lambda: self._show_files.download(progress),
            self._ui,
        )

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _on_error_dismissed(self) -> None:
        emitter = PageChangeEmitter()
        emitter.navigate_to(self._ui.stackedWidget, self._ui.error_source_page)
        self._ui.worker_waiting = False

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        self._ui.about_to_close = True
        os._exit(0)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _maybe_resume_upload(self) -> None:
        state = self._container.upload_transfer_repo.load()
        if state and not state.get("start_flag") and state.get("key"):
            self._on_start_upload("Resume Uploading file..")

    def _maybe_resume_download(self) -> None:
        state = self._container.download_transfer_repo.load()
        if state and not state.get("start_flag") and state.get("key"):
            self._on_start_download("Resume Downloading file..")
