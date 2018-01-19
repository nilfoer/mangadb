import os
import csv
import sqlite3

from tsu_info_getter import *

logger = logging.getLogger("manga-db")
logger.setLevel(logging.DEBUG)

# create a file handler
# handler = TimedRotatingFileHandler("gwaripper.log", "D", encoding="UTF-8", backupCount=10)
# max 1MB and keep 5 files
handler = RotatingFileHandler(os.path.join(ROOTDIR, "tsuinfo.log"),
                              maxBytes=1048576, backupCount=5, encoding="UTF-8")
handler.setLevel(logging.DEBUG)

# create a logging format
formatter = logging.Formatter(
    "%(asctime)-15s - %(name)-9s - %(levelname)-6s - %(message)s")
# '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
handler.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(handler)

# create streamhandler
stdohandler = logging.StreamHandler(sys.stdout)
stdohandler.setLevel(logging.INFO)

# create a logging format
formatterstdo = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", "%H:%M:%S")
stdohandler.setFormatter(formatterstdo)
logger.addHandler(stdohandler)


def load_or_create_sql_db(filename):
    """
    Creates connection to sqlite3 db and a cursor object. Creates the table if it doesnt exist yet since,
    the connect function creates the file if it doesnt exist but it doesnt contain any tables then.

    :param filename: Filename string/path to file
    :return: connection to sqlite3 db and cursor instance
    """
    # PARSE_DECLTYPES -> parse types and search for converter function for it instead of searching for converter func for specific column name
    conn = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Tsumino (id INTEGER PRIMARY KEY ASC, title TEXT, "
              "title_eng TEXT, url TEXT, upload_date DATE, uploader TEXT, pages INTEGER, "
              "rating REAL, rating_full TEXT, category TEXT, collection TEXT, group TEXT, "
              "artist TEXT, parody TEXT, character TEXT, tags TEXT, list TEXT, last_change DATE)")
    # commit changes
    conn.commit()

    return conn, c

def watch_clip_get_info_after():
    found = None
    # predicate = is_tsu_book_url, callback = create_tsubook_info
    watcher = ClipboardWatcher(is_tsu_book_url, None, ROOTDIR, 0.1)
    try:
            logger.info("Watching clipboard...")
            watcher.run()
    except KeyboardInterrupt:
            found = watcher.get_found()
            watcher.stop()
            logger.info("Stopped watching clipboard!")
    return found


def main():
    optnr = input("OPTIONS: [1] Watch clipboard for manga urls, get and write info afterwards")
    if optnr == "1":
        l = watch_clip_get_info_after()
        logger.info("Started working on list with %i items", len(l))
        # TODO rework this, so we export current list on crash
        # but even needed? since no processing is done until we start working list here
        try:
                while l:
                        item = l.pop(0)
                        create_tsubook_info(item)
                        time.sleep(0.3)
        except Exception:
                # item is alrdy removed even though it failed on it
                logger.error("Job was interrupted, the following entries were not processed:\n%s\n%s", item, "\n".join(l))
                raise
if __name__ == "__main__":
    main()
