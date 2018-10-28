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
import logging
import logging.config

from manga_db.manga_db import MangaDB
from manga_db.manga import Book
from manga_db.ext_info import ExternalInfo
from manga_db.util import diff_update
from manga_db.constants import CENSOR_IDS
import manga_db.extractor as extr


# DB_PATH = r"N:\_archive\test\tsu-db\manga_db.sqlite"
DB_PATH = r"N:\coding\tsu-info\manga_db.sqlite"
ROOTDIR = os.path.abspath(os.path.dirname(__file__))
WEBGUI_PORT = 5000
logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'console': {'format': '%(asctime)s - %(levelname)s - %(message)s', 'datefmt': "%H:%M:%S"},
        "file": {"format": "%(asctime)-15s - %(name)-9s - %(levelname)-6s - %(message)s"}
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'console',
            'stream': 'ext://sys.stderr'
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'file',
            'filename': os.path.join(ROOTDIR, "manga_db_co.log"),
            'maxBytes': 1048576,
            'backupCount': 5,
            "encoding": "UTF-8"
        }
    },
    'loggers': {
    },
    "root": {
            'level': 'DEBUG',
            'handlers': ['console', 'file']
    },
    'disable_existing_loggers': False
})
logger = logging.getLogger(__name__)


# log unhandled execptions since we cant see the output when debugging the app
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("Uncaught exception: ", exc_info=(exc_type, exc_value, exc_traceback))

    if exc_traceback is not None:
        # printing locals by frame from: Python Cookbook p. 343/343 von Alex Martelli,Anna
        # Ravenscroft,David Ascher
        tb = exc_traceback
        # get innermost traceback
        while tb.tb_next:
            tb = tb.tb_next

        stack = []
        frame = tb.tb_frame
        # walk backwards to outermost frame -> innermost first in list
        while frame:
            stack.append(frame)
            frame = frame.f_back
        stack.reverse()  # remove if you want innermost frame first

        # we could filter ouput by filename (frame.f_code.co_filename) so that we
        # only print locals
        # when we've reached the first frame of that file (could use part of __name__ (here:
        # gwaripper.gwaripper))

        # build debug string by creating list of lines and join them on \n instead
        # of concatenation
        # since adding strings together means creating a new string
        # (and potentially destroying the old ones)
        # for each addition
        # add first string in list literal instead of appending it in the next line
        # -> would be bad practice
        debug_strings = ["Locals by frame, innermost last"]

        for frame in stack:
            debug_strings.append("Frame {} in {} at line {}\n{}\n".format(frame.f_code.co_name,
                                                                          frame.f_code.co_filename,
                                                                          frame.f_lineno, "-"*100))
            for key, val in frame.f_locals.items():
                try:
                    debug_strings.append("\t{:>20} = {}".format(key, val))
                # we must absolutely avoid propagating exceptions, and str(value) could cause any
                # exception, so we must catch any
                except:
                    debug_strings.append("ERROR WHILE PRINTING VALUES")

            debug_strings.append("\n" + "-" * 100 + "\n")

        logger.debug("\n".join(debug_strings))


# sys.excepthook is invoked every time an exception is raised and uncaught
# set own custom function so we can log traceback etc to file
# from: https://stackoverflow.com/questions/6234405/logging-uncaught-exceptions-in-python by gnu_lorien
sys.excepthook = handle_exception

# If the native application sends any output to stderr, the browser will redirect it
# to the browser console.
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


