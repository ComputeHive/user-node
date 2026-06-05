from PyQt5 import QtCore, QtWidgets


class Transition(QtWidgets.QWidget):
    # Signals
    okay_switch = QtCore.pyqtSignal()

    def __init__(self, ui, helper):
        QtWidgets.QWidget.__init__(self)
        self.ui = ui
        self.helper = helper
        # Connectors
        self.ui.transition_okay_pb.clicked.connect(self.okay_pressed)

    def okay_pressed(self):
        self.okay_switch.emit()
