from PyQt5 import QtCore, QtWidgets
from utils import create_file, get_price
import os
import json


class ContractDetails(QtWidgets.QWidget):

    go_to_upload_main_switch = QtCore.pyqtSignal()
    request_contract_switch = QtCore.pyqtSignal()

    def __init__(self, ui, helper):
        QtWidgets.QWidget.__init__(self)
        self.ui = ui
        self.helper = helper
        self.contract_details = {}
        self.file_path = None
        # Connectors
        self.ui.contract_details_cancel_pb.clicked.connect(self.cancel_contract_details)
        self.ui.contract_details_request_pb.clicked.connect(self.request_contract_switch.emit)
        self.ui.contract_details_download_counts_spin_box.valueChanged.connect(self.calculate_price)
        self.ui.contract_details_months_spin_box.valueChanged.connect(self.calculate_price)

    def cancel_contract_details(self):
        self.go_to_upload_main_switch.emit()

    def load_file_details(self, file_path):
        self.contract_details['file_size'] = os.stat(file_path).st_size
        self.file_path = file_path
        unit = ["B", "KB", "MB", "GB"]
        index = 0
        file_size = self.contract_details['file_size']
        while int(file_size/self.helper.kilobyte) > 0 and index < 3:
            index += 1
            file_size = file_size/self.helper.kilobyte
        self.ui.contract_details_file_size_label.setText("File Size: " + "{:.3f}".format(file_size) + " " + unit[index])
        self.calculate_price()

    def calculate_price(self):
        self.contract_details['download_count'] = self.ui.contract_details_download_counts_spin_box.value()
        self.contract_details['duration_in_months'] = self.ui.contract_details_months_spin_box.value()
        price = get_price(self.contract_details, self.ui)
        self.ui.contract_details_price_label.setText("Price:" + str(float(price/1000000000000000000)) + " ETH")

    def request_contract(self):
        self.contract_details['download_count'] = self.ui.contract_details_download_counts_spin_box.value()
        self.contract_details['duration_in_months'] = self.ui.contract_details_months_spin_box.value()
        self.contract_details['filename'] = os.path.basename(self.file_path)
        self.contract_details['segments'], self.contract_details['segments_count'] = \
            self.helper.get_file_metadata(self.contract_details['file_size'])
        # If file is created successfully go to upload main page
        if create_file(self.contract_details, self.ui):
            self.go_to_upload_main_switch.emit()
            self.save_file_to_upload_info()

    def save_file_to_upload_info(self):
        total_size = 0
        for segment in self.contract_details['segments']:
            total_size += segment['shard_size'] * segment['m']
        request_info = {'file_path': self.file_path, 'start_flag': True, 'type': 'upload',
                        'progress': 0, 'total_size_to_upload': total_size, 'key': None}
        with open(self.helper.transfer_file, "w", encoding="utf-8") as outfile:
            json.dump(request_info, outfile)
