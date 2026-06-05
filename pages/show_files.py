import json
import os

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QListWidgetItem
from utils import get_user_files, download_shards_and_retrieve


class ShowFiles(QtWidgets.QWidget):
    # Signals
    back_to_main_switch = QtCore.pyqtSignal()
    logout_switch = QtCore.pyqtSignal()
    download_switch = QtCore.pyqtSignal()

    def __init__(self, ui, helper):
        QtWidgets.QWidget.__init__(self)
        self.ui = ui
        self.helper = helper
        self.index = None
        self.files = None
        self.key = None

        # Connectors
        self.ui.show_files_back_pb.clicked.connect(self.back_to_main)
        self.ui.show_files_decryption_key_line_edit.textChanged[str].connect(self.check_download_conditions)
        self.ui.show_files_download_pb.clicked.connect(self.download_switch.emit)
        self.ui.show_files_list_widget.clicked.connect(self.item_selected)

    def back_to_main(self):
        self.index = None
        self.key = None
        self.ui.show_files_decryption_key_line_edit.setText(None)
        self.back_to_main_switch.emit()

    def show_user_files(self):
        self.index = None
        response = get_user_files(self.ui)
        self.files = response
        list_widget = self.ui.show_files_list_widget
        list_widget.clear()
        if not self.files:
            self.ui.show_files_download_pb.setEnabled(False)
            self.ui.show_files_decryption_key_line_edit.setEnabled(False)
            QListWidgetItem("No Files stored", list_widget).setFlags(Qt.NoItemFlags)
            return
        self.ui.show_files_decryption_key_line_edit.setEnabled(True)
        QListWidgetItem("File Name" + ', ' + "Size" + ', ' + "Download Count", list_widget)\
            .setFlags(Qt.NoItemFlags)
        for file in self.files:
            unit = ["B", "KB", "MB", "GB"]
            index = 0
            file_size = file['size']
            while int(file_size / self.helper.kilobyte) > 0 and index < 3:
                index += 1
                file_size = int(file_size) / self.helper.kilobyte
            QListWidgetItem(file["filename"] + ', ' + "{:.3f}".format(file_size) + " " + unit[index] +
                            ', ' + str(file['download_count']), list_widget)

    def check_download_conditions(self):
        self.key = self.ui.show_files_decryption_key_line_edit.text()
        if (len(self.key) > 32) or (len(self.key) <= 0):
            self.ui.show_files_download_pb.setEnabled(False)
        else:
            if self.index or self.index == 0:
                self.ui.show_files_download_pb.setEnabled(True)

    def item_selected(self):
        self.index = self.ui.show_files_list_widget.currentRow() - 1
        self.check_download_conditions()

    def download(self, progress_bar):
        # print("Downloading", self.index, self.files[self.index]['filename'])
        transfer_obj = self.helper.read_download_transfer_file()
        # if transfer object doesn't exit therefore the download is just started
        if not transfer_obj:
            if self.files[self.index]['filename']:
                # set progress bar range to the size of the file to be downloaded
                progress_bar.set_size(self.files[self.index]['size'])
                # save needed information to resume download if connection lost.
                transfer_obj = {
                    'filename': self.files[self.index]['filename'], 'key': self.key, "shards_renamed": False,
                    'type': 'download', 'progress': 0, 'total_size_to_download': self.files[self.index]['size'],
                    "start_flag": True
                }
                with open(self.helper.download_transfer_file, 'w') as outfile:
                    json.dump(transfer_obj, outfile)
                download_shards_and_retrieve(self.files[self.index]['filename'], self.key, self.ui, progress_bar)
        # if transfer object exits therefore there is a download needs to be resumed.
        else:
            # set progress bar range to the size of the file to be downloaded
            progress_bar.set_size(transfer_obj['total_size_to_download'])
            # set current progress to the progress bar.
            print("Old Progress", transfer_obj['progress'],
                  int(transfer_obj['progress']/ transfer_obj['total_size_to_download']))
            progress_bar(transfer_obj['progress'], "download")
            # resume download
            download_shards_and_retrieve(transfer_obj['filename'], transfer_obj['key'], self.ui, progress_bar)
