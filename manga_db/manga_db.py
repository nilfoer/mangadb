import os
import logging
import sqlite3
import re
import urllib.request

from .logging_setup import configure_logging
from . import extractor
from .db import search
from .db.loading import load_instance
from .db.id_map import IndentityMap
from .manga import Book
from .ext_info import ExternalInfo


configure_logging("manga_db.log")
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

# part of lexical analysis
# This expression states that a "word" is either (1) non-quote, non-whitespace text
# surrounded by whitespace, or (2) non-quote text surrounded by quotes (followed by some
# whitespace).
WORD_RE = re.compile(r'([^"^\s]+)\s*|"([^"]+)"\s*')


class MangaDB:
    DEFAULT_HEADERS = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    VALID_SEARCH_COLS = {"title", "language", "status", "favorite",
                         "category", "artist", "parody", "character", "collection", "groups",
                         "tag", "list"}

    def __init__(self, root_dir, db_path, settings=None):
        self.db_con, _ = self._load_or_create_sql_db(db_path)
        self.db_con.row_factory = sqlite3.Row
        self.root_dir = os.path.abspath(os.path.normpath(root_dir))
        # TODO if we have mutliple users in e.g. webgui we need to have separate IdentityMaps
        self.id_map = IndentityMap()
        self.language_map = self._get_language_map()
        self.settings = {}
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

    def __exit__(self, exc_type, exc_value, traceback):
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
    def get_language(self, language):
        # add language if its not a language_id
        if language not in self.language_map and type(language) == str:
            with self.db_con:
                c = self.db_con.execute("INSERT OR IGNORE INTO Languages (name) VALUES (?)",
                                        (language,))
            if c.lastrowid:
                self.language_map[language] = c.lastrowid
                self.language_map[c.lastrowid] = language
            return c.lastrowid
        else:
            try:
                return self.language_map[language]
            except KeyError:
                logger.warning("Invalid language_id: %d", language)

    @staticmethod
    def download_cover(url, filename, overwrite=False):
        # TODO use urlopen and add headers
        if not os.path.isfile(filename) or overwrite:
            try:
                urllib.request.urlretrieve(url,
                                           filename)
            except urllib.request.HTTPError as err:
                logger.warning("HTTP Error %s: %s: \"%s\"",
                               err.code, err.reason, url)
                return False
            else:
                return True
        else:
            logger.debug("Thumb at '%s' was skipped since the path already exists: '%s'",
                         url, filename)
            return None

    @staticmethod
    def retrieve_book_data(url):
        extractor_cls = extractor.find(url)
        extr = extractor_cls(url)
        data = extr.get_metadata()
        if data:
            return data, extr.get_cover()
        else:
            logger.warning("No book data recieved! URL was '%s'!", url)
            return None, None

    # !!! also change single_thread_import in threads when this gets changed
    def import_book(self, url, lists):
        """
        Imports book into DB and downloads cover
        Either url and lists or book and thumb_url has to be supplied
        """
        extr_data, thumb_url = self.retrieve_book_data(url)
        if extr_data is None:
            logger.warning("Importing book failed!")
            return None, None
        # @Cleanup @Temporary convert lanugage in data to id
        extr_data["language_id"] = self.get_language(extr_data["language"])
        del extr_data["language"]

        book = Book(self, **extr_data)
        ext_info = ExternalInfo(self, book, **extr_data)
        book.ext_infos = [ext_info]
        book.list = lists

        bid, outdated_on_ei_id = book.save(block_update=True)
        if bid is None:
            logger.info("Book at url '%s' was already in DB!",
                        url if url is not None else book.ext_infos[0].url)
            return None, None, None

        # book.save returns list of ext_info_ids but import book only ever has one
        # ext_info per book -> so later just return first one if true
        outdated_on_ei_id = outdated_on_ei_id[0] if outdated_on_ei_id else None

        cover_path = os.path.join(self.root_dir, "thumbs", f"{book.id}")
        # always pass headers = extr.headers?
        if self.download_cover(thumb_url, cover_path):
            logger.info("Thumb for book %s downloaded successfully!", book.title)
        else:
            logger.warning("Thumb for book %s couldnt be downloaded!", book.title)

        return bid, book, outdated_on_ei_id

    def get_x_books(self, x, after=None, before=None, order_by="Books.id DESC"):

        # order by has to come b4 limit/offset
        query = f"""
                SELECT * FROM Books
                ORDER BY {order_by}
                LIMIT ?"""
        query, vals_in_order = search.keyset_pagination_statment(
                query, [], after=after, before=before,
                order_by=order_by, first_cond=True)
        c = self.db_con.execute(query, (*vals_in_order, x))
        rows = c.fetchall()

        if rows:
            return [load_instance(self, Book, row) for row in rows]
        else:
            return None

    def get_outdated(self, id_onpage=None, imported_from=None, order_by="Books.id DESC"):
        if id_onpage and imported_from:
            c = self.db_con.execute(f"""
                    SELECT Books.*
                    FROM Books, ExternalInfo ei
                    WHERE Books.id = ei.book_id
                    AND ei.outdated = 1
                    AND ei.id_onpage = ?
                    AND ei.imported_from = ?
                    ORDER BY {order_by}""", (id_onpage, imported_from))
        else:
            c = self.db_con.execute(f"""
                    SELECT Books.*
                    FROM Books, ExternalInfo ei
                    WHERE Books.id = ei.book_id
                    AND ei.outdated = 1
                    ORDER BY {order_by}""")
        rows = c.fetchall()
        return [load_instance(self, Book, row) for row in rows] if rows else None

    def _validate_indentifiers_types(self, identifiers_types):
        if "url" in identifiers_types:
            return True
        elif "id_onpage" in identifiers_types and "imported_from" in identifiers_types:
            return True
        elif "title_eng" in identifiers_types and "title_foreign" in identifiers_types:
            return True
        elif "id" in identifiers_types:
            return True
        else:
            logger.error("Unsupported identifiers supplied or identifier missing:\n"
                         "Identifiers need to be either 'url', 'id_onpage and imported_from', "
                         "id or 'title_eng,title_foreign' otherwise use the search:\n%s\n",
                         identifiers_types)
            return False

    def get_books(self, identifiers_types, order_by="Books.id DESC"):
        if not self._validate_indentifiers_types(identifiers_types):
            return

        if "id" in identifiers_types:
            return self.get_book(identifiers_types["id"])
        elif "title_eng" in identifiers_types:
            return self.get_book(title_eng=identifiers_types["title_eng"],
                                 title_foreign=identifiers_types["title_foreign"])
        # get id_onpage and imported_from rather than using url to speed up search
        elif "url" in identifiers_types:
            url = identifiers_types.pop("url")
            extractor_cls = extractor.find(url)
            bid = extractor_cls.book_id_from_url(url)
            identifiers_types["id_onpage"] = bid
            identifiers_types["imported_from"] = extractor_cls.site_id

        # group by books.id to get unique book results
        cur = self.db_con.execute(f"""
                    SELECT Books.*
                    FROM Books, ExternalInfo ei
                    WHERE ei.id_onpage = :id_onpage
                    AND ei.imported_from = :imported_from
                    AND Books.id = ei.book_id
                    GROUP BY Books.id
                    ORDER BY {order_by}""", identifiers_types)
        rows = cur.fetchall()
        if not rows:
            return

        for row in rows:
            yield load_instance(self, Book, row)

    def get_book(self, _id=None, title_eng=None, title_foreign=None):
        """Only id or title can guarantee uniqueness and querying using the title
           would be slower"""
        if _id:
            # try to get instance from id_map first
            instance = self.id_map.get((Book, (_id,)))
            if instance:
                return instance

            c = self.db_con.execute("SELECT * FROM Books WHERE id = ?", (_id,))
        elif title_eng or title_foreign:
            c = self.db_con.execute("SELECT * FROM Books WHERE title_eng = ? "
                                    "AND title_foreign = ?", (title_eng, title_foreign))
        else:
            logger.error("At least one of id or (title_eng and title_foreign) "
                         "needs to be supplied!")

        row = c.fetchone()
        return load_instance(self, Book, row) if row else None

    def get_book_id(self, title_eng, title_foreign):
        """
        Returns internal db id for book with given title or None
        """
        c = self.db_con.execute("SELECT id FROM Books WHERE title_eng = ? "
                                "AND title_foreign = ?", (title_eng, title_foreign))
        _id = c.fetchone()
        return _id[0] if _id else None

    def get_collection_info(self, name, order_by="id ASC"):
        c = self.db_con.execute(f"""
                SELECT b.id, b.title_eng, title_foreign, b.pages, b.my_rating
                FROM Books b, Collection c, BookCollection bc
                WHERE bc.collection_id = c.id
                AND c.name = ?
                AND b.id = bc.book_id
                ORDER BY b.{order_by}""", (name,))
        rows = c.fetchall()
        return rows if rows else None

    def get_ext_info(self, _id):
        c = self.db_con.execute("SELECT * FROM ExternalInfo WHERE id = ?", (_id,))
        row = c.fetchone()
        return load_instance(self, ExternalInfo, row, None) if row else None

    def search(self, search_string, **kwargs):
        return self._search_sytnax_parser(search_string, **kwargs)

    def _search_sytnax_parser(self,
                              search_str,
                              order_by="Books.id DESC",
                              delimiter=";",
                              **kwargs):
        normal_col_values = {}
        assoc_col_values_incl = {}
        assoc_col_values_excl = {}
        # TODO turn language_id into language and so on
        # TODO filter col name
        # Return all non-overlapping matches of pattern in string, as a list of strings.
        # The string is scanned left-to-right, and matches are returned in the order found.
        # If one or more groups are present in the pattern, return a list of groups; this will
        # be a list of tuples if the pattern has more than one group. Empty matches are included
        # in the result.
        search_col = None
        for match in WORD_RE.findall(search_str):
            single, multi_word = match
            part = None
            # single alwys has : included unless its not our syntax
            # since col:akdka;dajkda;dakda is one single word and col: is too
            if single:
                if ":" in single:
                    # -> search type is part of the word
                    search_col, part = single.split(":", 1)
                    if search_col not in self.VALID_SEARCH_COLS:
                        logger.info("'%s' is not a supported search type!", search_col)
                        # set to None so we skip adding search_options for next word (which
                        # still belongs to unsupported search_col)
                        search_col = None
                        continue
                    if not part:
                        # if part empty it was col:"multi-word"
                        continue
                else:
                    # multiple single words after each other -> use to search for title
                    # with normal syntax col is always in single word and no col if
                    # search_col isnt set so we can append all single words till we find a single
                    # word with :
                    try:
                        normal_col_values["title"] = f"{normal_col_values['title']} {single}"
                    except KeyError:
                        normal_col_values["title"] = single
                    continue

            # search_col is None if search_col isnt supported
            # then we want to ignore this part of the search
            if search_col is None:
                continue

            # a or b -> uses whatever var is true -> both true (which cant happen here) uses
            # first one
            part = part or multi_word

            if search_col in Book.ASSOCIATED_COLUMNS:
                incl, excl = search.search_assoc_col_string_parse(part, delimiter=delimiter)
                # make sure not to add an empty list otherwise we wont get an empty dic
                # that evaluates to false for testing in search_normal_mult_assoc
                if incl:
                    assoc_col_values_incl[search_col] = incl
                if excl:
                    assoc_col_values_excl[search_col] = excl
            else:
                normal_col_values[search_col] = part

        # validate order_by from user input
        if not search.validate_order_by_str(order_by):
            logger.warning("Sorting %s is not supported", order_by)
            order_by = "Books.id DESC"

        if normal_col_values or assoc_col_values_incl or assoc_col_values_excl:
            rows = search.search_normal_mult_assoc(
                    self.db_con, normal_col_values,
                    assoc_col_values_incl, assoc_col_values_excl,
                    order_by=order_by, **kwargs)
            return [load_instance(self, Book, row) for row in rows]
        else:
            return self.get_x_books(kwargs.pop("limit", 60), order_by=order_by, **kwargs)

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
            PRAGMA foreign_keys=ON; -- make sure foreign key support is activated
            CREATE TABLE IF NOT EXISTS Books(
                    id INTEGER PRIMARY KEY ASC,
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
                    book_id INTEGER NOT NULL,
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
                    outdated INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                       ON DELETE CASCADE,
                    FOREIGN KEY (imported_from) REFERENCES Sites(id)
                       ON DELETE RESTRICT,
                    FOREIGN KEY (censor_id) REFERENCES Censorship(id)
                       ON DELETE RESTRICT
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

            CREATE INDEX IF NOT EXISTS idx_id_onpage_imported_from ON
            ExternalInfo (id_onpage, imported_from);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_artist_name ON Artist (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_category_name ON Category (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_character_name ON Character (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_name ON Collection (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_name ON Groups (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_list_name ON List (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_parody_name ON Parody (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tag_name ON Tag (name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_title_eng_foreign
                ON Books (title_eng, title_foreign);
            CREATE INDEX IF NOT EXISTS idx_id_onpage_imported_from ON ExternalInfo
                (id_onpage, imported_from);

            CREATE TRIGGER IF NOT EXISTS set_books_last_change
                                 AFTER UPDATE ON Books
                                 BEGIN
                                    UPDATE Books
                                    SET last_change = DATE('now', 'localtime')
                                    WHERE id = NEW.id;
                                 END
                 """)

        # commit changes
        conn.commit()

        return conn, c
