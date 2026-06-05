import os
import sys
import time
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget
from .erasure_coding import encode, decode
from .encryption import encrypt, decrypt
from .cera import get_pending_file_info, start_download, file_done_uploading
from .file_transfer_user import send_data, add_connection, check_old_connections, receive_data

helper = None


def init_file_handler(helper_obj):
    global helper
    helper = helper_obj


def process_segment(from_file, key, segment_number, transfer_obj, ui, progress_bar):
    """
    This function takes a segment then start to process it if it's not already processed, and start uploading shard
    by shard
    :param ui: ui object.
    :param progress_bar: progress bar to show the percentage of upload
    :param from_file: segment file that will be processed
    :param key: encryption key used to encrypt segment
    :param segment_number: segment number in a file
    :param transfer_obj: transfer object that holds information about transaction.
    """
    # If the segment is not processed, process it
    if not transfer_obj['segments'][segment_number]['processed']:
        print("Segment#", segment_number, "--------Processing----------")
        # Process#1:    Encryption
        try:
            filename = os.path.basename(from_file)
            file_size = os.stat(from_file).st_size
            encrypted_file_path = helper.get_encryption_file_path(filename)
            encrypt(from_file, encrypted_file_path, key)
            print("Segment Encrypted")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            function_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print("Error in Encryption", exc_type, function_name, exc_tb.tb_lineno)
            return
        # Process#2:    Erasure coding
        try:
            # file_size = os.stat(encrypted_file_path).st_size
            input_file = open(encrypted_file_path, 'rb')
            # file_obj = input_file.read()
            # encode(file_obj, file_size, helper.shards_directory_path, segment_number,
            #        transfer_obj['segments'][segment_number]['k'], transfer_obj['segments'][segment_number]['m'])
            encode(encrypted_file_path, helper.shards_directory_path, segment_number,
                   transfer_obj['segments'][segment_number]['k'], transfer_obj['segments'][segment_number]['m'])
            input_file.close()
            print("Segment Erasure coded")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            function_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print("Error in Erasure coding", exc_type, function_name, exc_tb.tb_lineno)
            return
        # Process#3:    Rename Shards to their new ids
        try:
            shards = sorted(os.listdir(helper.shards_directory_path))
            shards_new = transfer_obj['segments'][segment_number]['shards']
            for shard_index, shard_name in enumerate(shards):
                os.rename(os.path.join(helper.shards_directory_path, shard_name),
                          os.path.join(helper.shards_directory_path, shards_new[shard_index]["shard_id"]))
            print("Shards Renamed")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            function_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print("Error in renaming shards", exc_type, function_name, exc_tb.tb_lineno)
            return

        # Segment is processed save it's new state
        transfer_obj['segments'][segment_number]['processed'] = True
        helper.save_transfer_file(transfer_obj)
    # If the segment is already processed, Nothing to do just a debugging statement
    else:
        print("Segment#", segment_number, "--------Already Processed Resume uploading----------")

    # Upload Shards: Add connections and upload
    for shard_index, shard in enumerate(transfer_obj['segments'][segment_number]['shards']):
        # If shard is not uploaded
        if not shard['done_uploading']:
            print("Segment#", segment_number, "Shard#", shard_index, "--------Start Uploading.----------")
            # Prepare upload information dictionary
            req = {'type': 'upload',
                   'port': shard['port'],
                   'shard_id': os.path.join(helper.shards_directory_path, shard['shard_id']),
                   'auth': shard['shared_authentication_key'],
                   'ip': shard['ip_address'],
                   "segment_number": segment_number,
                   "shard_index": shard_index,
                   "shard_size": transfer_obj['segments'][segment_number]['shard_size']
                   }
            # Add connection
            add_connection(req)

            # Send data to storage node
            send_data(req, True, ui, progress_bar)

            # Save new state of the shard
            # transfer_obj['segments'][segment_number]['shards'][shard_index]['done_uploading'] = True
            # save_transfer_file(transfer_obj)
            print("Segment#", segment_number, "Shard#", shard_index, "--------Done Uploading.----------")

        else:
            print("Segment#", segment_number, "Shard#", shard_index, "--------Already Uploaded(Skipped)----------")

    # Reset
    helper.reset_shards()


