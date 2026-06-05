import hashlib
import random
from .helper import Helper
helper = Helper()


def generate_audits(file, audits_count=helper.audits_default_count):
    """
    This function generate audits to a given file
    :param file: input file that will need audits
    :param audits_count: number of audits to be generated
    :return: list of audits
    """
    audits = []
    with open(file, "rb") as file:
        file_hash = hashlib.md5()
        file_content = file.read()
        file_hash.update(file_content)

    for i in range(audits_count):
        # generate random salt of length 16 bytes
        salt = ''.join([chr(random.randint(0, 0xFF)) for i in range(16)])
        file_hash_copy = file_hash.copy()

        file_hash_copy.update(salt.encode())
        # append to audits list
        audits.append({"salt": salt, "hash": file_hash_copy.hexdigest()})
    return audits
