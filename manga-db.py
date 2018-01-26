import time
import sys
import logging
import os
import datetime
import csv
import sqlite3

from logging.handlers import RotatingFileHandler

import pyperclip

from tsu_info_getter import *

ROOTDIR = os.path.dirname(os.path.realpath(__file__))

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
    # group reserved keyword -> use groups for col name
    # SQLite does not have a separate Boolean -> stored as integers 0 (false) and 1 (true).
    c.execute("CREATE TABLE IF NOT EXISTS Tsumino (id INTEGER PRIMARY KEY ASC, title TEXT UNIQUE, "
              "title_eng TEXT, url TEXT UNIQUE, id_onpage INTEGER UNIQUE, upload_date DATE, "
              "uploader TEXT, pages INTEGER, rating REAL, rating_full TEXT, category TEXT, "
              "collection TEXT, groups TEXT, artist TEXT, parody TEXT, character TEXT, tags TEXT, "
              "lists TEXT, last_change DATE, downloaded INTEGER)")
    # commit changes
    conn.commit()

    return conn, c


def enter_manga_lists():
    lists = ["to-read", "downloaded", "femdom", "good", "good futa", "monster",
             "straight shota", "trap", "vanilla", "best"]
    # create list with lines where one line contains 3 elements from list with corresponding indexes as string
    # use two fstrings to first format index and value and then pad the resulting string to the same length
    # is there a way just using one f string? -> no not without using variables, which doesnt work here (at least i dont think so)
    descr = [" ".join([f"{f'[{i+n}] {lists[i+n]}':20}" for n in range(3 if (len(lists)-i) >= 3 else len(lists)-i)]) for i in range(0, len(lists), 3)]
    # or pad index and value independently?
    # descr = [" ".join([f"[{i+n:>2}] {lists[i+n]:15}" for n in range(3 if (len(lists)-i) >= 3 else len(lists)-i)]) for i in range(0, len(lists), 3)]
    print("\n".join(descr))

    while True:
        result = []
        inp = input("Enter indexes (displayed in [i]) of lists the manga should be in seperated by commas:\n")
        if inp:
            for ind in inp.split(","):
                try:
                    lname = lists[int(ind)]
                    result.append(lname)
                except ValueError:
                    logger.error("\"%s\" was not a valid list index, please re-enter list indexes", ind)
                    break
            # keep looping (while) till all list names are recognized -> for doesnt break -> return
            else:
                return result
        else:
            # no input -> dont add to any lists
            return None

 
# match book id as grp1
re_tsu_book_id = re.compile(r".+tsumino.com/\w+/\w+/(\d+)")
dic_key_helper = ( ("Collection", "collection"), ("Group", "groups"), ("Artist", "artist"),
                   ("Parody", "parody"), ("Character", "character") )
def update_manga_db_entry_from_dict(db_con, url, lists, dic):
    eng_title = re.match(eng_title_re, dic["Title"])
    eng_title = eng_title.group(1) if eng_title else dic["Title"]
    # assume group 1 is always present (which it should be, contrary to above where it alrdy might be only english so it wont find a match)
    book_id = re.match(re_tsu_book_id, url).group(1)

    if lists:
        downloaded = 1 if "downloaded" in lists else 0
    else:
        downloaded = 0
    # prepare new update dictionary first or use same keys as in tsu_info dict?
    # use seperate update dict so we dont get screwed if keys change
    update_dic = {
            "title": dic["Title"],
            "title_eng": eng_title,
            "url": url,
            "id_onpage": book_id, 
            # strptime -> string parse time (inverse of strftime, second param is format
            # tsu date in form: 2016 December 10
            # %Y -> Year with century as a decimal number. 2010, 2011 ...
            # %B -> Month as locale’s full name.
            # %d -> Day of the month as a zero-padded decimal number.
            # module  class    method
            # datetime.datetime.strptime(date, "%Y-%m-%d")
            # with datetime.datetime.strptime time gets defaulted to 0, 0
            # datetime.datetime.strptime("2016 December 10", "%Y %B %d")
            # datetime.datetime(2016, 12, 10, 0, 0)
            # use .date() to get date instead of datetime
            # datetime.datetime.strptime("2016 December 10", "%Y %B %d").date()
            # datetime.date(2016, 12, 10)
            "upload_date": datetime.datetime.strptime(dic["Uploaded"], "%Y %B %d").date(),
            "uploader": dic["Uploader"][0],
            "pages": dic["Pages"],
            "rating": float(dic["Rating"].split()[0]),
            "rating_full": dic["Rating"],
            # might be list -> join on ", " if just one entry no comma added
            "category": ", ".join(dic["Category"]),
            "collection": None,
            "groups": None,
            "artist": None,
            "parody": None,
            "character": None,
            "tags": ", ".join(dic["Tag"]),
            # TODO have lists as seperate tables ADDITIONALY?
            "lists": ", ".join(lists) if lists else None,
            "last_change": datetime.date.today(),
            "downloaded": downloaded
            }
    # update values of keys that are not always present on book age/in dic
    for key_tsu, key_upd in dic_key_helper:
        try:
            if isinstance(dic[key_tsu], list):
                update_dic[key_upd] = ", ".join(dic[key_tsu])
            else:
                update_dic[key_upd] = dic[key_tsu]
        except KeyError:
            continue

    db_con.execute("INSERT INTO Tsumino (title, title_eng, url, id_onpage, upload_date, uploader, "
              "pages, rating, rating_full, category, collection, groups, "
              "artist, parody, character, tags, lists, last_change, downloaded) "
              "VALUES (:title, :title_eng, :url, :id_onpage, :upload_date, :uploader, "
              ":pages, :rating, :rating_full, :category, :collection, "
              ":groups, :artist, :parody, :character, :tags, :lists, :last_change, "
              ":downloaded)", update_dic)
    logger.info("Added/Updated book with url \"%s\" to/in database!", url)
    db_con.commit()


