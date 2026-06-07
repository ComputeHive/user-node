from __future__ import annotations

from PyQt5 import QtWidgets

from presentation.controllers.worker import run_in_background


class LoginPage(QtWidgets.QWidget):

    def __init__(self, ui, container) -> None:
        super().__init__()
        self._ui = ui
        self._container = container

        ui.login_pb.clicked.connect(
            lambda: run_in_background(self._login, ui, ui.main_page, "Logging in..")
        )

    def _login(self) -> None:
        username = self._ui.login_username_line_edit.text().strip()
        password = self._ui.login_password_line_edit.text()
        if not username or not password:
            raise ValueError("Please fill in username and password.")
        self._container.login(username, password)
