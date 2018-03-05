import time
import sys
import logging
import os
import datetime
import csv
import sqlite3
import urllib.request

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

# normal urllib user agent is being blocked by tsumino
# set user agent to use with urrlib
opener = urllib.request.build_opener()
opener.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0')]
# ...and install it globally so it can be used with urlretrieve/open
urllib.request.install_opener(opener)



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
    c.execute("""CREATE TABLE IF NOT EXISTS Tsumino (
                 id INTEGER PRIMARY KEY ASC,
                 title TEXT UNIQUE NOT NULL, 
                 title_eng TEXT NOT NULL, 
                 url TEXT UNIQUE NOT NULL, 
                 id_onpage INTEGER UNIQUE NOT NULL,
                 upload_date DATE NOT NULL, 
                 uploader TEXT, 
                 pages INTEGER NOT NULL, 
                 rating REAL NOT NULL,
                 rating_full TEXT NOT NULL, 
                 my_rating REAL, 
                 category TEXT, 
                 collection TEXT, 
                 groups TEXT, 
                 artist TEXT, 
                 parody TEXT, 
                 character TEXT, 
                 last_change DATE NOT NULL,
                 downloaded INTEGER,
                 favorite INTEGER)""")

    # create index for id_onpage so we SQLite can access it with O(log n) instead of O(n) complexit when using WHERE id_onpage = ? (same exists for PRIMARY KEY)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS book_id_onpage ON Tsumino (id_onpage)")

    # was using AUTO_INCREMENT here but it wasnt working (tag_id remained NULL)
    # SQLite recommends that you should not use AUTOINCREMENT attribute because:
    # The AUTOINCREMENT keyword imposes extra CPU, memory, disk space, and disk I/O overhead and should be avoided if not strictly needed. It is usually not needed.
    # (comment Moe: --> PRIMARY KEY implies AUTOINCREMENT)
    # In addition, the way SQLite assigns a value for the AUTOINCREMENT column is slightly different from the way it used for rowid column. -> wont reuse unused ints when max nr(9223372036854775807; signed 64bit) is used -> error db full
    c.execute("""CREATE TABLE IF NOT EXISTS Tags(
                 tag_id INTEGER PRIMARY KEY ASC,
                 name TEXT UNIQUE NOT NULL,
                 list_bool INTEGER NOT NULL)""")

    # foreign key book_id is linked to id column in Tsumino table
    # also possible to set actions on UPDATE/DELETE
    # FOREIGN KEY (foreign_key_columns)
    # REFERENCES parent_table(parent_key_columns)
    # ON UPDATE action 
    # ON DELETE action;
    # this is a bridge/intersection/junction/mapping-table
    # primary key is a composite key containing both book_id and tag_id
    # FOREIGN KEY.. PRIMARY KEY (..) etc. muss nach columns kommen sonst syntax error
    # NOT NULL for book_id, tag_id must be stated even though theyre primary keys since
    # in SQLite they can be 0 (contrary to normal SQL)
    # ON DELETE CASCADE, wenn der eintrag des FK in der primärtabelle gelöscht wird dann auch in dieser (detailtabelle) die einträge löschen -> Löschweitergabe
    c.execute("""CREATE TABLE IF NOT EXISTS BookTags(
                 book_id INTEGER NOT NULL, 
                 tag_id INTEGER NOT NULL,
                 FOREIGN KEY (book_id) REFERENCES Tsumino(id)
                 ON DELETE CASCADE,
                 FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
                 ON DELETE CASCADE,
                 PRIMARY KEY (book_id, tag_id))""")

    # commit changes
    conn.commit()

    return conn, c


lists = ["li_to-read", "li_downloaded", "li_prob-good", "li_femdom", "li_good", "li_good futa",
         "li_monster", "li_straight shota", "li_trap", "li_vanilla", "li_best"]