def watch_clip_db_get_info_after(fixed_lists=None, predicate=is_tsu_book_url):
    found = []
    stopping = False
    try:
        logger.info("Watching clipboard...")
        recent_value = ""
        while not stopping:
                tmp_value = pyperclip.paste()
                if tmp_value != recent_value:
                        recent_value = tmp_value
                        # if predicate is met
                        if predicate(recent_value):
                                # call callback
                                logger.info("Found manga url: \"%s\"", recent_value)
                                if fixed_lists is None:
                                    # strip urls of trailing "-" since there is a dash appended to the url when exiting from reading a manga on tsumino (compared to when entering from main site)
                                    manga_lists = enter_manga_lists()
                                    found.append((recent_value.rstrip("-"), manga_lists))
                                else:
                                    found.append((recent_value.rstrip("-"), fixed_lists))
                                # TODO filter duplicates afterwards only keeping latest entries in list so we can just copy link again to fix wrong lists etc.
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Stopped watching clipboard!")

    return found

def export_csv_from_sql(filename, db_con):
    """
    Fetches and writes all rows (with all cols) in db_con's database to the file filename using
    writerows() from the csv module

    writer kwargs: dialect='excel', delimiter=";"

    :param filename: Filename or path to file
    :param db_con: Connection to sqlite db
    :return: None
    """
    # newline="" <- important otherwise weird behaviour with multiline cells (adding \r) etc.
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        # excel dialect -> which line terminator(\r\n), delimiter(,) to use, when to quote cells etc.
        csvwriter = csv.writer(csvfile, dialect="excel", delimiter=";")

        # get rows from db
        c = db_con.execute("SELECT * FROM Tsumino")
        rows = c.fetchall()

        # cursor.description -> sequence of 7-item sequences each containing info describing one result column
        col_names = [description[0] for description in c.description]
        csvwriter.writerow(col_names)  # header
        # write the all the rows to the file
        csvwriter.writerows(rows)

def main():
    optnr = input("OPTIONS: [1] Watch clipboard for manga urls, get and write info afterwards\n")
    if optnr == "1":
        write_infotxt = bool(input("Write info txt files?"))
        # TODO
        print("You can now configure the lists that all following entries should be added to!")
        fixed_list_opt = enter_manga_lists()

        conn, c = load_or_create_sql_db("manga_db.sqlite")

        l = watch_clip_db_get_info_after(fixed_lists=fixed_list_opt)
        logger.info("Started working on list with %i items", len(l))
        # TODO rework this, so we export current list on crash
        # but even needed? since no processing is done until we start working list here
        try:
            while l:
                url, lists = l.pop(0)
                logger.debug("Starting job!")
                if write_infotxt:
                    dic = create_tsubook_info(url)
                else:
                    dic = get_tsubook_info(url)
                update_manga_db_entry_from_dict(conn, url, lists, dic)
                time.sleep(0.3)
        except Exception:
                # current item is alrdy removed even though it failed on it
                logger.error("Job was interrupted, the following entries were not processed:\n(%s, %s)\n%s", url, lists, "\n".join((f"({u}, {li})" for u,li in l)))
                raise
        export_csv_from_sql("manga-db.csv", conn)
if __name__ == "__main__":
    main()

# TODO
# even better to just use id in tsumino.com/Book/Info/30203/pure-trap-fakku -> id == 30203
