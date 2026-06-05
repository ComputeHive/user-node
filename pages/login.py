from PyQt5 import QtWidgets
from controllers.worker import call_worker
from utils import user_login


class Login(QtWidgets.QWidget):

    def __init__(self, ui, helper):
        QtWidgets.QWidget.__init__(self)
        self.ui = ui
        self.helper = helper
        # Connectors
        self.ui.login_pb.clicked.connect(
            lambda: call_worker(self.login, ui, ui.main_page, "Logging in..")
        )

    def login(self):
        username = self.ui.login_username_line_edit.text()
        password = self.ui.login_password_line_edit.text()
        if username == "" or password == "":
            raise Exception("Please fill in username and password.")
        user_login(username, password)
        self.helper.get_token()