# create list with lines where one line contains 3 elements from list with corresponding indexes as string
# use two fstrings to first format index and value and then pad the resulting string to the same length
# is there a way just using one f string? -> no not without using variables, which doesnt work here (at least i dont think so)
descr = [" ".join([f"{f'[{i+n}] {lists[i+n]}':20}" for n in range(3 if (len(lists)-i) >= 3 else len(lists)-i)]) for i in range(0, len(lists), 3)]
# or pad index and value independently?
# descr = [" ".join([f"[{i+n:>2}] {lists[i+n]:15}" for n in range(3 if (len(lists)-i) >= 3 else len(lists)-i)]) for i in range(0, len(lists), 3)]
def enter_manga_lists(i):
    # only print available lists every fifth time
    if i%5 == 0:
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


dic_key_helper = ( ("Collection", "collection"), ("Group", "groups"), ("Artist", "artist"),
                   ("Parody", "parody"), ("Character", "character"), ("Uploader", "uploader") )

def prepare_dict_for_db(url, dic):
    eng_title = re.match(eng_title_re, dic["Title"])
    eng_title = eng_title.group(1) if eng_title else dic["Title"]
    # book_id_from_url assumes group 1 is always present (which it should be, contrary to above where it alrdy might be only english so it wont find a match)
    book_id = book_id_from_url(url)

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
            "uploader": None,  # sometimes no uploader specified
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
            "last_change": datetime.date.today(),
            "downloaded": None,
            "favorite": None
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

 
def add_tags(db_con, tags):
    """Leaves committing changes to upper scope"""
    tags = [(tag, 1 if tag.startswith("li_") else 0) for tag in tags]
    # executemany accepts a list of tuples (one ? in sqlite code for every member of the tuples)
    # INSERT OR IGNORE -> ignore violation of unique constraint of column -> one has to be unique otherwise new rows inserted
    # It is then possible to tell the database that you want to silently ignore records that would violate such a constraint
    # theres also INSERT OR REPLACE -> replace if unique constraint violated
    c = db_con.executemany("INSERT OR IGNORE INTO Tags(name, list_bool) VALUES(?, ?)", tags)
    # also possible:
    # INSERT INTO memos(id,text) 
    # SELECT 5, 'text to insert' <-- values you want to insert
    # WHERE NOT EXISTS(SELECT 1 FROM memos WHERE id = 5 AND text = 'text to insert')

    return c

def add_tags_to_book(db_con, bid, tags):
    """Leaves committing changes to upper scope. Also sets downloaded and favorite
       if those tags are in tags."""
    c = add_tags(db_con, tags)

    # create list with [(bid, tag), (bid, tag)...
    bid_tags = zip([bid]*len(tags), tags)
    # we can specify normal values in a select statment (that will also get used e.g. 5 as bid)
    # here using ? which will get replaced by bookid from tuple
    # then select value of tag_id column in Tags table where the name matches the current tag
    c.executemany("""INSERT OR IGNORE INTO BookTags(book_id, tag_id)
                     SELECT ?, Tags.tag_id FROM Tags
                     WHERE Tags.name = ?""", bid_tags)
    # ^^taken from example: INSERT INTO Book_Author (Book_ISBN, Author_ID)SELECT Book.Book_ISBN, Book.Author_ID FROM Book GROUP BY Book.Book_ISBN, Book.Author_ID
    # --> GROUP BY to get distinct (no duplicate) values
    # ==> but better to use SELECT DISTINCT!!
    # The DISTINCT clause is an optional clause of the SELECT statement. The DISTINCT clause allows you to remove the duplicate rows in the result set

    if "li_downloaded" in tags:
        c.execute("UPDATE Tsumino SET downloaded = ? WHERE id = ?", (1, bid))
    if "li_best" in tags:
        c.execute("UPDATE Tsumino SET favorite = ? WHERE id = ?", (1, bid))

    return c


