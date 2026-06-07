from PyQt5 import QtCore, QtWidgets


class TransitionPage(QtWidgets.QWidget):
    okay_switch = QtCore.pyqtSignal()

    def __init__(self, ui) -> None:
        super().__init__()
        ui.transition_okay_pb.clicked.connect(self.okay_switch.emit)