def fetch_book_info(db_con, title_eng, title_foreign, id_onpage, imported_from):
    b_row = db_con.execute(f"""
            SELECT b.id AS BookID, b.last_change AS LastChange, (
                       SELECT group_concat(l.name, ";")
                       FROM BookList bl, List l
                       WHERE bl.book_id = b.id
                       AND bl.list_id = l.id
                   ) AS List
            FROM Books b
            WHERE b.title_eng {'= :title_eng' if title_eng is not None else 'IS NULL'}
            AND b.title_foreign {'= :title_foreign' if title_foreign is not None else 'IS NULL'}
            GROUP BY b.id""", {"title_eng": title_eng,
                               "title_foreign": title_foreign}).fetchone()
    if not b_row:
        logger.debug("Book not in DB! title_eng: %s, title_foreign: %s", title_eng,
                     title_foreign)
        return {}, {}
    ei_rows = db_con.execute(f"""
                SELECT ei.uploader AS Uploader, ei.upload_date AS UploadDate,
                       ei.censor_id AS Censorship, ei.downloaded AS Downloaded,
                       ei.last_update AS LastUpdate, ei.id AS ExtInfoId
                FROM ExternalInfo ei, Books b
                WHERE b.id = ei.book_id
                AND b.id = ?
                AND ei.id_onpage = ? AND ei.imported_from = ?
                """, (b_row["BookID"], id_onpage, imported_from)).fetchall()

    book_info = {
            "Title": Book.build_title(title_eng=title_eng, title_foreign=title_foreign),
            "List": b_row["List"],
            "LastChange": b_row["LastChange"].strftime("%Y-%m-%d"),
            "WebGUIUrl": f"http://localhost:{WEBGUI_PORT}/book/{b_row['BookID']}",
            "BookID": b_row["BookID"]
            }
    if len(ei_rows) > 1:
        multiple_ei = True
    else:
        multiple_ei = False
    if ei_rows:
        ei_info = {
                "Uploader": ei_rows[0]["Uploader"],
                "UploadDate": ei_rows[0]["UploadDate"].strftime("%Y-%m-%d"),
                "Censorship": CENSOR_IDS[ei_rows[0]["Censorship"]],
                "Downloaded": "Yes" if ei_rows[0]["Downloaded"] else "No",
                "LastUpdate": ei_rows[0]["LastUpdate"].strftime("%Y-%m-%d"),
                "MultipleEi": multiple_ei,
                "ExtInfoId": ei_rows[0]["ExtInfoId"]
                }
    else:
        ei_info = {}
    return book_info, ei_info


def main():
    mdb = MangaDB(os.path.dirname(DB_PATH), DB_PATH)
    # tested: with connection-based messaging the app stays alive although it only sends
    # messages when it recieves them (tested with recording start time in variable and sending
    # that every time) whereas with connectionless messaging it always sends a new start time
    # since it restarts every time
    while True:
        receivedMessage = getMessage()
        # data in stdout has to follow nativeMessaging protocol so for debugging write to stderr
        # receiving stderr in browser still doesnt work for me
        # print('To stderr.', file=sys.stderr)
        if receivedMessage["action"] == "get_book_info":
            url, title = receivedMessage["book_info"]
            logger.debug("Getting info for book at url %s", url)
            extr_cls = extr.find(url)
            if extr_cls is None:
                logger.warning("No extractor class found for url %s!", url)
                sendMessage(encodeMessage(["error", "Site not supported!"]))
                continue
            imported_from = extr_cls.site_id
            id_onpage = extr_cls.book_id_from_url(url)
            title_eng, title_foreign = extr_cls.split_title(title)
            # dont use mdb to get info rather use db directly so circumvent id_map
            book_info, ei_info = fetch_book_info(mdb.db_con, title_eng, title_foreign,
                                                 id_onpage, imported_from)
            logger.debug("Book Info:\n%s", book_info)
            logger.debug("External Info:\n%s", ei_info)

            cover_url = extr_cls(url).get_cover()
            sendMessage(encodeMessage({"action": "show_book_info", "cover_url": cover_url,
                                       "book_info": book_info, "ei_info": ei_info}))
        elif receivedMessage["action"] == "toggle_dl":
            ei_id = receivedMessage["ei_id"]
            before = receivedMessage["before"]
            intbool = 1 if before == "No" else 0
            logger.debug("Toggling downloaded for ei id %d; before: %s", ei_id, before)
            ExternalInfo.set_downloaded_id(mdb, ei_id, intbool)
            dled = "Yes" if intbool else "No"
            sendMessage(encodeMessage({"action": "toggle_dl", "Downloaded": dled}))
        elif receivedMessage["action"] == "set_lists":
            book_id = receivedMessage["book_id"]
            before = set(receivedMessage["before"].split(";"))
            after = set(receivedMessage["after"].split(";"))
            added, removed = diff_update(before, after)
            if added:
                Book.add_assoc_col_on_book_id(mdb, book_id, "list", added, before)
            if removed:
                Book.remove_assoc_col_on_book_id(mdb, book_id, "list", removed, before)
            sendMessage(encodeMessage({"action": "set_lists", "List": ";".join(after)}))
        elif receivedMessage:
            sendMessage(encodeMessage({"received_native": receivedMessage}))