def add_manga_db_entry_from_dict(db_con, url, lists, dic):
    add_dic = prepare_dict_for_db(url, dic)

    if lists:
        add_dic["downloaded"] = 1 if "li_downloaded" in lists else 0
        add_dic["favorite"] = 1 if "li_best" in lists else 0
    else:
        add_dic["downloaded"] = 0
        add_dic["favorite"] = 0

    with db_con:
        c = db_con.execute("INSERT INTO Tsumino (title, title_eng, url, id_onpage, upload_date, "
                  "uploader, pages, rating, rating_full, category, collection, groups, "
                  "artist, parody, character, last_change, downloaded, favorite) "
                  "VALUES (:title, :title_eng, :url, :id_onpage, :upload_date, :uploader, "
                  ":pages, :rating, :rating_full, :category, :collection, "
                  ":groups, :artist, :parody, :character, :last_change, "
                  ":downloaded, :favorite)", add_dic)

        # workaround to make concatenation work
        if lists is None:
            lists = []
        # use cursor.lastrowid to get id of last insert in Tsumino table
        add_tags_to_book(db_con, c.lastrowid, lists + dic["Tag"])

        logger.info("Added book with url \"%s\" to database!", url)


def update_manga_db_entry_from_dict(db_con, url, lists, dic):
    book_id = book_id_from_url(url)

    c = db_con.execute("SELECT id FROM Tsumino WHERE id_onpage = ?", (book_id,))
    # lists from db is string "list1, list2, .."
    id_internal = c.fetchone()[0]

    update_dic = prepare_dict_for_db(url, dic)

    # get previous value for downloaded and fav from db
    c = db_con.execute("SELECT downloaded, favorite FROM Tsumino WHERE id_onpage = ?", (book_id,))
    downloaded, favorite = c.fetchone()
    if lists:
        update_dic["downloaded"] = 1 if "li_downloaded" in lists else downloaded
        update_dic["favorite"] = 1 if "li_best" in lists else downloaded

    # seems like book id on tsumino just gets replaced with newer uncensored or fixed version -> check if upload_date uploader pages or tags (esp. uncensored + decensored) changed
    # => WARN to redownload book
    c.execute("SELECT uploader, upload_date, pages FROM Tsumino WHERE id_onpage = ?", (book_id,))
    res_tuple = c.fetchone()

    field_change_str = []
    # build line str of changed fields
    for res_tuple_i, key in ((0, "uploader"), (1, "upload_date"), (2, "pages")):
        if res_tuple[res_tuple_i] != update_dic[key]:
            field_change_str.append(f"Field \"{key}\" changed from \"{res_tuple[res_tuple_i]}\" to \"{update_dic[key]}\"!")

    # check tags seperately due to using bridge table
    # get column tag names where tag_id in BookTags and Tags match and book_id in BookTags is the book were looking for
    c.execute("""SELECT Tags.name
                 FROM BookTags bt, Tags
                 WHERE bt.tag_id = Tags.tag_id
                 AND bt.book_id = ?""", (id_internal,))
    # filter lists from tags first
    tags = [tup[0] for tup in c.fetchall() if not tup[0].startswith("li_")]
    removed_on_page = None
    # compare sorted to see if tags changed, alternatively convert to set and add -> see if len() changed
    if sorted(tags) != sorted(dic["Tag"]):
        field_change_str.append(f"Field \"tags\" changed from \"{', '.join(tags)}\" to \"{', '.join(dic['Tag'])}\"!")
        removed_on_page = set(tags).difference(dic["Tag"])

    if field_change_str:
        field_change_str = '\n'.join(field_change_str)
        logger.warning(f"Please re-download \"{url}\", since the change of following fields suggest that someone has uploaded a new version:\n{field_change_str}")

    with db_con:
        # dont update: title = :title, title_eng = :title_eng, 
        c.execute("""UPDATE Tsumino SET
                     upload_date = :upload_date, uploader = :uploader, pages = :pages, 
                     rating = :rating, rating_full = :rating_full, category = :category, 
                     collection = :collection, groups = :groups, artist = :artist, 
                     parody = :parody, character = :character, 
                     last_change = :last_change, downloaded = :downloaded, favorite = :favorite 
                     WHERE id_onpage = :id_onpage""", update_dic)

        # workaround to make concatenation work
        if lists is None:
            lists = []
        # c.lastrowid doesnt work with update

        if removed_on_page:
            # remove tags that are still present in db but were removed on page
            remove_tags_from_book(db_con, url, removed_on_page)

        add_tags_to_book(db_con, id_internal, lists + dic["Tag"])

        logger.info("Updated book with url \"%s\" in database!", url)


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
                                if book_id_from_url(recent_value) in db_book_ids:
                                    logger.info("Book was found in db! Values will be updated!")
                                    upd = True
                                else:
                                    upd = False

                                if fixed_lists is None:
                                    manga_lists = enter_manga_lists(len(found))
                                    # strip urls of trailing "-" since there is a dash appended to the url when exiting from reading a manga on tsumino (compared to when entering from main site)
                                    found.append((recent_value.rstrip("-"), manga_lists, upd))
                                else:
                                    found.append((recent_value.rstrip("-"), fixed_lists, upd))
                        elif recent_value == "set_tags":
                            url, tag_li, upd = found.pop()
                            logger.info("Setting tags for \"%s\"! Previous tags were: %s", url, tag_li)
                            manga_lists = enter_manga_lists(len(found)-1)
                            found.append((url, manga_lists, upd))


                time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Stopped watching clipboard!")

    # use filter_duplicate_at_index_of_list_items to only keep latest list element with same urls -> index 0 in tuple
    return filter_duplicate_at_index_of_list_items(0, found)


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

        # get rows from db, using joins and aggregate func group_concat to combine data from bridge table
        # SELECT Tsumino.*, Tags.* and the inner joins without the group by would return one row for every tag that a book has
        # the inner join joins matching (<- matching dependent on ON condition e.g. Tsumino id matching book_id in BookTags) rows from both tables --> MATCHING rows only
        # then we group by Tsumino.id and the aggregate function group_concat(X) returns a string which is the concatenation of all non-NULL values of X --> default delimiter is "," but customizable with group_concat(X,Y) as Y
        # rename col group_concat(Tags.name) to tags with AS, but group_concat(Tags.name) tags would also work
        c = db_con.execute("""SELECT Tsumino.*, group_concat(Tags.name) AS tags
                              FROM Tsumino
                              INNER JOIN BookTags bt ON Tsumino.id = bt.book_id
                              INNER JOIN Tags ON Tags.tag_id = bt.tag_id
                              GROUP BY Tsumino.id""")
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