def process_file(from_file, key, ui, progress_bar, chunk_size=None):
    """
    This function divides the file into segments to process each segment separately
    :param progress_bar: progress bar to show the percentage of upload
    :param from_file: input file that will be uploaded
    :param key: encryption key
    :param chunk_size: segment size
    :param ui: ui object
    """
    if chunk_size is None:
        chunk_size = helper.segment_size
    # try:
    start = time.time()
    print("process file function")
    # Get needed data to start processing and uploading.
    transfer_obj = helper.read_transfer_file()
    response = get_pending_file_info(ui)
    file_size = os.stat(from_file).st_size
    file_size_cera, segments_metadata = response['file_size'], response['segments']

    # set progress of progress bar
    progress_bar(transfer_obj['progress'])

    # First time to upload.
    if transfer_obj['start_flag']:
        print("First Upload")
        helper.reset_shards()
        helper.reset_directories()
        transfer_obj['segments'] = segments_metadata
        # Add segment state
        for segment_index, segment in enumerate(segments_metadata):
            transfer_obj['segments'][segment_index]['done_uploading'] = False
            transfer_obj['segments'][segment_index]['processed'] = False
        transfer_obj['key'] = key
        transfer_obj['start_flag'] = False
        helper.save_transfer_file(transfer_obj)
    else:   # Retry uploading on pending connections
        print("Resume Upload")
        if not key:
            if transfer_obj['key']:
                key = transfer_obj['key']
            else:
                return
        else:
            transfer_obj['key'] = key
            helper.save_transfer_file(transfer_obj)
        print("Key:", key)
        check_old_connections(ui, progress_bar)

    # File path has been changed
    if file_size != file_size_cera:
        print("Invalid file")
        return

    # File size is smaller than chunk size, 1 segment is needed
    if file_size < chunk_size:
        print("Segment", "Start Uploading.")
        process_segment(from_file, key, 0, transfer_obj, ui, progress_bar)
        helper.reset_directories()
        transfer_obj['segments'][0]['done_uploading'] = True
        helper.save_transfer_file(transfer_obj)
        print("Segment", "Done Uploading. Cleaning up ....")
        upload_name = os.path.basename(from_file)
        file_done_uploading(ui, filename=upload_name)
        try:
            os.remove(helper.transfer_file)
        except OSError:
            raise Exception("Error Occurred while deleting transfer file.")
        transition_after_operation(ui.transition_page, ui, "File Uploaded Successfully")
        helper.reset_directories()
        helper.reset_shards()
        print("-----------------Done Processing and uploading file-----------------")
        print("Time: ", time.time() - start)
        return
    filename = os.path.basename(from_file)
    segment_num = 0
    input_file = open(from_file, 'rb')
    while 1:
        chunk = input_file.read(chunk_size)         # get next part <= chunk size
        if not chunk:                               # eof=empty string from read
            break
        print("Segment#", segment_num, "------START------")
        if not transfer_obj['segments'][segment_num]['done_uploading']:
            print("Segment#", segment_num, "Start Uploading.")
            file_segment_path = helper.segments_directory_path + '/' + str(segment_num) + '_' + filename
            file_segment = open(file_segment_path, 'wb')
            file_segment.write(chunk)
            process_segment(file_segment_path, key, segment_num, transfer_obj, ui, progress_bar)
            file_segment.close()
            helper.reset_directories()
            transfer_obj['segments'][segment_num]['done_uploading'] = True
            helper.save_transfer_file(transfer_obj)
            print("Segment#", segment_num, "Done Uploading. Cleaning up ....")
        else:
            print("Segment#", segment_num, "Already Uploaded(Skipped).")
        segment_num = segment_num + 1

    upload_name = os.path.basename(from_file)
    file_done_uploading(ui, filename=upload_name)
    try:
        os.remove(helper.transfer_file)
    except OSError:
        raise Exception("Error Occurred while deleting transfer file.")

    transition_after_operation(ui.transition_page, ui, "File Uploaded Successfully")
    helper.reset_directories()
    helper.reset_shards()
    input_file.close()
    print("-----------------Cleaning up-----------------")
    print("-----------------Done Processing and uploading file-----------------")
    print("Time: ", time.time() - start)
    # except Exception as e:
    #    exc_type, exc_obj, exc_tb = sys.exc_info()
    #    filename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    #    print(exc_type, filename, exc_tb.tb_lineno)


def retrieve_original_file(key, info, read_size=None):
    """
    this function retrieve the file by decoding and decrypting different segments. Then combine segments into one file
    :param info: file metadata dictionary contain data needed to retrieve file
    :param key: decryption key
    :param read_size: segment size
    """
    if read_size is None:
        read_size = helper.segment_size
    segments_count = len(info["segments"])
    if segments_count > 1:
        for segment_num, segment in enumerate(info["segments"]):
            segment_name = helper.segment_filename + '_' + str(segment_num)
            print("-----------------Decoding Segment#" + str(segment_num) + "-----------------")
            decode(helper.shards_directory_path, helper.encryption_directory, segment_num, segment['k'])
            print("-----------------Decrypting Segment#" + str(segment_num) + "-----------------")
            decrypt(os.path.join(helper.encryption_directory, segment_name),
                    os.path.join(helper.segments_directory_path, segment_name), key)
    else:
        segment_name = helper.segment_filename + '_0'
        print("-----------------Decoding Segment#0-----------------")
        decode(helper.shards_directory_path, helper.encryption_directory, 0, info["segments"][0]['k'])
        print("-----------------Decrypting Segment#0-----------------")
        decrypt(os.path.join(helper.encryption_directory, segment_name),
                os.path.join(helper.segments_directory_path, segment_name), key)

    print("-----------------Retrieve file-----------------")
    output = open(os.path.join(helper.downloaded_output, info['filename']), 'wb')
    parts = os.listdir(helper.segments_directory_path)
    parts.sort()
    for filename in parts:
        file_path = os.path.join(helper.segments_directory_path, filename)
        file_obj = open(file_path, 'rb')
        while 1:
            file_bytes = file_obj.read(read_size)
            if not file_bytes:
                break
            output.write(file_bytes)
        file_obj.close()
    output.close()
    print("-----------------Done Retrieving File-----------")


