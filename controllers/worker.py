from PyQt5.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget
import time
import os
from utils import Helper
helper = Helper()


class Worker(QRunnable):
    def __init__(self, fn, target_page=None, ui=None, text='', *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.target_page = target_page
        self.text = text
        self.ui = ui
        if self.loading_screen_selected():
            self.current_page = ui.stackedWidget.currentWidget()
            self.change_page_signal_emitter = self.ChangePageSignalEmitter()

    def loading_screen_selected(self):
        return self.target_page is not None and self.ui is not None and self.text != ''

    class ChangePageSignalEmitter(QObject):
        change_page_trigger = pyqtSignal(QWidget)
        change_waiting_text_trigger = pyqtSignal(str)

        def change_page(self, stacked_widget, target):
            self.change_page_trigger.connect(stacked_widget.setCurrentWidget)
            self.change_page_trigger.emit(target)

        def change_waiting_text(self, loading_text, text):
            self.change_waiting_text_trigger.connect(loading_text.setText)
            self.change_waiting_text_trigger.emit(text)

    @pyqtSlot()
    def run(self):
        # try:
        if self.loading_screen_selected():
            self.change_page_signal_emitter.change_waiting_text(self.ui.loading_text, self.text)
            self.change_page_signal_emitter.change_page(self.ui.stackedWidget, self.ui.loading_page)

        output = self.fn(*self.args, **self.kwargs)

        if self.loading_screen_selected():
            if output == 'failure':
                self.change_page_signal_emitter.change_page(self.ui.stackedWidget, self.current_page)
            else:
                self.change_page_signal_emitter.change_page(self.ui.stackedWidget, self.target_page)

#         except Exception as e:
#             worker_error_page("Error", str(e), self.ui)
#             if self.loading_screen_selected():
#                 self.change_page_signal_emitter.change_page(self.ui.stackedWidget, self.current_page)


def worker_error_page(title, body, ui, target=None):
    title = str(title)
    body = str(body)
    if target:
        ui.error_source_page = target
        try:
            # Remove cached file
            os.remove(helper.cache_file)
        except:
            print("No cache file")
    else:
        ui.error_source_page = ui.stackedWidget.currentWidget()
    ui.worker_waiting = True

    class ErrorSignalEmitter(QObject):
        change_page_trigger = pyqtSignal(QWidget)
        change_title_trigger = pyqtSignal(str)
        change_body_trigger = pyqtSignal(str)
        adjust_title = pyqtSignal()
        adjust_body = pyqtSignal()

        def display_error(self):
            self.change_page_trigger.connect(ui.stackedWidget.setCurrentWidget)
            self.change_page_trigger.emit(ui.error_page)
            self.change_title_trigger.connect(ui.error_title.setText)
            self.change_title_trigger.emit(title)
            self.change_body_trigger.connect(ui.error_body.setText)
            self.change_body_trigger.emit(body)
            self.adjust_title.connect(ui.error_title.adjustSize)
            self.adjust_title.emit()
            self.adjust_body.connect(ui.error_body.adjustSize)
            self.adjust_body.emit()
            print(body)

    change_page_signal_emitter = ErrorSignalEmitter()
    change_page_signal_emitter.display_error()
    # to prevent from returning to previous page in waiting screens.
    while ui.worker_waiting:
        time.sleep(0.1)
    time.sleep(0.1)


def call_worker(fn, ui=None, target_page=None, text=''):
    """takes a function and runs it in another thread, and shows loading screen with the specified text.
     upon success it proceeds to the target page. If it failed, it returns to the previous page"""

    worker = Worker(fn, target_page, ui, text)
    ui.thread_pool.start(worker)