# match book id as grp1
re_tsu_book_id = re.compile(r".+tsumino.com/\w+/\w+/(\d+)")
def book_id_from_url(url):
    try:
        return int(re.match(re_tsu_book_id, url).group(1))
    except IndexError:
        logger.warning("No book id could be extracted from \"%s\"!", url)
        # reraise or continue and check if bookid returned in usage code?
        raise


def rate_manga(db_con, url, rating):
    """Leaves commiting changes to upper scope!!"""
    book_id = book_id_from_url(url)
    db_con.execute("UPDATE Tsumino SET my_rating = ? WHERE id_onpage = ?", (rating, book_id))
    logger.info("Successfully updated rating of book with id \"%s\" to \"%s\"", book_id, rating)


def search_tags_intersection(db_con, tags, keep_row_fac=False):
    """Searches for entries containing all tags in tags and returns the rows as
    a list of sqlite3.Row objects
    :param db_con: Open connection to database
    :param tags: List of tags as strings
    :return List of sqlite3.Row objects"""

    # would also be possible to use c.description but as i want to populate a dictionary anyways Row is a better fit
    # Row provides both index-based and case-insensitive name-based access to columns with almost no memory overhead
    db_con.row_factory = sqlite3.Row
    # we need to create new cursor after changing row_factory
    c = db_con.cursor()

    # even though Row class can be accessed both by index (like tuples) and case-insensitively by name
    # reset row_factory to default so we get normal tuples when fetching (should we generate a new cursor)
    # new_c will always fetch Row obj and cursor will fetch tuples
    # -> this was generating problems when called from webGUI that always expected Rows since we set it there in the module, but calling the search_tags_.. functions always reset it back to tuples
    if not keep_row_fac:
        db_con.row_factory = None

    # dynamically insert correct nr (as many ? as elements in tags) of ? in SQLite
    # query using join on ", " and ["?"] * amount
    # then unpack list with arguments using *tags

    # SQLite Query -> select alls columns in Tsumino
    # tagids must match AND name of the tag(singular) must be in tags list
    # bookids must match
    # results are GROUPed BY Tsumino.id and only entries are returned that occur
    # ? (=nr of tags in tags) times --> matching all tags
    c.execute(f"""SELECT Tsumino.*
                  FROM BookTags bt, Tsumino, Tags
                  WHERE bt.tag_id = Tags.tag_id
                  AND (Tags.name IN ({', '.join(['?']*len(tags))}))
                  AND Tsumino.id = bt.book_id
                  GROUP BY Tsumino.id
                  HAVING COUNT( Tsumino.id ) = ?
                  ORDER BY Tsumino.id DESC""", (*tags, len(tags)))

    return c.fetchall()


