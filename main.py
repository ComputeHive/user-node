"""
main.py – Application entry point.

Constructs the DI container, which wires all services, then hands off
to PageController to build the UI.
"""

import sys
import logging

from PyQt5 import QtWidgets

from application.container import AppContainer
from presentation.controllers.page_controller import PageController

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)

    container = AppContainer()

    # In local mode: ensure a token is present so the app starts on the main page
    from config.settings import LOCAL_MODE, DEV_TOKEN
    if LOCAL_MODE and not container.token_repo.exists():
        container.token_repo.save(DEV_TOKEN)

    controller = PageController(container)
    app.aboutToQuit.connect(controller.cleanup)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
