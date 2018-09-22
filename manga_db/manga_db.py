import sqlite3

from .manga import MangaDBEntry


class MangaDB:
    HANDLE_DUPLICATE_BOOK_ACTIONS = ("replace", "keep_both", "keep_old")

    def __init__(self, db_path):
        self.db_con = self._load_or_create_sql_db(db_path)
        self.settings = {
                # replace, keep_both, keep_old
                "duplicate_action": None
                }

    def import_book(self, url):
        pass

    def get_book(self, identifier, id_type):
        if id_type == "id":
            id_col = "id"
            id_type_db = "id_internal"
        elif id_type == "onpage":
            id_col = "id_onpage"
            id_type_db = "id_onpage"
        elif id_type == "url":
            # TODO
            pass
        else:
            logger.error("%s is an unsupported identifier type!", id_type)
            return
        cur = db_con.execute(f'select * from Tsumino WHERE {id_col} = ?',
                             (identifier, ))
        book_info = cur.fetchone()
        if not book_info:
            return

        tags = get_tags_by_book(db_con, identifier, id_type_db).split(",")
        # split tags and lists
        lists_book = [tag for tag in tags if tag.startswith("li_")]
        tags = [tag for tag in tags if not tag.startswith("li_")]

        book = MangaDBEntry(self, book_info["imported_from"], book_info)
        return book

    @staticmethod
    def _load_or_create_sql_db(filename):
        """
        Creates connection to sqlite3 db and a cursor object. Creates the table+file if it
        doesnt exist yet.

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
                     imported_from TEXT,
                     last_change DATE NOT NULL,
                     downloaded INTEGER,
                     favorite INTEGER)""")

        # create index for id_onpage so we SQLite can access it with O(log n) instead of O(n)
        # complexit when using WHERE id_onpage = ? (same exists for PRIMARY KEY)
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS book_id_onpage ON Tsumino (id_onpage)"
        )

        # was using AUTO_INCREMENT here but it wasnt working (tag_id remained NULL)
        # SQLite recommends that you should not use AUTOINCREMENT attribute because:
        # The AUTOINCREMENT keyword imposes extra CPU, memory, disk space, and disk I/O overhead
        # and should be avoided if not strictly needed. It is usually not needed.
        # (comment Moe: --> PRIMARY KEY implies AUTOINCREMENT)
        # In addition, the way SQLite assigns a value for the AUTOINCREMENT column is slightly
        # different from the way it used for rowid column. -> wont reuse unused ints when
        # max nr(9223372036854775807; signed 64bit) is used -> error db full
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
        # ON DELETE CASCADE, wenn der eintrag des FK in der primärtabelle gelöscht wird dann auch
        # in dieser (detailtabelle) die einträge löschen -> Löschweitergabe
        c.execute("""CREATE TABLE IF NOT EXISTS BookTags(
                     book_id INTEGER NOT NULL,
                     tag_id INTEGER NOT NULL,
                     FOREIGN KEY (book_id) REFERENCES Tsumino(id)
                     ON DELETE CASCADE,
                     FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
                     ON DELETE CASCADE,
                     PRIMARY KEY (book_id, tag_id))""")

        # trigger that gets executed everytime after a row is updated in Tsumino table
        # with UPDATE -> old and new values of cols accessible with OLD.colname NEW.colname
        # WHERE id = NEW.id is needed otherwise whole col in table gets set to that value
        # set last_change to current DATE on update of any col in Tsumino gets updated
        # could limit to certain rows with WHEN condition (AFTER UPDATE ON table WHEN..)
        # by checking if old and new val for col differ OLD.colname <> NEW.colname
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tsumino
                     AFTER UPDATE ON Tsumino
                     BEGIN
                        UPDATE Tsumino
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = NEW.id;
                     END""")

        # set last_change on Tsumino when new tags get added in bridge table
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tags_ins
                     AFTER INSERT ON BookTags
                     BEGIN
                        UPDATE Tsumino
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = NEW.book_id;
                     END""")

        # set last_change on Tsumino when tags get removed in bridge table
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tags_del
                     AFTER DELETE ON BookTags
                     BEGIN
                        UPDATE Tsumino
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = OLD.book_id;
                     END""")

        # also do this the other way around -> if downloaded get set also add "li_downloaded" to tags?
        # set downloaded to 1 if book gets added to li_downloaded
        c.execute("""CREATE TRIGGER IF NOT EXISTS update_downloaded_on_tags_insert
                     AFTER INSERT ON BookTags
                                     WHEN NEW.tag_id IN (
                                     SELECT tag_id FROM Tags WHERE name = 'li_downloaded')
                     BEGIN
                        UPDATE Tsumino
                        SET downloaded = 1
                        WHERE id = NEW.book_id;
                     END""")

        # set downloaded to 0 if book gets removed from li_downloaded
        c.execute("""CREATE TRIGGER IF NOT EXISTS update_downloaded_on_tags_delete
                     AFTER DELETE ON BookTags
                                     WHEN OLD.tag_id IN (
                                     SELECT tag_id FROM Tags WHERE name = 'li_downloaded')
                     BEGIN
                        UPDATE Tsumino
                        SET downloaded = 0
                        WHERE id = OLD.book_id;
                     END""")

        # set favorite to 1 if book gets added to li_best
        c.execute("""CREATE TRIGGER IF NOT EXISTS update_favorite_on_tags_insert
                     AFTER INSERT ON BookTags
                                     WHEN NEW.tag_id IN (
                                     SELECT tag_id FROM Tags WHERE name = 'li_best')
                     BEGIN
                        UPDATE Tsumino
                        SET favorite = 1
                        WHERE id = NEW.book_id;
                     END""")

        # set favorite to 0 if book gets removed from li_best
        c.execute("""CREATE TRIGGER IF NOT EXISTS update_favorite_on_tags_delete
                     AFTER DELETE ON BookTags
                                     WHEN OLD.tag_id IN (
                                     SELECT tag_id FROM Tags WHERE name = 'li_best')
                     BEGIN
                        UPDATE Tsumino
                        SET favorite = 0
                        WHERE id = OLD.book_id;
                     END""")

        # commit changes
        conn.commit()

        return conn, c

    # TODO
    def _add_manga_db_entry(self, url, lists, dic, duplicate_action=None):
        """Commits changes to db"""
        book = MangaDBEntry(imported_from, dic)
        if lists:
            dic["downloaded"] = 1 if "li_downloaded" in lists else 0
            dic["favorite"] = 1 if "li_best" in lists else 0
        else:
            dic["downloaded"] = 0
            dic["favorite"] = 0

        lastrowid = None
        with self.db_con:
            try:
                c = self.db_con.execute(
                    "INSERT INTO Tsumino (title, title_eng, url, id_onpage, upload_date, "
                    "uploader, pages, rating, rating_full, category, collection, groups, "
                    "artist, parody, character, imported_from, last_change, downloaded, "
                    "favorite) "
                    "VALUES (:title, :title_eng, :url, :id_onpage, :upload_date, :uploader, "
                    ":pages, :rating, :rating_full, :category, :collection, "
                    ":groups, :artist, :parody, :character, :imported_from, :last_change, "
                    ":downloaded, :favorite)", dic)
            except sqlite3.IntegrityError as error:
                error_msg = str(error)
                if "UNIQUE constraint failed" in error_msg:
                    failed_col = error_msg.split(".")[-1]
                    logger.info("Tried to add book with %s that was already in DB: %s",
                                failed_col, dic[failed_col])
                    lastrowid = handle_book_not_unique(self.db_con, failed_col, url, lists, dic, action=duplicate_action)
                else:
                    # were only handling unique constraint fail so reraise if its sth else
                    raise error
            else:
                lastrowid = c.lastrowid
                # workaround to make concatenation work
                if lists is None:
                    lists = []
                # use cursor.lastrowid to get id of last insert in Tsumino table
                add_tags_to_book(self.db_con, lastrowid, lists + dic["Tag"])

                # handle_book_not_unique also handles downloading book thumb in that case
                dl_book_thumb(url)

                logger.info("Added book with url \"%s\" to database!", url)

        return lastrowid
        

    def _handle_book_not_unique(db_con, duplicate_col, url, lists, dic, action=None):
        """Only partly commits changes where it calls add_manga or update_manga"""
        # @Cleanup ^^
        # doing this several times @Hack
        prepared_dic = prepare_dict_for_db(url, dic)

        # webGUI cant do input -> use default None and set if None
        if action is None:
            # options: replace(==keep_new), keep_both, keep_old
            while True:
                action_i = input("Choose the action for handling duplicate "
                                f"book {prepared_dic['title_eng']}:\n"
                                 "(0) replace, (1) keep_both, (2) keep_old: ")
                try:
                    action = HANDLE_DUPLICATE_BOOK_ACTIONS[int(action_i)]
                except ValueError:
                    print("Not a valid index!!")
                else:
                    break


        # @Incomplete just replacing most recent one if action keep_both was used before
        c = db_con.execute(f"SELECT id, id_onpage, my_rating, title FROM Tsumino WHERE {duplicate_col} = ?",
                          (prepared_dic[duplicate_col],))
        row = c.fetchall()
        assert(len(row) == 1)
        old_id_internal, old_id_onpage, my_rating, old_title = row[0]

        id_internal = None
        if action == "keep_old":
            logger.info("Kept old book with id_onpage: %s", old_id_onpage)
            # return None here so we know when no action was taken
            return id_internal

        if action == "replace":
            logger.info("Replacing book with id_onpage %s. Everything but the lists (only downloaded will be modified -> new lists wont be added!) will be replaced!", old_id_onpage)
            # only add/remove list downloaded
            li_downloaded = None
            if lists and ("li_downloaded" in lists):
                li_downloaded = ["li_downloaded"]
            else:
                remove_tags_from_book_id(db_con, old_id_internal, ["li_downloaded"])

            # since update_manga_db_entry_from_dict tries to query for id using id_onpage we have to update id_onpage maunally first @Hack @Cleanup
            # also update url since update.. doesnt @Hack
            new_id_onpage = book_id_from_url(url)
            db_con.execute("UPDATE Tsumino SET id_onpage = ?, url = ? WHERE id = ?",
                          (new_id_onpage, url, old_id_internal))
            update_manga_db_entry_from_dict(db_con, url, li_downloaded, dic)

            # also delete book thumb
            os.remove(os.path.join("thumbs", str(old_id_onpage)))
            logger.debug("Removed thumb with path %s", f"thumbs/{old_id_onpage}")

            id_internal = old_id_internal
        elif action == "keep_both":
            i = 1
            while True:
                try:
                    # change title of old book
                    old_title_dupe = f"{old_title} (DUPLICATE {i})"
                    db_con.execute("UPDATE Tsumino SET title = ? WHERE id = ?", (old_title_dupe,
                                   old_id_internal))
                except sqlite3.IntegrityError as error:
                    error_msg = str(error)
                    if "UNIQUE constraint failed" not in error_msg:
                        # were only handling unique constraint fail so reraise if its sth else
                        raise error
                    i += 1
                else:
                    break
            logger.info("Keeping both books, renamed old version to: %s", old_title_dupe)

            id_internal = add_manga_db_entry_from_dict(db_con, url, lists, dic)

        # in both cases (replace and keep_both) use old rating on newly added book
        rate_manga(db_con, url, my_rating)

        # dl new thumb also for both cases
        dl_book_thumb(url)

        return id_internal


    def _update_manga_db_entry_from_dict(db_con, url, lists, dic):
        """Commits changes to db,
        lists will ONLY be ADDED not removed"""
        book_id = book_id_from_url(url)

        c = db_con.execute("SELECT id FROM Tsumino WHERE id_onpage = ?",
                           (book_id, ))
        # lists from db is string "list1, list2, .."
        id_internal = c.fetchone()[0]

        update_dic = prepare_dict_for_db(url, dic)

        # get previous value for downloaded and fav from db
        c = db_con.execute(
            "SELECT downloaded, favorite FROM Tsumino WHERE id_onpage = ?",
            (book_id, ))
        downloaded, favorite = c.fetchone()
        if lists:
            # if there are lists -> set dled/fav to 1 if appropriate list is in lists else
            # use value from db (since lists just contains lists to ADD)
            update_dic["downloaded"] = 1 if "li_downloaded" in lists else downloaded
            update_dic["favorite"] = 1 if "li_best" in lists else favorite
        else:
            # no lists to add to -> use values from db
            update_dic["downloaded"] = downloaded
            update_dic["favorite"] = favorite

        # seems like book id on tsumino just gets replaced with newer uncensored or fixed version
        # -> check if upload_date uploader pages or tags (esp. uncensored + decensored) changed
        # => WARN to redownload book
        c.execute(
            "SELECT uploader, upload_date, pages FROM Tsumino WHERE id_onpage = ?",
            (book_id, ))
        res_tuple = c.fetchone()

        field_change_str = []
        # build line str of changed fields
        for res_tuple_i, key in ((0, "uploader"), (1, "upload_date"), (2,
                                                                       "pages")):
            if res_tuple[res_tuple_i] != update_dic[key]:
                field_change_str.append(
                    f"Field \"{key}\" changed from \"{res_tuple[res_tuple_i]}\" "
                    f"to \"{update_dic[key]}\"!"
                )

        # check tags seperately due to using bridge table
        # get column tag names where tag_id in BookTags and Tags match and book_id in BookTags
        # is the book were looking for
        c.execute("""SELECT Tags.name
                     FROM BookTags bt, Tags
                     WHERE bt.tag_id = Tags.tag_id
                     AND bt.book_id = ?""", (id_internal, ))
        # filter lists from tags first
        tags = set(
            (tup[0] for tup in c.fetchall() if not tup[0].startswith("li_")))
        tags_page = set(dic["Tag"])
        added_tags = None
        removed_on_page = None
        # compare sorted to see if tags changed, alternatively convert to set and add -> see
        # if len() changed
        if tags != tags_page:
            added_tags = tags_page - tags
            removed_on_page = tags - tags_page
            field_change_str.append(
                f"Field \"tags\" changed -> Added Tags: \"{', '.join(added_tags)}\"; "
                f"Removed Tags: \"{', '.join(removed_on_page)}\"!"
            )

        if field_change_str:
            field_change_str = '\n'.join(field_change_str)
            logger.warning(
                f"Please re-download \"{url}\", since the change of following fields suggest "
                f"that someone has uploaded a new version:\n{field_change_str}"
            )

        with db_con:
            # dont update: title = :title, title_eng = :title_eng,
            c.execute("""UPDATE Tsumino SET
                         upload_date = :upload_date, uploader = :uploader, pages = :pages,
                         rating = :rating, rating_full = :rating_full, category = :category,
                         collection = :collection, groups = :groups, artist = :artist,
                         parody = :parody, character = :character, imported_from = :imported_from,
                         last_change = :last_change, downloaded = :downloaded, favorite = :favorite
                         WHERE id_onpage = :id_onpage""", update_dic)

            if removed_on_page:
                # remove tags that are still present in db but were removed on page
                remove_tags_from_book(db_con, url, removed_on_page)

            tags_lists_to_add = []
            if lists:
                # (micro optimization i know) list concat is faster with + compared with extend
                tags_lists_to_add = tags_lists_to_add + lists
            if added_tags:
                # converting set to list and then concat is faster than using s.union(list)
                tags_lists_to_add = tags_lists_to_add + list(added_tags)

            if tags_lists_to_add:
                # WARNING lists will only be added, not removed
                add_tags_to_book(db_con, id_internal, tags_lists_to_add)

            logger.info("Updated book with url \"%s\" in database!", url)

        # c.lastrowid only works for INSERT/REPLACE
        return id_internal, field_change_str