def search_tags_exclude(db_con, tags, keep_row_fac=False):
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None
    # select all tsumino.ids that contain these tags (OR, would be AND with HAVING COUNT)
    # -> select all rows whose ids are not in the sub-query
    c.execute(f"""SELECT Tsumino.*
                  FROM Tsumino
                  WHERE Tsumino.id NOT IN (
                          SELECT Tsumino.id 
                          FROM BookTags bt, Tsumino, Tags 
                          WHERE Tsumino.id = bt.book_id 
                          AND bt.tag_id = Tags.tag_id 
                          AND Tags.name IN ({', '.join(['?']*len(tags))})
                )
                ORDER BY Tsumino.id DESC""", (*tags,))
    # ^^ use *tags, -> , to ensure its a tuple when only one tag supplied

    return c.fetchall()


def search_tags_intersection_exclude(db_con, tags_and, tags_ex, keep_row_fac=False):
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None

    c.execute(f"""SELECT Tsumino.*
                  FROM BookTags bt, Tsumino, Tags
                  WHERE bt.tag_id = Tags.tag_id
                  AND (Tags.name IN ({', '.join(['?']*len(tags_and))}))
                  AND Tsumino.id = bt.book_id
                  AND Tsumino.id NOT IN (
                    SELECT Tsumino.id 
                    FROM BookTags bt, Tsumino, Tags 
                    WHERE Tsumino.id = bt.book_id 
                    AND bt.tag_id = Tags.tag_id 
                    AND Tags.name IN ({', '.join(['?']*len(tags_ex))})
                  )
                  GROUP BY Tsumino.id
                  HAVING COUNT( Tsumino.id ) = ?
                  ORDER BY Tsumino.id DESC""", (*tags_and, *tags_ex, len(tags_and)))

    return c.fetchall()


def search_tags_string_parse(db_con, tagstring, keep_row_fac=False):
    if "!" in tagstring:
        excl_nr = tagstring.count("!")
        # nr of commas + 1 == nr of tags
        tags_nr = tagstring.count(",") + 1
        if tags_nr == excl_nr:
            tags = [tag[1:] for tag in tagstring.split(",")]
            # only excluded tags in tagstring
            return search_tags_exclude(db_con, tags, keep_row_fac=keep_row_fac)
        else:
            # is list comprehension faster even though we have to iterate over the list twice?
            tags_and = []
            tags_ex = []
            # sort tags for search_tags_intersection_exclude func
            for tag in tagstring.split(","):
                if tag[0] == "!":
                    # remove ! then append
                    tags_ex.append(tag[1:])
                else:
                    tags_and.append(tag)

            return search_tags_intersection_exclude(db_con, tags_and, tags_ex, keep_row_fac=keep_row_fac)
    else:
        tags = tagstring.split(",")
        return search_tags_intersection(db_con, tags, keep_row_fac=keep_row_fac)