def download_shards_and_retrieve(filename, key, ui, progress_bar, read_size=None):
    """
    This function download shards needed to retrieve the file and then call retrieve original file function
    :param progress_bar: progress bar to show the percentage of download
    :param filename: the name of the file to be downloaded.
    :param key: the decryption key that will be used to decrypt the files.
    :param ui: ui object.
    :param read_size: segment size
    """
    if read_size is None:
        read_size = helper.segment_size
    transfer_obj = helper.read_download_transfer_file()

    # download is already started, resume the download
    if not transfer_obj["start_flag"]:
        print("-----------------Resume Download ----------------")
        check_old_connections(ui, progress_bar)
        file_metadata = transfer_obj['file_metadata']
        segments = file_metadata["segments"]
    else:
        print("-----------------Request Download from Cera ----------------")
        # get information of the shards to download them
        segments = start_download(filename, ui)
        if segments:
            for segment in segments:
                for shard in segment['shards']:
                    req = {'type': 'download',
                           'port': int(shard['port']),
                           'shard_id': shard['shard_id'],
                           'auth': shard['auth'],
                           'ip': shard['ip_address']}
                    print("-----------------Add Connection to Shard#"+str(shard['shard_no'])+" in Segment#" +
                          str(shard['segment_no'])+"----------------")
                    # Add connection
                    add_connection(req)

            # prepare file metadata dictionary needed by retrieve original file function.
            file_metadata = {
                "filename": filename,
                "segments": segments
            }
            transfer_obj["start_flag"] = False
            transfer_obj['file_metadata'] = file_metadata
            helper.save_download_transfer_file(transfer_obj)

            for segment in segments:
                for shard in segment['shards']:
                    req = {'type': 'download',
                           'port': int(shard['port']),
                           'shard_id': shard['shard_id'],
                           'auth': shard['auth'],
                           'ip': shard['ip_address']}
                    print("-----------------Downloading Shard#"+str(shard['shard_no'])+" in Segment#" +
                          str(shard['segment_no'])+"----------------")

                    # Receive data from storage node
                    receive_data(req, progress_bar)

                    print("-----------------Download Done ----------------")
        else:
            return
    try:
        if not transfer_obj['shards_renamed']:
            # rename the shards to their original names.
            print("-----------------Shards Renaming----------------")
            for segment in segments:
                for shard in segment['shards']:
                    os.rename(os.path.join(helper.shards_directory_path, shard['shard_id']),
                              os.path.join(helper.shards_directory_path,
                                           helper.shard_filename + "_" + str(shard['segment_no']) + "." +
                                           str(shard['shard_no']) + "_" + str(segment["m"]) + ".fec"))
            print("-----------------Shards Renamed-----------------")
            transfer_obj['shards_renamed'] = True
            helper.save_download_transfer_file(transfer_obj)
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        function_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print("Error in renaming shards", exc_type, function_name, exc_tb.tb_lineno)
        return
    print("-----------------Start retrieving-----------------")
    retrieve_original_file(key, file_metadata, read_size)
    print("-----------------Done retrieving-----------------")
    print("-----------------Cleaning up-----------------")
    helper.reset_directories()
    helper.reset_shards()
    transition_after_operation(ui.transition_page, ui, "File Downloaded Successfully")
    try:
        os.remove(helper.download_transfer_file)
    except:
        raise Exception("Error Occurred while deleting transfer file.")


def transition_after_operation(target_page, ui, msg):

    class ChangePageSignalEmitter(QObject):
        change_page_trigger = pyqtSignal(QWidget)
        change_body_trigger = pyqtSignal(str)

        def change_page(self, stacked_widget, target, message):
            self.change_page_trigger.connect(stacked_widget.setCurrentWidget)
            self.change_page_trigger.emit(target)
            self.change_body_trigger.connect(ui.transition_label.setText)
            self.change_body_trigger.emit(message)

    change_page_signal_emitter = ChangePageSignalEmitter()
    change_page_signal_emitter.change_page(ui.stackedWidget, target_page, msg)
