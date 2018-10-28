#!/usr/bin/python -u

# new src: https://github.com/mdn/webextensions-examples/tree/master/native-messaging
# old src: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging
# !!! example from ^^ didnt work -> uses python2
# On the application side, you use standard input to receive messages and standard output to send them.
# Each message is serialized using JSON, UTF-8 encoded and is preceded with a 32-bit value containing the message length in native byte order.
# The maximum size of a single message from the application is 1 MB. The maximum size of a message sent to the application is 4 GB.

# Note that running python with the `-u` flag is required on Windows,
# in order to ensure that stdin and stdout are opened in binary, rather
# than text, mode.

import json
import sys
import struct
import os

from manga_db.manga_db import MangaDB
from manga_db.manga import Book
import manga_db.extractor as extr

DB_PATH = r"N:\coding\tsu-info\manga_db.sqlite"
ROOTDIR = os.path.abspath(os.path.dirname(__file__))

# If the native application sends any output to stderr, the browser will redirect it to the browser console.
# -> use this for debugging


# Python 3.x version
# Read a message from stdin and decode it.
def getMessage():
    rawLength = sys.stdin.buffer.read(4)
    if len(rawLength) == 0:
        sys.exit(0)
    messageLength = struct.unpack('@I', rawLength)[0]
    message = sys.stdin.buffer.read(messageLength).decode('utf-8')
    return json.loads(message)


# Encode a message for transmission,
# given its content.
def encodeMessage(messageContent):
    encodedContent = json.dumps(messageContent).encode('utf-8')
    encodedLength = struct.pack('@I', len(encodedContent))
    return {'length': encodedLength, 'content': encodedContent}


# Send an encoded message to stdout
def sendMessage(encodedMessage):
    sys.stdout.buffer.write(encodedMessage['length'])
    sys.stdout.buffer.write(encodedMessage['content'])
    sys.stdout.buffer.flush()


def main():
    mdb = MangaDB(os.path.dirname(DB_PATH), DB_PATH, read_only=True)
    while True:
        receivedMessage = getMessage()
        # data in stdout has to follow nativeMessaging protocol so for debugging write to stderr
        # receiving stderr in browser still doesnt work for me
        # print('To stderr.', file=sys.stderr)
        if isinstance(receivedMessage, list):
            url, title = receivedMessage
            extr_cls = extr.find(url)
            if extr_cls is None:
                sendMessage(encodeMessage(["error", "Site not supported!"]))
                continue
            imported_from = extr_cls.site_id
            id_onpage = extr_cls.book_id_from_url(url)
            title_eng, title_foreign = extr_cls.TITLE_RE.match(title).groups()
            b = mdb.get_book(title_eng=title_eng, title_foreign=title_foreign)
            if b is None:
                # book not in db
                sendMessage(encodeMessage([url, {}, {}]))
                continue
            ext_info = [ei for ei in b.ext_infos if ei.id_onpage == id_onpage and
                        ei.imported_from == imported_from]
            ext_info = ext_info[0] if ext_info else None
            book_info = {
                    "Title": b.title,
                    "List": b.list,
                    "LastChange": b.last_change.strftime("%Y-%m-%d")
                    }
            if ext_info is not None:
                ei_info = {
                        "Uploader": ext_info.uploader,
                        "UploadDate": ext_info.upload_date.strftime("%Y-%m-%d"),
                        "Censorship": ext_info.censorship,
                        "Downloaded": "Yes" if ext_info.downloaded else "No",
                        "LastUpdate": ext_info.last_update.strftime("%Y-%m-%d")
                        }
            else:
                ei_info = {}

            cover_url = extr_cls(url).get_cover()
            sendMessage(encodeMessage([cover_url, book_info, ei_info]))
        elif receivedMessage:
            sendMessage(encodeMessage(["Received native: ", receivedMessage]))