def set_favorite_by_id(db_con, id_internal, fav_intbool):
    """Leaves commiting changes to upper scope
       :param fav_intbool: 0 or 1"""
    db_con.execute("UPDATE Tsumino SET favorite = ? WHERE id = ?", (fav_intbool, id_internal))
    logger.info("Set favorite on bookid %s to %s", id_internal, fav_intbool)


def remove_tags_from_book_id(db_con, id_internal, tags):
    """Leave commiting changes to upper scope"""
    # also do this for li_downloaded, but removing from this list would only make sense if it happened by accident and then we dont need to set downloaded
    if "li_best" in tags:
        set_favorite_by_id(db_con, id_internal, 0)

    db_con.execute(f"""DELETE FROM BookTags WHERE BookTags.tag_id IN
                       (SELECT Tags.tag_id FROM Tags
                       WHERE (Tags.name IN ({', '.join(['?']*len(tags))})))
                       AND BookTags.book_id = ?""", (*tags, id_internal))
    logger.info("Tags %s were successfully removed from book with id \"%s\"", tags, id_internal)


def remove_tags_from_book(db_con, url, tags):
    """Leave commiting changes to upper scope"""
    book_id = book_id_from_url(url)

    # cant use DELETE FROM with multiple tables or multiple WHERE statements -> use" WITH .. AS" (->Common Table Expressions, but they dont seem to work for me with DELETE -> error no such table, but they work with SELECT ==> this due to acting like temporary views and thus are READ-ONLY) or seperate subquery with "IN"
    # -> we can only use CTE/with for the subqueries/select statements
    # WITH bts AS (
    # SELECT BookTags.*
    # FROM BookTags, Tags
    # WHERE BookTags.book_id = 12
    # AND (Tags.name IN ('Yaoi'))
    # AND BookTags.tag_id = Tags.tag_id
    # ) 
    # DELETE
    # FROM BookTags
    # WHERE BookTags.book_id IN (select book_id FROM bts)
    # AND BookTags.tag_id IN (select tag_id FROM bts)

    # delete all rows that contain a tagid where the name col in Tags matches one of the tags to delete and the book_id matches id of Tsumino table where id_onpage matches our book_id
    c = db_con.execute(f"""DELETE FROM BookTags WHERE BookTags.tag_id IN
                       (SELECT Tags.tag_id FROM Tags
                       WHERE (Tags.name IN ({', '.join(['?']*len(tags))})))
                       AND BookTags.book_id IN
                       (SELECT Tsumino.id FROM Tsumino
                       WHERE Tsumino.id_onpage = ?)""", (*tags, book_id))

    if "li_best" in tags:
        set_favorite_by_id(db_con, c.lastrowid, 0)
    logger.info("Tags %s were successfully removed from book with url \"%s\"", tags, url)


def add_tags_to_book_cl(db_con, url, tags):
    book_id = book_id_from_url(url)
    c = db_con.execute("SELECT Tsumino.id FROM Tsumino WHERE Tsumino.id_onpage = ?", (book_id,))
    id_internal = c.fetchone()[0]
    add_tags_to_book(db_con, id_internal, tags)
    logger.info("Tags %s were successfully added to book with url \"%s\"", tags, url)


def get_tags_by_book_url(db_con, url):
    book_id = book_id_from_url(url)
    c = db_con.execute("""SELECT group_concat(Tags.name)
                          FROM Tags, BookTags bt, Tsumino
                          WHERE bt.book_id = Tsumino.id
                          AND Tsumino.id_onpage = ?
                          AND bt.tag_id = Tags.tag_id
                          GROUP BY bt.book_id""", (book_id,))
    return c.fetchone()[0]


