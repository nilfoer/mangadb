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
              "uploader TEXT, pages INTEGER, rating REAL, rating_full TEXT, my_rating REAL, "
              "category TEXT, collection TEXT, groups TEXT, artist TEXT, parody TEXT, "
              "character TEXT, tags TEXT, lists TEXT, last_change DATE, downloaded INTEGER)")
    # commit changes
    conn.commit()

    return conn, c


lists = ["to-read", "downloaded", "femdom", "good", "good futa", "monster",
         "straight shota", "trap", "vanilla", "best"]
# create list with lines where one line contains 3 elements from list with corresponding indexes as string
# use two fstrings to first format index and value and then pad the resulting string to the same length
# is there a way just using one f string? -> no not without using variables, which doesnt work here (at least i dont think so)
descr = [" ".join([f"{f'[{i+n}] {lists[i+n]}':20}" for n in range(3 if (len(lists)-i) >= 3 else len(lists)-i)]) for i in range(0, len(lists), 3)]
# or pad index and value independently?
# descr = [" ".join([f"[{i+n:>2}] {lists[i+n]:15}" for n in range(3 if (len(lists)-i) >= 3 else len(lists)-i)]) for i in range(0, len(lists), 3)]
def enter_manga_lists(i):
    # TODO find way to make sure its visible but not printed every time
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


