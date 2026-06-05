import json
import os

from PyQt5.QtCore import QThreadPool, QObject, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget

from PyQt5 import QtWidgets
from gui.ui import Ui_MainWindow

from pages import Main, Login, UploadMain, ContractDetails, ShowFiles, Transition
from utils.app_config import LOCAL_MODE, bootstrap_local_session
from .worker import call_worker
from .progress_bar import ProgressBar


# =========================================================
# SAFE JSON LOADER
# =========================================================
def safe_json_load(path):
    try:
        if not path or not os.path.exists(path):
            return None

        if os.path.getsize(path) == 0:
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except (json.JSONDecodeError, OSError):
        return None


# =========================================================
# PAGE CONTROLLER
# =========================================================
class PageController:

    def __init__(self, helper):
        self.helper = helper

        self.application_window = QtWidgets.QWidget()
        self.application_window.setWindowIcon(QIcon(helper.icon_path))
        self.application_window.setWindowTitle("CERA Client Application")

        self.ui = Ui_MainWindow()
        self.ui.about_to_close = False
        self.ui.setupUi(self.application_window)

        self.ui.thread_pool = QThreadPool()
        self.ui.worker_waiting = False
        self.ui.waiting_spinner.start()

        # -------------------------
        # Initial page selection
        # -------------------------
        if LOCAL_MODE:
            bootstrap_local_session(self.helper)
            self.ui.stackedWidget.setCurrentWidget(self.ui.main_page)
        elif self.helper.is_user_logged_in():
            self.ui.stackedWidget.setCurrentWidget(self.ui.main_page)
        else:
            self.ui.stackedWidget.setCurrentWidget(self.ui.login_page)

        # -------------------------
        # Pages
        # -------------------------
        self.login = Login(self.ui, self.helper)
        self.main = Main(self.ui, self.helper)
        self.upload_main = UploadMain(self.ui, self.helper)
        self.show_files = ShowFiles(self.ui, self.helper)
        self.contract_details = ContractDetails(self.ui, self.helper)
        self.transition = Transition(self.ui, self.helper)

        # -------------------------
        # UI signals
        # -------------------------
        self.ui.error_ok_pb.clicked.connect(self.return_from_error_page)

        self.main.logout_switch.connect(self.switch_to_login)
        self.main.show_my_files_switch.connect(self.switch_show_files)
        self.main.upload_files_switch.connect(self.switch_upload_main)

        self.show_files.back_to_main_switch.connect(self.switch_to_main)
        self.show_files.logout_switch.connect(self.switch_to_login)
        self.show_files.download_switch.connect(lambda: self.switch_start_download("Downloading File.."))

        self.upload_main.back_to_main_switch.connect(self.switch_to_main)
        self.upload_main.contract_details_switch.connect(self.switch_contract_details)
        self.upload_main.start_uploading_switch.connect(lambda: self.switch_start_upload("Uploading file.."))

        self.contract_details.go_to_upload_main_switch.connect(self.switch_upload_main)
        self.contract_details.request_contract_switch.connect(self.switch_create_contract)

        self.transition.okay_switch.connect(self.switch_to_main)

        # -------------------------
        # Resume upload (SAFE)
        # -------------------------
        upload_state = safe_json_load(self.helper.transfer_file)

        if upload_state:
            if (
                not upload_state.get("start_flag")
                and upload_state.get("key")
                and os.path.exists(self.helper.cache_file)
            ):
                self.switch_start_upload("Resume Uploading file..")

        # -------------------------
        # Resume download (SAFE)
        # -------------------------
        download_state = safe_json_load(self.helper.download_transfer_file)

        if download_state:
            if (
                not download_state.get("start_flag")
                and download_state.get("key")
                and os.path.exists(self.helper.cache_file)
            ):
                self.switch_start_download("Resume Downloading file..")

        # -------------------------
        # Show UI
        # -------------------------
        self.application_window.show()

    # =========================================================
    # NAVIGATION
    # =========================================================
    def switch_to_main(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.main_page)

    def switch_to_login(self):
        self.logout()
        self.ui.stackedWidget.setCurrentWidget(self.ui.login_page)

    def switch_upload_main(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.upload_main_page)
        call_worker(self.upload_main.poll_state, self.ui)

    def switch_show_files(self):
        call_worker(
            self.show_files.show_user_files,
            self.ui,
            self.ui.show_files_page,
            "loading Files.."
        )

    def switch_contract_details(self, file_path):
        call_worker(
            lambda: self.contract_details.load_file_details(file_path),
            self.ui,
            self.ui.contract_details_page,
            "loading File details.."
        )

    def switch_start_upload(self, msg):
        self.ui.progress_bar_page_label.setText(msg)
        self.ui.progress_bar_page_progress_bar.setValue(0)
        self.ui.stackedWidget.setCurrentWidget(self.ui.progress_bar_page)

        call_worker(
            lambda: self.upload_main.start_uploading(
                ProgressBar(self.ui.progress_bar_page_progress_bar)
            ),
            self.ui
        )

    def switch_create_contract(self):
        call_worker(
            self.contract_details.request_contract,
            self.ui,
            self.ui.upload_main_page,
            "Creating contract.."
        )

    def switch_start_download(self, msg):
        self.ui.progress_bar_page_label.setText(msg)
        self.ui.progress_bar_page_progress_bar.setValue(0)
        self.ui.stackedWidget.setCurrentWidget(self.ui.progress_bar_page)

        call_worker(
            lambda: self.show_files.download(
                ProgressBar(self.ui.progress_bar_page_progress_bar)
            ),
            self.ui
        )

    # =========================================================
    # AUTH
    # =========================================================
    def logout(self):
        try:
            if os.path.exists(self.helper.cache_file):
                os.remove(self.helper.cache_file)
        except OSError:
            pass

    # =========================================================
    # APP LIFECYCLE
    # =========================================================
    def cleanup(self):
        self.ui.about_to_close = True
        os._exit(0)

    # =========================================================
    # ERROR HANDLING
    # =========================================================
    def return_from_error_page(self):
        self.change_current_page(self.ui.error_source_page)
        self.ui.worker_waiting = False

    def change_current_page(self, target_page):
        class ChangePageSignalEmitter(QObject):
            change_page_trigger = pyqtSignal(QWidget)

            def change_page(self, stacked_widget, target):
                self.change_page_trigger.connect(stacked_widget.setCurrentWidget)
                self.change_page_trigger.emit(target)

        emitter = ChangePageSignalEmitter()
        emitter.change_page(self.ui.stackedWidget, target_page)