def get_tags_by_book_id_onpage(db_con, id_onpage):
    c = db_con.execute("""SELECT group_concat(Tags.name)
                          FROM Tags, BookTags bt, Tsumino
                          WHERE bt.book_id = Tsumino.id
                          AND Tsumino.id_onpage = ?
                          AND bt.tag_id = Tags.tag_id
                          GROUP BY bt.book_id""", (id_onpage,))
    return c.fetchone()[0]


def get_tags_by_book_id_internal(db_con, id_internal):
    c = db_con.execute("""SELECT group_concat(Tags.name)
                          FROM Tags, BookTags bt, Tsumino
                          WHERE bt.book_id = Tsumino.id
                          AND Tsumino.id = ?
                          AND bt.tag_id = Tags.tag_id
                          GROUP BY bt.book_id""", (id_internal,))
    return c.fetchone()[0]

    
def dl_book_thumb(url):
    book_id = book_id_from_url(url)
    thumb_url = f"http://www.tsumino.com/Image/Thumb/{book_id}"
    try:
        urllib.request.urlretrieve(thumb_url, os.path.join("thumbs", str(book_id)))
    except urllib.request.HTTPError as err:
        logger.warning("Thumb for book with id (on page) %s couldnt be downloaded!", book_id)
        logger.warning("HTTP Error {}: {}: \"{}\"".format(err.code, err.reason, thumb_url))
        return False
    else:
        return True
        logger.info("Thumb for book with id (on page) %s downloaded successfully!", book_id)


def add_book(db_con, url, lists, write_infotxt=False):
    if write_infotxt:
        dic = create_tsubook_info(url)
    else:
        dic = get_tsubook_info(url)
    add_manga_db_entry_from_dict(db_con, url, lists, dic)
    dl_book_thumb(url)


def update_book(db_con, url, lists, write_infotxt=False):
    if write_infotxt:
        dic = create_tsubook_info(url)
    else:
        dic = get_tsubook_info(url)
    update_manga_db_entry_from_dict(db_con, url, lists, dic)


def process_job_list(db_con, jobs, write_infotxt=False):
    logger.info("Started working on list with %i items", len(jobs))
    try:
        while jobs:
            url, lists, upd = jobs.pop(0)
            logger.debug("Starting job!")
            if write_infotxt:
                dic = create_tsubook_info(url)
            else:
                dic = get_tsubook_info(url)

            if upd:
                update_manga_db_entry_from_dict(db_con, url, lists, dic)
            else:
                add_manga_db_entry_from_dict(db_con, url, lists, dic)
                dl_book_thumb(url)
            time.sleep(0.3)
    except Exception:
            # current item is alrdy removed even though it failed on it
            # join() expects list of str -> convert them first with (str(i) for i in tup)
            logger.error("Job was interrupted, items that werent processed yet were exported to resume_info.txt")
            # insert popped tuple again since it wasnt processed
            jobs.insert(0, (url, lists, upd))
            write_resume_info("resume_info.txt", jobs)
            raise


def write_resume_info(filename, info):
    info_str = "\n".join((f"{tup[0]};{','.join(tup[1])};{tup[2]}" for tup in info))

    with open(filename, "w", encoding="UTF-8") as w:
        w.write(info_str)


def resume_from_file(filename):
    with open("resume_info.txt", "r", encoding="UTF-8") as f:
        info = f.read().splitlines()

    result = []
    for ln in info:
        url, tags, upd = ln.split(";")
        upd = True if upd == "True" else False
        result.append((url, tags.split(","), upd))

    return result


cmdline_cmds = ("help", "test", "rate", "watch", "exportcsv", "remove_tags", "add_tags",
                "search_tags", "resume", "read", "downloaded", "show_tags", "update_book",
                "add_book")
