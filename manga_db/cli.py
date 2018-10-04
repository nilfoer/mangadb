import sys


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


def cli_yes_no(question_str):
    ans = input(f"{question_str} y/n:\n")
    while True:
        if ans == "n":
            return False
        elif ans == "y":
            return True
        else:
            ans = input(f"\"{ans}\" was not a valid answer, type in \"y\" or \"n\":\n")

lists = 
# create list with lines where one line contains 3 elements from list with corresponding
# indexes as string
# use two fstrings to first format index and value and then pad the resulting string to
# the same length
# is there a way just using one f string? -> no not without using variables, which doesnt work
# here (at least i dont think so)
DESCR = [
    " ".join([
        f"{f'[{i+n}] {LISTS[i+n]}':20}"
        for n in range(3 if (len(LISTS) - i) >= 3 else len(LISTS) - i)
    ]) for i in range(0, len(LISTS), 3)
]


# or pad index and value independently?
# DESCR = [" ".join([f"[{i+n:>2}] {LISTS[I+N]:15}" for n in range(3 if (len(LISTS)-I) >= 3 else len(LISTS)-I)]) for i in range(0, len(LISTS), 3)]
def enter_manga_lists(i):
    # only print available LISTS every fifth time
    if i % 5 == 0:
        print("\n".join(DESCR))

    while True:
        result = []
        inp = input(
            "Enter indexes (displayed in [i]) of lists the manga should be in seperated "
            "by commas:\n"
        )
        if inp:
            for ind in inp.split(","):
                try:
                    lname = LISTS[int(ind)]
                    result.append(lname)
                # (Error1, Erro2) is needed to except multiple exceptions in one except statement
                except (ValueError, IndexError):
                    logger.error(
                        "\"%s\" was not a valid list index, please re-enter list indexes",
                        ind)
                    break
            # keep looping (while) till all list names are recognized -> for doesnt break -> return
            else:
                logger.info("The following lists were selected %s", result)
                return result
        else:
            logger.info("No lists were selected!")
            # no input -> dont add to any lists
            return None
