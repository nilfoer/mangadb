import os
import logging
import sqlite3
import urllib.request

from . import extractor
from .manga import MangaDBEntry
from .db.tags import get_tags_by_book, add_tags_to_book
from .db.mixed_queries import add_language


logger = logging.getLogger(__name__)

# normal urllib user agent is being blocked by tsumino
# set user agent to use with urrlib
opener = urllib.request.build_opener()
opener.addheaders = [(
    'User-agent',
    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0')
]
# ...and install it globally so it can be used with urlretrieve/open
urllib.request.install_opener(opener)


class MangaDB:
    HANDLE_DUPLICATE_BOOK_ACTIONS = ("replace", "keep_both", "keep_old")

    def __init__(self, root_dir, db_path):
        self.db_con, _ = self._load_or_create_sql_db(db_path)
        self.db_con.row_factory = sqlite3.Row
        self.root_dir = os.path.abspath(os.path.normpath(root_dir))
        self.settings = {
                # replace, keep_both, keep_old
                "duplicate_action": None
                }

    def import_book(self, url, lists):
        extractor_cls = extractor.find(url)
        extr = extractor_cls(url)
        book_data = extr.get_metadata()
        extr.get_cover()
        book = MangaDBEntry(self, extr.site_id, book_data, lists=lists)
        # TODO add or update?
        return self.add_book(book)

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
        cur = self.db_con.execute(f'select * from Books WHERE {id_col} = ?',
                                  (identifier, ))
        book_info = cur.fetchone()
        if not book_info:
            return

        tags = get_tags_by_book(self.db_con, identifier, id_type_db).split(",")
        # split tags and lists
        lists_book = [tag for tag in tags if tag.startswith("li_")]
        tags = [tag for tag in tags if not tag.startswith("li_")]

        book = MangaDBEntry(self, book_info["imported_from"], book_info,
                            lists=lists_book, tags=tags)
        return book

    def add_book(self, book):
        # add/update book in db
        # TODO move to MangaDBEntry class?
        bid = self._add_manga_db_entry(book)
        book.id = bid
        return book

    # TODO
    def _add_manga_db_entry(self, manga_db_entry, duplicate_action=None):
        """Commits changes to db"""
        add_language(self.db_con, manga_db_entry.language)
        db_dict = manga_db_entry.export_for_db()
        lastrowid = None
        with self.db_con:
            try:
                c = self.db_con.execute("""
                    INSERT INTO Books (title, title_eng, title_foreign, url,
                    id_onpage, upload_date, uploader, pages, rating,
                    rating_full, my_rating, category, collection, 
                    groups, artist, parody, character, imported_from,
                    last_change, downloaded, favorite, language)
                    VALUES (:title, :title_eng, :title_foreign, :url, :id_onpage,
                    :upload_date, :uploader, :pages, :rating, :rating_full,
                    :my_rating, :category, :collection, :groups, :artist,
                    :parody, :character, :imported_from, :last_change,
                    :downloaded, :favorite,
                    (SELECT id FROM Languages WHERE name = :language)""", db_dict)
            except sqlite3.IntegrityError as error:
                error_msg = str(error)
                if "UNIQUE constraint failed" in error_msg:
                    failed_col = error_msg.split(".")[-1]
                    logger.info("Tried to add book with %s that was already in DB: %s",
                                failed_col, db_dict[failed_col])
                    lastrowid = self._handle_book_not_unique(self.db_con,
                                                             failed_col, manga_db_entry,
                                                             action=duplicate_action)
                else:
                    # were only handling unique constraint fail so reraise if its sth else
                    raise error
            else:
                lastrowid = c.lastrowid
                # use cursor.lastrowid to get id of last insert in Books table
                add_tags_to_book(self.db_con, lastrowid, manga_db_entry.lists +
                                 manga_db_entry.tags)

                # handle_book_not_unique also handles downloading book thumb in that case
                # TODO where should i dl the cover
                # manga_db_entry.get_cover()

                logger.info("Added book with url \"%s\" to database!", manga_db_entry.url)

        return lastrowid
        
    def _handle_book_not_unique(self, duplicate_col, manga_db_entry, lists, action=None):
        """Only partly commits changes where it calls add_manga or update_manga"""
        # webGUI cant do input -> use default None and set if None
        if action is None:
            # options: replace(==keep_new), keep_both, keep_old
            while True:
                action_i = input("Choose the action for handling duplicate "
                                f"book {prepared_dic['title_eng']}:\n"
                                 "(0) replace, (1) keep_both, (2) keep_old: ")
                try:
                    action = self.HANDLE_DUPLICATE_BOOK_ACTIONS[int(action_i)]
                except ValueError:
                    print("Not a valid index!!")
                else:
                    break


        # @Incomplete just replacing most recent one if action keep_both was used before
        c = db_con.execute(f"SELECT id, id_onpage, imported_from, my_rating, title"
                            "FROM Books WHERE {duplicate_col} = ?",
                            (prepared_dic[duplicate_col],))
        row = c.fetchall()
        assert(len(row) == 1)
        old_id_internal, old_id_onpage, old_imported_from, my_rating, old_title = row[0]

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
                remove_tags_from_book_id(self.db_con, old_id_internal, ["li_downloaded"])

            # since update_manga_db_entry_from_dict tries to query for id using id_onpage we have to update id_onpage maunally first @Hack @Cleanup
            # also update url since update.. doesnt @Hack
            new_id_onpage = book_id_from_url(url)
            db_con.execute("UPDATE Books SET id_onpage = ?, url = ? WHERE id = ?",
                          (new_id_onpage, url, old_id_internal))
            update_manga_db_entry_from_dict(db_con, url, li_downloaded, dic)

            # also delete book thumb
            os.remove(os.path.join("thumbs", f"{old_imported_from}_{old_id_onpage}"))
            logger.debug("Removed thumb with path %s", f"thumbs/{old_id_onpage}")

            id_internal = old_id_internal
        elif action == "keep_both":
            i = 1
            while True:
                try:
                    # change title of old book
                    old_title_dupe = f"{old_title} (DUPLICATE {i})"
                    db_con.execute("UPDATE Books SET title = ? WHERE id = ?", (old_title_dupe,
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

    def get_all_id_onpage_set(self):
        c = self.db_con.execute("SELECT id_onpage FROM Books")
        return set([tupe[0] for tupe in c.fetchall()])

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

        c.execute("""CREATE TABLE IF NOT EXISTS Sites (
                     id INTEGER PRIMARY KEY ASC,
                     name TEXT UNIQUE NOT NULL)""")
        # insert supported sites
        c.executemany("INSERT OR IGNORE INTO Sites(id, name) VALUES (?, ?)",
                      extractor.SUPPORTED_SITES)

        # creat languages table
        c.execute("""CREATE TABLE IF NOT EXISTS Languages (
                     id INTEGER PRIMARY KEY ASC,
                     name TEXT UNIQUE NOT NULL)""")

        # create table if it doesnt exist
        # group reserved keyword -> use groups for col name
        # SQLite does not have a separate Boolean -> stored as integers 0 (false) and 1 (true).
        # FOREIGN KEY ON DEL/UPD RESTRICT disallows deleting/modifying parent
        # key if it has child key(s)
        # title_foreign cant be UNIQUE since some uploads on tsumino had the same asian title
        # but a different english title/ were a different book; mb because theyre chapters of
        # a larger book?
        # for now lets assume the english title is always unique (at least it has been for now for
        # over 2k books), the alternative would be to only leave title UNIQUE and (which i have to
        # do anyway) always have the title as english-title / foreign-title -- this may be the better
        # approach anyway
        c.execute("""CREATE TABLE IF NOT EXISTS Books (
                     id INTEGER PRIMARY KEY ASC,
                     title TEXT UNIQUE NOT NULL,
                     title_eng TEXT UNIQUE,
                     title_foreign TEXT,
                     url TEXT UNIQUE NOT NULL,
                     id_onpage INTEGER NOT NULL,
                     imported_from INTEGER NOT NULL,
                     upload_date DATE NOT NULL,
                     uploader TEXT,
                     language INTEGER NOT NULL,
                     pages INTEGER NOT NULL,
                     rating REAL,
                     rating_full TEXT,
                     my_rating REAL,
                     category TEXT,
                     collection TEXT,
                     groups TEXT,
                     artist TEXT,
                     parody TEXT,
                     character TEXT,
                     note TEXT,
                     last_change DATE NOT NULL,
                     downloaded INTEGER NOT NULL,
                     favorite INTEGER NOT NULL,
                     FOREIGN KEY (imported_from) REFERENCES Sites(id)
                        ON DELETE RESTRICT,
                     FOREIGN KEY (language) REFERENCES Languages(id)
                        ON DELETE RESTRICT
                    )""")

        # create index for imported_from,id_onpage so we SQLite can access it
        # with O(log n) instead of O(n) complexit when using WHERE id_onpage = ?
        # (same exists for PRIMARY KEY) but using rowid/PK INTEGER ASC is still faster
        # order is important for composite key index
        # To utilize a multicolumn index, the query must contain the condition
        # that has the same column order as defined in the index
        # querying by just imported_from will work or imported_from,id_onpage
        # but just id_onpage wont work
        # by making index unique we get an error if we want to insert values
        # for imported_from,id_onpage that are already in the table as the same combo
        # TODO but from sqlite.org: The left-most column is the primary key
        # used for ordering the rows in the index. The second column is used to
        # break ties in the left-most column. If there were a third column, it
        # would be used to break ties for the first two columns
        # -> more sense to have id_onpage since it will have few cases where there
        # are still duplicates left whereas imported_from will have TONS
        # but then i cant sort by site having the speed bonus of the index only
        # id_onpage alone would work which is of no use
        c.execute(
            "CREATE INDEX IF NOT EXISTS id_onpage_on_site ON Books (id_onpage, imported_from)"
        )
        # TODO cant rely on id_onpage,imported_from always being unique since
        # e.g. tsumino reuses old, unused ids, so i'd have to update
        # this id by searching for the title or let id_onpage be NULL

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

        # foreign key book_id is linked to id column in Books table
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
                     FOREIGN KEY (book_id) REFERENCES Books(id)
                     ON DELETE CASCADE,
                     FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
                     ON DELETE CASCADE,
                     PRIMARY KEY (book_id, tag_id))""")

        # trigger that gets executed everytime after a row is updated in Books table
        # with UPDATE -> old and new values of cols accessible with OLD.colname NEW.colname
        # WHERE id = NEW.id is needed otherwise whole col in table gets set to that value
        # set last_change to current DATE on update of any col in Books gets updated
        # could limit to certain rows with WHEN condition (AFTER UPDATE ON table WHEN..)
        # by checking if old and new val for col differ OLD.colname <> NEW.colname
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_books
                     AFTER UPDATE ON Books
                     BEGIN
                        UPDATE Books
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = NEW.id;
                     END""")

        # set last_change on Books when new tags get added in bridge table
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tags_ins
                     AFTER INSERT ON BookTags
                     BEGIN
                        UPDATE Books
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = NEW.book_id;
                     END""")

        # set last_change on Books when tags get removed in bridge table
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tags_del
                     AFTER DELETE ON BookTags
                     BEGIN
                        UPDATE Books
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
                        UPDATE Books
                        SET downloaded = 1
                        WHERE id = NEW.book_id;
                     END""")

        # set downloaded to 0 if book gets removed from li_downloaded
        c.execute("""CREATE TRIGGER IF NOT EXISTS update_downloaded_on_tags_delete
                     AFTER DELETE ON BookTags
                                     WHEN OLD.tag_id IN (
                                     SELECT tag_id FROM Tags WHERE name = 'li_downloaded')
                     BEGIN
                        UPDATE Books
                        SET downloaded = 0
                        WHERE id = OLD.book_id;
                     END""")

        # set favorite to 1 if book gets added to li_best
        c.execute("""CREATE TRIGGER IF NOT EXISTS update_favorite_on_tags_insert
                     AFTER INSERT ON BookTags
                                     WHEN NEW.tag_id IN (
                                     SELECT tag_id FROM Tags WHERE name = 'li_best')
                     BEGIN
                        UPDATE Books
                        SET favorite = 1
                        WHERE id = NEW.book_id;
                     END""")

        # set favorite to 0 if book gets removed from li_best
        c.execute("""CREATE TRIGGER IF NOT EXISTS update_favorite_on_tags_delete
                     AFTER DELETE ON BookTags
                                     WHEN OLD.tag_id IN (
                                     SELECT tag_id FROM Tags WHERE name = 'li_best')
                     BEGIN
                        UPDATE Books
                        SET favorite = 0
                        WHERE id = OLD.book_id;
                     END""")

        # commit changes
        conn.commit()

        return conn, c
