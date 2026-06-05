import threading
from PyQt5.QtCore import QObject, pyqtSignal
helper = None


def init_progress_bar(helper_obj):
    global helper
    helper = helper_obj


class ProgressBar(object):
    def __init__(self, progress_bar):
        self.file_size = 0
        self._progress_bar = progress_bar
        self._seen_so_far = 0
        self._lock = threading.Lock()
        self.progress_signal_emitter = self.ProgressSignalEmitter()

    def set_size(self, size):
        self.file_size = size // 1024
        self._progress_bar.setRange(0, self.file_size)

    class ProgressSignalEmitter(QObject):
        trigger = pyqtSignal(int)

        def emit_trigger(self, progress_bar, value):
            self.trigger.connect(progress_bar.setValue)
            self.trigger.emit(value)

    def __call__(self, bytes_amount, transfer_type="upload"):
        with self._lock:
            self._seen_so_far += (bytes_amount / 1024)
            if transfer_type == "upload":
                transfer_obj = helper.read_transfer_file()
                if transfer_obj:
                    if transfer_obj['progress'] <= self._seen_so_far:
                        transfer_obj['progress'] = self._seen_so_far
                        helper.save_transfer_file(transfer_obj)
                    else:
                        self._seen_so_far = transfer_obj['progress']
            else:
                transfer_obj = helper.read_download_transfer_file()
                if transfer_obj:
                    if transfer_obj['progress'] <= self._seen_so_far:
                        transfer_obj['progress'] = self._seen_so_far
                        helper.save_download_transfer_file(transfer_obj)
                    else:
                        self._seen_so_far = transfer_obj['progress']

            self.progress_signal_emitter.emit_trigger(self._progress_bar, self._seen_so_far)
