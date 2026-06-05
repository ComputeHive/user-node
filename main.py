import threading
from PyQt5 import QtWidgets
import sys
from controllers import PageController, init_progress_bar
from utils import Helper, init_cera, init_file_transfer_user, init_file_handler
from utils.app_config import LOCAL_MODE, bootstrap_local_session


def main():
    app = QtWidgets.QApplication(sys.argv)
    helper = Helper()
    semaphore = threading.Semaphore()
    init_cera(helper)
    init_file_transfer_user(helper, semaphore)
    init_file_handler(helper)
    if LOCAL_MODE:
        bootstrap_local_session(helper)
    init_progress_bar(helper)
    page_controller = PageController(helper)
    app.aboutToQuit.connect(page_controller.cleanup)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
