import os
import logging
import sqlite3
import re
import urllib.request

from .logging_setup import configure_logging
from . import extractor
from .db import search
from .manga import MangaDBEntry
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
                               err.code, err.reason, url)
                return False
            else:
                return True
        else:
            logger.debug("Thumb at '%s' was skipped since the path already exists: '%s'",
                         url, filename)
            return None

    def retrieve_book_data(self, url):
        extractor_cls = extractor.find(url)
        extr = extractor_cls(self, url)
        data = extr.get_metadata()
        if data:
            book = MangaDBEntry(self, data)
            ext_info = ExternalInfo(self, book, data)
            book.ext_infos = [ext_info]
            return book, ext_info, extr.get_cover()
        else:
            logger.warning("No data to create book at url '%s' from!", url)
            return None, None, None

    def import_book(self, url=None, lists=None, book=None, thumb_url=None):
        """
        Imports book into DB and downloads cover
        Either url and lists or book and thumb_url has to be supplied
        """
        thumb_url = thumb_url
        if url and lists is not None:
            book, _, thumb_url = self.retrieve_book_data(url)
            if book is None:
                logger.warning("Importing book failed!")
                return None, None
            # @Cleanup find a better way to add/set data esp. b4 adding to db
            # works here since changes are ignored when adding to db and reset afterwards
            book.update_from_dict({"list": lists})
        elif book and thumb_url:
            book = book
        else:
            logger.error("Either url and lists or book and thumb_url have to be supplied")
            return None, None

        # @Cleanup getting id twice (once here 2nd time in book.save)
        bid = self.get_book_id(book.title)
        outdated_on_ei_id = None
        if bid is None:
            bid, outdated_on_ei_ids = book.save()
            # book.save returns list of ext_info_ids but import book only ever has one
            # ext_info per book -> so later just return first one if true
            outdated_on_ei_id = outdated_on_ei_ids[0] if outdated_on_ei_ids else None

            cover_path = os.path.join(self.root_dir, "thumbs", f"{book.id}")
            # always pass headers = extr.headers?
            if self.download_cover(thumb_url, cover_path):
                logger.info("Thumb for book %s downloaded successfully!", book.title)
            else:
                logger.warning("Thumb for book %s couldnt be downloaded!", book.title)
        else:
            logger.info("Book at url '%s' was already in DB!",
                        url if url is not None else book.ext_infos[0].url)

        return bid, book, outdated_on_ei_id

    def get_x_books(self, x, offset=0, order_by="Books.id DESC", count=False):
        # order by has to come b4 limit/offset
        c = self.db_con.execute(f"SELECT * FROM Books ORDER BY {order_by} LIMIT {x} "
                                f"OFFSET {offset}")
        rows = c.fetchall()

        total = None
        if count:
            c.execute(f"SELECT COUNT(*) FROM Books")
            total = c.fetchone()
            total = total[0] if total else 0

        if rows:
            return [MangaDBEntry(self, row) for row in rows], total
        else:
            return None, None

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

    def get_books(self, identifiers_types, order_by="Books.id DESC"):
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
                    AND Books.id = eib.book_id
                    ORDER BY {order_by}""", identifiers_types)
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

    def get_ext_info(self, _id):
        c = self.db_con.execute("SELECT * FROM ExternalInfo WHERE id = ?", (_id,))
        return ExternalInfo(self, None, c.fetchone())

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

            if search_col in MangaDBEntry.JOINED_COLUMNS:
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
            return search.search_normal_mult_assoc(
                    self.db_con, normal_col_values,
                    assoc_col_values_incl, assoc_col_values_excl,
                    order_by=order_by, **kwargs)
        else:
            return self.get_x_books(60, order_by=order_by, offset=kwargs.get("offset", 0),
                                    count=kwargs.get("count", False))

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
                    outdated INTEGER NOT NULL,
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