def prepare_dict_for_db(url, lists, dic):
    eng_title = re.match(eng_title_re, dic["Title"])
    eng_title = eng_title.group(1) if eng_title else dic["Title"]
    # assume group 1 is always present (which it should be, contrary to above where it alrdy might be only english so it wont find a match)
    book_id = int(re.match(re_tsu_book_id, url).group(1))

    if lists:
        downloaded = 1 if "downloaded" in lists else 0
    else:
        downloaded = 0
    # prepare new update dictionary first or use same keys as in tsu_info dict?
    # use seperate update dict so we dont get screwed if keys change
    db_dic = {
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
            "pages": int(dic["Pages"]),
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
                db_dic[key_upd] = ", ".join(dic[key_tsu])
            else:
                db_dic[key_upd] = dic[key_tsu]
        except KeyError:
            continue
    return db_dic

 
# match book id as grp1
re_tsu_book_id = re.compile(r".+tsumino.com/\w+/\w+/(\d+)")
dic_key_helper = ( ("Collection", "collection"), ("Group", "groups"), ("Artist", "artist"),
                   ("Parody", "parody"), ("Character", "character") )
def add_manga_db_entry_from_dict(db_con, url, lists, dic):
    add_dic = prepare_dict_for_db(url, lists, dic)

    db_con.execute("INSERT INTO Tsumino (title, title_eng, url, id_onpage, upload_date, uploader, "
              "pages, rating, rating_full, category, collection, groups, "
              "artist, parody, character, tags, lists, last_change, downloaded) "
              "VALUES (:title, :title_eng, :url, :id_onpage, :upload_date, :uploader, "
              ":pages, :rating, :rating_full, :category, :collection, "
              ":groups, :artist, :parody, :character, :tags, :lists, :last_change, "
              ":downloaded)", add_dic)
    logger.info("Added book with url \"%s\" to database!", url)
    db_con.commit()


def update_manga_db_entry_from_dict(db_con, url, lists, dic):
    book_id = int(re.match(re_tsu_book_id, url).group(1))
    upd_lists = None
    if lists:
        upd_l = input(f"Also update lists for book \"{dic['Title']}\" to previously entered ({lists}) lists? y/n\n")
        if upd_l == "y":
            upd_lists = lists
    # this is executed in all cases except lists evaluating to True and selecting y when asked if you want to update the lists
    if upd_lists is None:
        c = db_con.execute("SELECT lists FROM Tsumino WHERE id_onpage = ?", (book_id,))
        # lists from db is string "list1, list2, .."
        upd_lists = c.fetchone()[0].split(", ")

    update_dic = prepare_dict_for_db(url, upd_lists, dic)

    # seems like book id on tsumino just gets replaced with newer uncensored or fixed version -> check if upload_date uploader pages or tags (esp. uncensored + decensored) changed
    # => WARN to redownload book
    c = db_con.execute("SELECT uploader, upload_date, pages, tags FROM Tsumino WHERE id_onpage = ?", (book_id,))
    res_tuple = c.fetchone()
    field_change_str = []
    for res_tuple_i, key in ((0, "uploader"), (1, "upload_date"), (2, "pages"), (3, "tags")):
        if res_tuple[res_tuple_i] != update_dic[key]:
            print(res_tuple[res_tuple_i], update_dic[key], type(res_tuple[res_tuple_i]), type(update_dic[key]))
            field_change_str.append(f"Field \"{key}\" changed from \"{res_tuple[res_tuple_i]}\" to \"{update_dic[key]}\"!")
    if field_change_str:
        field_change_str = '\n'.join(field_change_str)
        logger.warning(f"Please re-download \"{url}\", since the change of following fields suggest that someone has uploaded a new version:\n{field_change_str}")


    # dont update: title = :title, title_eng = :title_eng, 
    c.execute("""UPDATE Tsumino SET url = :url,
                      upload_date = :upload_date, uploader = :uploader, pages = :pages, 
                      rating = :rating, rating_full = :rating_full, category = :category, 
                      collection = :collection, groups = :groups, artist = :artist, 
                      parody = :parody, character = :character, tags = :tags, lists = :lists, 
                      last_change = :last_change, downloaded = :downloaded 
                      WHERE id_onpage = :id_onpage""", update_dic)
    logger.info("Updated book with url \"%s\" in database!", url)
    db_con.commit()


def watch_clip_db_get_info_after(db_book_ids, fixed_lists=None, predicate=is_tsu_book_url):
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
                                logger.info("Found manga url: \"%s\"", recent_value)
                                if int(re.match(re_tsu_book_id, recent_value).group(1)) in db_book_ids:
                                    logger.info("Book was found in db! Values will be updated!")
                                    upd = True
                                else:
                                    upd = False

                                if fixed_lists is None:
                                    # strip urls of trailing "-" since there is a dash appended to the url when exiting from reading a manga on tsumino (compared to when entering from main site)
                                    manga_lists = enter_manga_lists()
                                    found.append((recent_value.rstrip("-"), manga_lists, upd))
                                else:
                                    found.append((recent_value.rstrip("-"), fixed_lists, upd))
                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Stopped watching clipboard!")

    return found


def filter_duplicate_at_index_of_list_items(i, li):
    # filter duplicates based on element at pos i in tuples only keeping latest entries in list
    # filter_elements = [t[i] for t in tuple_list]
    # i could either use get_index_of_last_match to get index of last occurrence of match in filter_elements and in for loop check if were at that pos True->append False->continue (if count in filter_elements > 1)
    # -> would mean iterating/searching over list (1 + (len(tuple_list) + len(tuple_list)) * len(tuple_list)
    # or reverse tuple_list, and keep track of items at pos i that were alrdy seen/added
    # tuple_list[i] alrdy seen -> continue
    items_at_i = set()
    result = []
    for tup in reversed(li):
        if tup[i] in items_at_i:
            continue
        else:
            result.append(tup)
            items_at_i.add(tup[i])
    # order not preserved, reversing again would be closer to old order
    return result


def get_index_of_last_match(obj, li):
    """Get index of last item matching obj in list"""
    # start end step, start inclusive - end not
    for i in range(len(li)-1, -1, -1):
        if obj == li[i]:
            return i


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

def test_filter_duplicate_at_index_of_list_items():
    l = [   ("abc", 0, 0),
            ("def", 1, 1),
            ("abc", 2, 2,),
            ("ghi", 3, 3,),
            ("def", 4, 4,),
            ("jkl", 5, 5,)]
    res = filter_duplicate_at_index_of_list_items(0, l)
    return res == [('jkl', 5, 5), ('def', 4, 4), ('ghi', 3, 3), ('abc', 2, 2)]

def main():
    optnr = input("OPTIONS: [1] Watch clipboard for manga urls, get and write info afterwards\n")
    if optnr == "1":
        write_infotxt = bool(input("Write info txt files?"))
        print("You can now configure the lists that all following entries should be added to!")
        fixed_list_opt = enter_manga_lists()

        conn, c = load_or_create_sql_db("manga_db.sqlite")
        c.execute("SELECT id_onpage FROM Tsumino")
        ids_in_db = set([tupe[0] for tupe in c.fetchall()])

        l = watch_clip_db_get_info_after(ids_in_db, fixed_lists=fixed_list_opt)
        logger.info("Started working on list with %i items", len(l))
        try:
            while l:
                url, lists, upd = l.pop(0)
                logger.debug("Starting job!")
                if write_infotxt:
                    dic = create_tsubook_info(url)
                else:
                    dic = get_tsubook_info(url)

                if upd:
                    update_manga_db_entry_from_dict(conn, url, lists, dic)
                else:
                    add_manga_db_entry_from_dict(conn, url, lists, dic)
                time.sleep(0.3)
        except Exception:
                # current item is alrdy removed even though it failed on it
                # join() expects list of str -> convert them first with (str(i) for i in tup)
                logger.error("Job was interrupted, the following entries were not processed:\n%s\n%s", ", ".join((url, str(lists), str(upd))), "\n".join((', '.join(str(i) for i in tup) for tup in l)))
                raise
        export_csv_from_sql("manga-db.csv", conn)
if __name__ == "__main__":
    main()

# TODO
