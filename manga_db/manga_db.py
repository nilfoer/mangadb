import os
import logging
import sqlite3
import urllib.request

from . import extractor
from .manga import MangaDBEntry
from .ext_info import ExternalInfo


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
    DEFAULT_HEADERS = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    def __init__(self, root_dir, db_path, settings=None):
        self.db_con, _ = self._load_or_create_sql_db(db_path)
        self.db_con.row_factory = sqlite3.Row
        self.root_dir = os.path.abspath(os.path.normpath(root_dir))
        self.language_map = self._get_language_map()
        self.settings = {
                # replace, keep_both, keep_old
                "duplicate_action": None
                }
        if settings is not None:
            self.settings.update(settings)

    # __enter__ should return an object that is assigned to the variable after
    # as. By default it is None, and is optional. A common pattern is to return
    # self and keep the functionality required within the same class.
    # __exit__ is called on the original Context Manager object, not the object
    # returned by __enter__.
    # If an error is raised in __init__ or __enter__ then the code block is
    # never executed and __exit__ is not called.
    # Once the code block is entered, __exit__ is always called, even if an
    # exception is raised in the code block.
    # If __exit__ returns True, the exception is suppressed. and exit
    def __enter__(self):
        return self

    def __exit__(self):
        self.close()

    def close(self):
        self.db_con.close()

    def _get_language_map(self):
        c = self.db_con.execute("SELECT id, name FROM Languages")
        result = {}
        for row in c.fetchall():
            result[row["id"]] = row["name"]
            result[row["name"]] = row["id"]
        return result

    # used in extractor to get language id if language isnt in db itll be added
    def add_language(self, language):
        if language not in self.language_map:
            with self.db_con:
                c = self.db_con.execute("INSERT OR IGNORE INTO Languages (name) VALUES (?)",
                                        (language,))
            if c.lastrowid:
                self.language_map[language] = c.lastrowid
                self.language_map[c.lastrowid] = language
            return c.lastrowid
        else:
            return self.language_map[language]

    def fetch_list_names(self):
        c = self.db_con.execute("SELECT name FROM List")
        result = c.fetchall()
        return result if result else None

    def download_cover(self, url, filename, overwrite=False):
        # TODO use urlopen and add headers
        if not os.path.isfile(filename) or overwrite:
            try:
                urllib.request.urlretrieve(url,
                                           filename)
            except urllib.request.HTTPError as err:
                logger.warning("HTTP Error %s: %s: \"%s\"",
                               err.code, err.reason, self.thumb_url)
                return False
            else:
                return True
        else:
            logger.debug("Thumb at '%s' was skipped since the path already exists: '%s'",
                         url, filename)
            return None

    def retrieve_book_data(self, url, lists):
        extractor_cls = extractor.find(url)
        extr = extractor_cls(self, url)
        data = extr.get_metadata()
        # add lists to data since add/remove methods on MangaDBEntry are for updating
        # not for initializing/adding to db
        data.update({"list": lists})
        book = MangaDBEntry(self, data)
        ext_info = ExternalInfo(book, data)
        book.ext_infos = [ext_info]
        return book, extr.get_cover()

    def import_book(self, url=None, lists=None, book=None, thumb_url=None):
        """
        Imports book into DB and downloads cover
        Either url and lists or book and thumb_url has to be supplied
        """
        thumb_url = thumb_url
        if url and lists is not None:
            book, thumb_url = self.retrieve_book_data(url, lists)
        elif book and thumb_url:
            book = book
        else:
            logger.error("Either url and lists or book and thumb_url have to be supplied")
            return None, None

        bid = self.get_book_id(book.title)
        if bid is None:
            bid, _ = book.save()
            cover_path = os.path.join(self.root_dir, "thumbs", f"{book.id}")
            # always pass headers = extr.headers?
            if self.download_cover(thumb_url, cover_path):
                logger.info("Thumb for book %s downloaded successfully!", book.title)
            else:
                logger.warning("Thumb for book %s couldnt be downloaded!", book.title)
        else:
            logger.info("Book at url '%s' was already in DB!")

        return bid, book

    def get_x_books(self, x, offset=None):
        c = self.db_con.execute(f"SELECT * FROM Books LIMIT {x} "
                                f"{f'OFFSET {offset}' if offset is not None else ''}")
        rows = c.fetchall()
        if rows:
            return [MangaDBEntry(self, row) for row in rows]
        else:
            return None

    def _validate_indentifiers_types(self, identifiers_types):
        if "url" in identifiers_types:
            return True
        elif "id_onpage" in identifiers_types and "imported_from" in identifiers_types:
            return True
        elif "title" in identifiers_types:
            return True
        elif "id" in identifiers_types:
            return True
        else:
            logger.error("Unsupported identifiers supplied or identifier missing:\n"
                         "Identifiers need to be either 'url', 'id_onpage and imported_from', "
                         "id or 'title(_eng)' otherwise use the search:\n%s\n",
                         identifiers_types)
            return False

    def get_books(self, identifiers_types):
        if not self._validate_indentifiers_types(identifiers_types):
            return

        if "id" in identifiers_types:
            return self.get_book(identifiers_types["id"])
        elif "title" in identifiers_types:
            return self.get_book(title=identifiers_types["title"])
        # get id_onpage and imported_from rather than using url to speed up search
        elif "url" in identifiers_types:
            url = identifiers_types.pop("url")
            extractor_cls = extractor.find(url)
            bid = extractor_cls.book_id_from_url(url)
            identifiers_types["id_onpage"] = bid
            identifiers_types["imported_from"] = extractor_cls.site_id

        cur = self.db_con.execute(f"""
                    SELECT Books.*
                    FROM Books, ExternalInfo ei, ExternalInfoBooks eib
                    WHERE ei.id_onpage = :id_onpage
                    AND ei.imported_from = :imported_from
                    AND ei.id = eib.ext_info_id
                    AND Books.id = eib.book_id""", identifiers_types)
        rows = cur.fetchall()
        if not rows:
            return

        for book_info in rows:
            yield MangaDBEntry(self, book_info)

    def get_book(self, _id=None, title=None):
        """Only id or title can guarantee uniqueness and querying using the title
           would be slower"""
        if _id:
            c = self.db_con.execute("SELECT * FROM Books WHERE id = ?", (_id,))
        elif title:
            c = self.db_con.execute("SELECT * FROM Books WHERE title = ?", (title,))
        else:
            logger.error("At least one of id or title needs to be supplied!")

        row = c.fetchone()
        return MangaDBEntry(self, row) if row else None

    def get_book_id(self, title):
        """
        Returns internal db id for book with given title or None
        """
        c = self.db_con.execute("SELECT id FROM Books WHERE title = ?", (title,))
        _id = c.fetchone()
        return _id[0] if _id else None
        
    def get_collection_info(self, name, order_by="id ASC"):
        c = self.db_con.execute(f"""
                SELECT b.id, b.title, b.pages, b.my_rating
                FROM Books b, Collection c, BookCollection bc
                WHERE bc.collection_id = c.id
                AND c.name = ?
                AND b.id = bc.book_id
                ORDER BY b.{order_by}""", (name,))
        rows = c.fetchall()
        return rows if rows else None
                                    
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
                      [(key, val) for key, val in extractor.SUPPORTED_SITES.items()
                       if isinstance(key, int)])
        c.execute("INSERT OR IGNORE INTO Languages(name) VALUES (?)", ("English",))
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
            CREATE TABLE IF NOT EXISTS List(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookList(
                    book_id INTEGER NOT NULL,
                    list_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (list_id) REFERENCES List(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, list_id)
                );
            CREATE TABLE IF NOT EXISTS Tag(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE IF NOT EXISTS BookTag(
                    book_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES Tag(id)
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
                    name TEXT UNIQUE NOT NULL,
                    favorite INTEGER NOT NULL DEFAULT 0
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
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tag_ins
                     AFTER INSERT ON BookTag
                     BEGIN
                        UPDATE Books
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = NEW.book_id;
                     END""")

        # set last_change on Books when tags get removed in bridge table
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tag_del
                     AFTER DELETE ON BookTag
                     BEGIN
                        UPDATE Books
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = OLD.book_id;
                     END""")

        # set last_change on Books when new lists get added in bridge table
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_list_ins
                     AFTER INSERT ON BookList
                     BEGIN
                        UPDATE Books
                        SET last_change = DATE('now', 'localtime')
                        WHERE id = NEW.book_id;
                     END""")

        # set last_change on Books when lists get removed in bridge table
        c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_list_del
                     AFTER DELETE ON BookList
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

        # commit changes
        conn.commit()

        return conn, c
