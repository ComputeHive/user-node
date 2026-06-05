from PyQt5 import QtCore, QtWidgets


class Main(QtWidgets.QWidget):
    # Signals
    logout_switch = QtCore.pyqtSignal()
    show_my_files_switch = QtCore.pyqtSignal()
    upload_files_switch = QtCore.pyqtSignal()

    def __init__(self, ui, helper):
        QtWidgets.QWidget.__init__(self)
        self.ui = ui
        self.helper = helper
        # Connectors
        self.ui.main_show_files_pb.clicked.connect(self.show_my_files)
        self.ui.main_upload_files_pb.clicked.connect(self.upload_files)
        self.ui.main_logout_pb.clicked.connect(self.logout)

    def logout(self):
        self.logout_switch.emit()

    def show_my_files(self):
        self.show_my_files_switch.emit()

    def upload_files(self):
        self.upload_files_switch.emit()
