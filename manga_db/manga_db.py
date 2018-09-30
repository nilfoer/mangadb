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
    DEFAULT_HEADERS = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    def __init__(self, root_dir, db_path):
        self.db_con, _ = self._load_or_create_sql_db(db_path)
        self.db_con.row_factory = sqlite3.Row
        self.root_dir = os.path.abspath(os.path.normpath(root_dir))
        self.settings = {
                # replace, keep_both, keep_old
                "duplicate_action": None
                }

    def download_cover(self, url, filename):
        # TODO use urlopen and add headers
        try:
            urllib.request.urlretrieve(url,
                                       filename)
        except urllib.request.HTTPError as err:
            logger.warning("HTTP Error %s: %s: \"%s\"",
                           err.code, err.reason, self.thumb_url)
            return False
        else:
            return True

    def import_book(self, url, lists):
        extractor_cls = extractor.find(url)
        extr = extractor_cls(url)
        book_data = extr.get_metadata()
        book = MangaDBEntry(self, extr.site_id, book_data, lists=lists)
        bid = self.get_book_id_unique((book.id_onpage, book.imported_from), book.title)
        if bid is None:
            bid = self.add_book(book)
            cover_path = os.path.join(self.root_dir, "thumbs", f"{bid}")
            # always pass headers = extr.headers?
            if self.download_cover(extr.get_cover(), cover_path):
                logger.info(
                    "Thumb for book (%s,%d) downloaded successfully!",
                    extr.site_name, book.id_onpage)
            else:
                logger.warning(
                    "Thumb for book (%s,%d) couldnt be downloaded!",
                    extr.site_name, book.id_onpage)
        else:
            logger.info("Book at '%s' will be updated to id %d", url, bid)
            # update book
            book.id = bid
            book.save()

        return bid

    def _validate_indentifiers_types(self, identifiers_types):
        if "url" in identifiers_types:
            return True
        elif "id_onpage" in identifiers_types and "imported_from" in identifiers_types:
            return True
        elif "title" in identifiers_types:
            return True
        else:
            logger.error("Unsupported identifiers supplied or identifier missing:\n"
                         "Identifiers need to be either 'url', 'id_onpage and imported_from', "
                         "or 'title(_eng)' otherwise use the search:\n%s\n", identifiers_types)
            return False

    def get_books(self, identifiers_types):
        if not self._validate_indentifiers_types(identifiers_types):
            return

        # get id_onpage and imported_from rather than using url to speed up search
        if "url" in identifiers_types:
            url = identifiers_types.pop("url")
            extractor_cls = extractor.find(url)
            bid = extractor_cls.book_id_from_url(url)
            identifiers_types["id_onpage"] = bid
            identifiers_types["imported_from"] = extractor_cls.site_id

        where_clause = " AND ".join((f"{key} = :{key}" for key in identifiers_types))
        cur = self.db_con.execute(f'SELECT * FROM Books WHERE {where_clause}',
                                  identifiers_types)
        rows = cur.fetchall()
        if not rows:
            return

        for book_info in rows:
            yield self._book_from_row(book_info)

    def get_book(self, _id):
        """Only id or title can guarantee uniqueness and querying using the title
           would be slower"""
        c = self.db_con.execute("SELECT * FROM Books WHERE id = ?", (_id,))
        book = self._book_from_row(c.fetchone())
        return book

    def _book_from_row(self, row):
        tags = get_tags_by_book(self.db_con, row["id"]).split(",")
        # split tags and lists
        lists_book = [tag for tag in tags if tag.startswith("li_")]
        tags = [tag for tag in tags if not tag.startswith("li_")]

        book = MangaDBEntry(self, row["imported_from"], row,
                            lists=lists_book, tags=tags)
        return book

    def get_book_id(self, id_onpage_site_id_tuple, title=None):
        """
        Returns internal db id(s) for book with given identifiers or None
        Title is needed to uniquely identify a book in the db since the id_onpage
        might have been replaced by a different book
        :return: List of row(s) with cols id, title"""
        c = self.db_con.execute("SELECT id, title FROM Books WHERE id_onpage = ? "
                                "AND imported_from = ?", id_onpage_site_id_tuple)
        matching = c.fetchall()
        # even if it only returns one we dont know if the id on the page got re-used
        # -> check titles
        if len(matching) > 1:
            logger.debug("Returned %d rows for %s:\n%s", len(matching),
                         id_onpage_site_id_tuple, "\n".join((t[1] for t in matching)))
        if title is None:
            return matching
        else:
            for match in matching:
                if match[1] == title:
                    return [match]
            return None

    def get_book_id_unique(self, id_onpage_site_id_tuple, title):
        """
        Returns ONE internal db id for book with given identifiers or None
        Title is needed to uniquely identify a book in the db since the id_onpage
        might have been replaced by a different book
        :return: book id"""
        c = self.db_con.execute("SELECT id, title FROM Books WHERE id_onpage = ? "
                                "AND imported_from = ?", id_onpage_site_id_tuple)
        matching = c.fetchall()
        # even if it only returns one we dont know if the id on the page got re-used
        # -> check titles
        for match in matching:
            if match[1] == title:
                return match[0]
        return None

    def add_book(self, book):
        # add/update book in db
        bid = self._add_manga_db_entry(book)
        book.id = bid
        return book

    def _add_manga_db_entry(self, manga_db_entry, duplicate_action=None):
        """Commits changes to db"""
        add_language(self.db_con, manga_db_entry.language)
        db_dict = manga_db_entry.export_for_db()
        cols = list(manga_db_entry.DB_COL_HELPER)
        # special select statement for inserting language id -> remove from list
        cols.remove("language")

        lastrowid = None
        with self.db_con:
            try:
                c = self.db_con.execute(f"""
                        INSERT INTO Books ({','.join(cols)}, language)
                        VALUES ({','.join((f':{col}' for col in cols))},
                        (SELECT id FROM Languages WHERE name = :language)
                        )""", db_dict)
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

                logger.info("Added book with url \"%s\" to database!", manga_db_entry.url)

        return lastrowid
        
    # TODO
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
        # PARSE_DECLTYPES -> parse types and search for converter function for
        # it instead of searching for converter func for specific column name
        conn = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES)
        c = conn.cursor()

        c.executescript("""
            CREATE TABLE IF NOT EXISTS Sites (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS Languages (
                     id INTEGER PRIMARY KEY ASC,
                     name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS Censorship (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS Status(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                     """)
        c.executemany("INSERT OR IGNORE INTO Sites(id, name) VALUES (?, ?)",
                      extractor.SUPPORTED_SITES)
        cen_stats = [("Unknown",), ("Censored",), ("Decensored",), ("Uncensored",)]
        c.executemany("INSERT OR IGNORE INTO Censorship(name) VALUES (?)", cen_stats)
        status = [("Unknown",), ("Ongoing",), ("Completed",), ("Unreleased",),
                  ("Hiatus",)]
        c.executemany("INSERT OR IGNORE INTO Status(name) VALUES (?)", status)

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
        c.executescript("""
            CREATE TABLE IF NOT EXISTS Books(
                    id INTEGER PRIMARY KEY ASC,
                    title TEXT UNIQUE NOT NULL,
                    title_eng TEXT UNIQUE,
                    title_foreign TEXT,
                    language_id INTEGER NOT NULL,
                    pages INTEGER NOT NULL,
                    status_id INTERGER NOT NULL,
                    my_rating REAL,
                    note TEXT,
                    last_change DATE NOT NULL,
                    favorite INTEGER NOT NULL,
                    FOREIGN KEY (language_id) REFERENCES Languages(id)
                       ON DELETE RESTRICT,
                    FOREIGN KEY (status_id) REFERENCES Status(id)
                       ON DELETE RESTRICT
                );
            CREATE TABLE IF NOT EXISTS Tags(
                    tag_id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL,
                    list_bool INTEGER NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookTags(
                    book_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, tag_id)
                 );
            CREATE TABLE IF NOT EXISTS ExternalInfo(
                    id INTEGER PRIMARY KEY ASC,
                    -- url could be built from id but idk if thats true for all sites
                    -- so keep it for now
                    url TEXT NOT NULL,
                    id_onpage INTEGER NOT NULL,
                    imported_from INTEGER NOT NULL,
                    upload_date DATE NOT NULL,
                    uploader TEXT,
                    censor_id INTEGER NOT NULL,
                    rating REAL,
                    ratings INTEGER, -- number of users that rated the book
                    favorites INTEGER,
                    downloaded INTEGER NOT NULL,
                    last_update DATE NOT NULL,
                    FOREIGN KEY (imported_from) REFERENCES Sites(id)
                       ON DELETE RESTRICT,
                    FOREIGN KEY (censor_id) REFERENCES Censorship(id)
                       ON DELETE RESTRICT
                );
            CREATE TABLE IF NOT EXISTS ExternalInfoBooks(
                    book_id INTEGER NOT NULL,
                    ext_info_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (ext_info_id) REFERENCES ExternalInfo(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, ext_info_id)
                );
            CREATE TABLE IF NOT EXISTS Collection(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookCollection(
                    book_id INTEGER NOT NULL,
                    collection_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (collection_id) REFERENCES Collection(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, collection_id)
                );

            CREATE TABLE IF NOT EXISTS Category(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookCategory(
                    book_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (category_id) REFERENCES Category(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, category_id)
                );
            -- Group protected keyword in sql
            CREATE TABLE IF NOT EXISTS Groups(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookGroups(
                    book_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES Groups(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, group_id)
                );
            CREATE TABLE IF NOT EXISTS Artist(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookArtist(
                    book_id INTEGER NOT NULL,
                    artist_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (artist_id) REFERENCES Artist(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, artist_id)
                );
            CREATE TABLE IF NOT EXISTS Parody(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookParody(
                    book_id INTEGER NOT NULL,
                    parody_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (parody_id) REFERENCES Parody(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, parody_id)
                );
            CREATE TABLE IF NOT EXISTS Character(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookCharacter(
                    book_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (character_id) REFERENCES Character(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, character_id)
                );
                 """)

        c.execute("CREATE INDEX IF NOT EXISTS id_onpage_on_site ON ExternalInfo"
                  "(id_onpage, imported_from)")

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

        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_update_ext_info
                     AFTER UPDATE ON ExternalInfo
                     BEGIN
                        UPDATE ExternalInfo
                        SET last_update = DATE('now', 'localtime')
                        WHERE id = NEW.id;
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
