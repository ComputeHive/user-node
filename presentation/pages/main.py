from __future__ import annotations

from PyQt5 import QtCore, QtWidgets


class MainPage(QtWidgets.QWidget):
    logout_switch = QtCore.pyqtSignal()
    show_my_files_switch = QtCore.pyqtSignal()
    upload_files_switch = QtCore.pyqtSignal()

    def __init__(self, ui) -> None:
        super().__init__()
        self._ui = ui
        ui.main_show_files_pb.clicked.connect(self.show_my_files_switch.emit)
        ui.main_upload_files_pb.clicked.connect(self.upload_files_switch.emit)
        ui.main_logout_pb.clicked.connect(self.logout_switch.emit)
