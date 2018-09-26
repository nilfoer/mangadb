#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: manga_db.py
Description: Script for managing and creating a local sqilite3 manga DB
             currently supports importing from tsumino.com
"""

import time
import sys
import logging
import os
import datetime
import re
import csv
import sqlite3
import urllib.request

from logging.handlers import RotatingFileHandler

import pyperclip

from tsu_info_getter import create_tsubook_info, get_tsubook_info, ENG_TITLE_RE, is_tsu_book_url
from util import filter_duplicate_at_index_of_list_items

ROOTDIR = os.path.dirname(os.path.realpath(__file__))

logger = logging.getLogger("manga-db")
logger.setLevel(logging.DEBUG)

# create a file handler
# handler = TimedRotatingFileHandler("gwaripper.log", "D", encoding="UTF-8", backupCount=10)
# max 1MB and keep 5 files
handler = RotatingFileHandler(
    os.path.join(ROOTDIR, "tsuinfo.log"),
    maxBytes=1048576,
    backupCount=5,
    encoding="UTF-8")
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
formatterstdo = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s",
                                  "%H:%M:%S")
stdohandler.setFormatter(formatterstdo)
logger.addHandler(stdohandler)

# normal urllib user agent is being blocked by tsumino
# set user agent to use with urrlib
opener = urllib.request.build_opener()
opener.addheaders = [(
    'User-agent',
    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0')
]
# ...and install it globally so it can be used with urlretrieve/open
urllib.request.install_opener(opener)


def watch_clip_db_get_info_after(db_book_ids,
                                 fixed_lists=None,
                                 predicate=is_tsu_book_url):
    found = []
    print("Available copy cmds are: set_tags, remove_book !")
    try:
        logger.info("Watching clipboard...")
        # upd_setting -> should we update Book; upd_all -> print update prompt
        upd_setting, upd_all = None, None
        recent_value = ""
        while True:
            tmp_value = pyperclip.paste()
            if tmp_value != recent_value:
                recent_value = tmp_value
                # if predicate is met
                if predicate(recent_value):
                    logger.info("Found manga url: \"%s\"", recent_value)
                    if book_id_from_url(recent_value) in db_book_ids:
                        upd = True
                        if upd_all:
                            if upd_setting:
                                logger.info(
                                    "Book was found in db and will be updated!"
                                )
                            else:
                                logger.info(
                                    "Book was found in db and will not be updated!"
                                )
                        else:
                            logger.info("Book was found in db!")

                        if upd_setting is None or not upd_all:
                            if not found:
                                print(
                                    "Selected lists will ONLY BE ADDED, no list "
                                    "will be removed!")
                            inp_upd_setting = input(
                                "Should book in DB be updated? "
                                "y/n/all/none:\n")
                            if inp_upd_setting == "n":
                                upd_setting = False
                                print("Book will NOT be updated!")
                            elif inp_upd_setting == "all":
                                upd_setting = True
                                upd_all = True
                                print("All books will be updated!")
                            elif inp_upd_setting == "none":
                                upd_setting = False
                                upd_all = True
                                print("No books will be updated!")
                            else:
                                upd_setting = True
                                print("Book will be updated!")
                    else:
                        upd = False

                    # only append to list if were not updating or upd_setting -> True
                    if not upd or upd_setting:
                        if fixed_lists is None:
                            manga_lists = enter_manga_lists(len(found))
                            # strip urls of trailing "-" since there is a dash appended to
                            # the url when exiting from reading a manga on tsumino (compared
                            # to when entering from main site)
                            found.append((recent_value.rstrip("-"),
                                          manga_lists, upd))
                        else:
                            found.append((recent_value.rstrip("-"),
                                          fixed_lists, upd))
                elif recent_value == "set_tags":
                    url, tag_li, upd = found.pop()
                    logger.info(
                        "Setting tags for \"%s\"! Previous tags were: %s", url,
                        tag_li)
                    manga_lists = enter_manga_lists(len(found) - 1)
                    found.append((url, manga_lists, upd))
                elif recent_value == "remove_book":
                    logger.info("Deleted last book with url \"%s\" from list",
                                found[-1][0])
                    del found[-1]

            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Stopped watching clipboard!")

    # use filter_duplicate_at_index_of_list_items to only keep latest list element with same
    # urls -> index 0 in tuple
    return filter_duplicate_at_index_of_list_items(0, found)


def add_book(db_con, url, lists, write_infotxt=False, duplicate_action=None):
    if write_infotxt:
        dic = create_tsubook_info(url)
    else:
        dic = get_tsubook_info(url)
    if dic:
        # function alrdy commits changes
        id_internal = add_manga_db_entry_from_dict(db_con, url, lists, dic,
                                                   duplicate_action=duplicate_action)

        return id_internal
    else:
        return None


def update_book(db_con, url, lists, write_infotxt=False):
    if write_infotxt:
        dic = create_tsubook_info(url)
    else:
        dic = get_tsubook_info(url)
    if dic:
        return update_manga_db_entry_from_dict(db_con, url, lists, dic)
    else:
        return None, None


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

            # handle connection error or book 404
            if dic is None:
                continue

            if upd:
                update_manga_db_entry_from_dict(db_con, url, lists, dic)
            else:
                add_manga_db_entry_from_dict(db_con, url, lists, dic)
            time.sleep(0.3)
    except Exception:
        # current item is alrdy removed even though it failed on it
        # join() expects list of str -> convert them first with (str(i) for i in tup)
        logger.error(
            "Job was interrupted, items that werent processed yet were exported to resume_info.txt"
        )
        # insert popped tuple again since it wasnt processed
        jobs.insert(0, (url, lists, upd))
        write_resume_info("resume_info.txt", jobs)
        raise


def write_resume_info(filename, info):
    info_str = "\n".join(
        (f"{tup[0]};{','.join(tup[1])};{tup[2]}" for tup in info))

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


CMDLINE_CMDS = ("help", "test", "rate", "watch", "exportcsv", "remove_tags",
                "add_tags", "search_tags", "resume", "read", "downloaded",
                "show_tags", "update_book", "add_book", "search_title",
                "remove_book", "update_low_usr_count")


def main():
    # sys.argv[0] is path to file (manga_db.py)
    cmdline = sys.argv[1:]
    if cmdline[0] == "help":
        print(
            """OPTIONS:    [watch] Watch clipboard for manga urls, get and write info afterwards
            [resume] Resume from crash
            [rate] url rating: Update rating for book with supplied url
            [exportcsv] Export csv-file of SQLite-DB
            [search_tags] \"tag,!exclude_tag,..\": Returns title and url of books with matching tags
            [search_title] title: Prints title and url of books with matching title
            [add_book] \"tag1,tag2,..\" url (writeinfotxt): Adds book with added tags to db using url
            [update_book] \"tag1,tag2,..\" url (writeinfotxt): Updates book with added tags using url
            [remove_book] identifier id_type: Removes book db entry and deletes book thumb
            [update_low_usr_count] min_usr_count (write_infotxt): Updates all books on which less than min_usr_count users have voted
            [add_tags] \"tag,tag,..\" url: Add tags to book
            [remove_tags] \"tag,tag,..\" url: Remove tags from book
            [read] url: Mark book as read (-> remove from li_to-read)
            [downloaded] url: Mark book as downloaded
            [show_tags] url: Display tags of book""")
    elif cmdline[0] in CMDLINE_CMDS:
        # valid cmd -> load db
        conn, c = load_or_create_sql_db("manga_db.sqlite")

        if cmdline[0] == "test":
            # print([r["pages"] for r in search_book_by_title(conn, "FAKKU", order_by="Books.pages DESC")])
            r = search_sytnax_parser(
                conn,
                'tags:li_to-read',
                order_by="Books.rating",
                keep_row_fac=False)
            for row in r:
                print_sqlite3_row(row)
            #print(search_equals_cols_values(conn, ("artist", "Enomoto Hidehira"), ("title_eng", "Papilla Heat Up Ch 1-2"))[0]["title"])
            #print([t["title"] for t in search_like_cols_values(conn, ("title_eng", "ea"))])
            # test_filter_duplicate_at_index_of_list_items()
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
            if (cmdline[1] == "") or (cmdline[1] == "-"):
                lists = None
            else:
                lists = cmdline[1].split(",")

            add_book(
                conn,
                cmdline[2],
                lists,
                write_infotxt=True if len(cmdline) > 3 else False)
        elif cmdline[0] == "update_book":
            # no added tags
            if (cmdline[1] == "") or (cmdline[1] == "-"):
                lists = None
            else:
                lists = cmdline[1].split(",")

            update_book(
                conn,
                cmdline[2],
                lists,
                write_infotxt=True if len(cmdline) > 3 else False)
        elif cmdline[0] == "update_low_usr_count":
            rows = get_books_low_usr_count(conn, int(cmdline[1]))
            write_infotxt = len(cmdline) > 2
            for row in rows:
                update_book(
                    conn, row["url"], None, write_infotxt=write_infotxt)
        elif cmdline[0] == "remove_book":
            remove_book(conn, *cmdline[1:])
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
            print("\n".join(
                (f"{row['title_eng']}: {row['url']}"
                 for row in search_tags_string_parse(conn, cmdline[1]))))
        elif cmdline[0] == "search_title":
            print("\n".join(
                (f"{row['title_eng']}: {row['url']}"
                 for row in search_book_by_title(conn, cmdline[1]))))
        elif cmdline[0] == "exportcsv":
            export_csv_from_sql("manga_db.csv", conn)
        elif cmdline[0] == "resume":
            write_infotxt = bool(
                input("Write info txt files? -> empty string -> No!!"))
            process_job_list(
                conn,
                resume_from_file("resume_info.txt"),
                write_infotxt=write_infotxt)
        elif cmdline[0] == "watch":
            write_infotxt = bool(
                input("Write info txt files? -> empty string -> No!!"))
            print(
                "You can now configure the lists that all following entries should be added to!"
            )
            fixed_list_opt = enter_manga_lists(0)

            ids_in_db = get_all_id_onpage_set(conn)

            l = watch_clip_db_get_info_after(
                ids_in_db, fixed_lists=fixed_list_opt)
            process_job_list(conn, l, write_infotxt=write_infotxt)
    else:
        print(
            f"\"{cmdline[0]}\" is not a valid command! Valid commands are: {', '.join(CMDLINE_CMDS)}"
        )


if __name__ == "__main__":
    main()