def main():
    # sys.argv[0] is path to file (manga_db.py)
    cmdline = sys.argv[1:]
    if cmdline[0] == "help":
        print("""OPTIONS:    [watch] Watch clipboard for manga urls, get and write info afterwards
            [resume] Resume from crash
            [rate] url rating: Update rating for book with supplied url
            [exportcsv] Export csv-file of SQLite-DB
            [search_tags] \"tag,!exclude_tag,..\": Returns title and url of books with matching tags
            [add_book] \"tag1,tag2,..\" url (writeinfotxt): Adds book with added tags to db using url
            [update_book] \"tag1,tag2,..\" url (writeinfotxt): Updates book with added tags using url
            [add_tags] \"tag,tag,..\" url: Add tags to book
            [remove_tags] \"tag,tag,..\" url: Remove tags from book
            [read] url: Mark book as read (-> remove from li_to-read)
            [downloaded] url: Mark book as downloaded
            [show_tags] url: Display tags of book""")
    elif cmdline[0] in cmdline_cmds:
        # valid cmd -> load db
        conn, c = load_or_create_sql_db("manga_db.sqlite")

        if cmdline[0] == "test":
            #test_filter_duplicate_at_index_of_list_items()
            #print(search_tags_intersection(conn, input("Tags: ").split(",")))
            pass
            # with conn:
            #     add_tags_to_book(conn, int(input("\nBookid: ")), input("\nTags: ").split(","))
        elif cmdline[0] == "show_tags":
            print(get_tags_by_book_url(conn, cmdline[1]))
        elif cmdline[0] == "rate":
            with conn:
                rate_manga(conn, *cmdline[1:])
        elif cmdline[0] == "add_book":
            # no added tags, though unlikely for add_book
            if (cmdline[1] ==  "") or (cmdline[1] == "-"):
                lists = None
            else:
                lists = cmdline[1].split(",")

            add_book(conn, cmdline[2], lists, write_infotxt=True if len(cmdline) > 3 else False)
        elif cmdline[0] == "update_book":
            # no added tags
            if (cmdline[1] ==  "") or (cmdline[1] == "-"):
                lists = None
            else:
                lists = cmdline[1].split(",")

            update_book(conn, cmdline[2], lists, write_infotxt=True if len(cmdline) > 3 else False)
        elif cmdline[0] == "remove_tags":
            # remove_tags "tag1,tag2,tag3 tag3,.." url
            with conn:
                remove_tags_from_book(conn, cmdline[2], cmdline[1].split(","))
        elif cmdline[0] == "add_tags":
            with conn:
                add_tags_to_book_cl(conn, cmdline[2], cmdline[1].split(","))
        elif cmdline[0] == "read":
            with conn:
                remove_tags_from_book(conn, cmdline[1], ["li_to-read"])
        elif cmdline[0] == "downloaded":
            with conn:
                add_tags_to_book_cl(conn, cmdline[1], ["li_downloaded"])
        elif cmdline[0] == "search_tags":
            print("\n".join((f"{row['title_eng']}: {row['url']}" for row in search_tags_string_parse(conn, cmdline[1]))))
        elif cmdline[0] == "exportcsv":
            export_csv_from_sql("manga_db.csv", conn)
        elif cmdline[0] == "resume":
            write_infotxt = bool(input("Write info txt files? -> empty string -> No!!"))
            process_job_list(conn, resume_from_file("resume_info.txt"), write_infotxt=write_infotxt)
        elif cmdline[0] == "watch":
            write_infotxt = bool(input("Write info txt files? -> empty string -> No!!"))
            print("You can now configure the lists that all following entries should be added to!")
            fixed_list_opt = enter_manga_lists(0)

            c.execute("SELECT id_onpage FROM Tsumino")
            ids_in_db = set([tupe[0] for tupe in c.fetchall()])

            l = watch_clip_db_get_info_after(ids_in_db, fixed_lists=fixed_list_opt)
            process_job_list(conn, l, write_infotxt=write_infotxt)
    else:
        print(f"\"{cmdline[0]}\" is not a valid command! Valid commands are: {', '.join(cmdline_cmds)}")
if __name__ == "__main__":
    main()

# TODO
