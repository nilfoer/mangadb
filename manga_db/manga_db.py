import os
import logging
import sqlite3
import re
import urllib.request
import urllib.error
import http.cookiejar

from typing import (
    Optional, Tuple, Any, List, overload, TypedDict,
    ClassVar, cast, Dict, Sequence, Union
)

from .logging_setup import configure_logging
from . import extractor
from .extractor.base import MangaExtractorData
from .exceptions import MangaDBException
from .db import migrate
from .db import search
from .db.loading import load_instance
from .db.id_map import IndentityMap
from .db.util import table_name_to_bridge_id_col
from .manga import Book
from .ext_info import ExternalInfo
from .constants import CENSOR_IDS, STATUS_IDS, LANG_IDS


configure_logging("manga_db.log")
logger = logging.getLogger(__name__)

# setup OpenerDirector to be used for all requests
# cookiejar stores the cookies and the filecookiejar is able to save/load them to/from a file
# FileCookieJar is a kind of abstract class (i.e. it has some functionality unimplemented)
# have to use a specific subclass like MozillaCookieJar
cookie_jar = http.cookiejar.MozillaCookieJar()
# handles sending and setting cookies
cookie_handler = urllib.request.HTTPCookieProcessor(cookie_jar)
url_opener = urllib.request.build_opener(cookie_handler)
# these get automatically added to every request that use the opener
# but will be overwritten by headers that are passed to Request explicitly
url_opener.addheaders = [
    ('User-Agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'),
]
# Installing an opener is only necessary if you want urlopen to use that
# opener; otherwise, simply call OpenerDirector.open() instead of urlopen().
urllib.request.install_opener(url_opener)

# part of lexical analysis
# This expression states that a "word" is either (1) non-quote, non-whitespace text
# surrounded by whitespace, or (2) non-quote text surrounded by quotes (followed by some
# whitespace).
WORD_RE = re.compile(r'([^"^\s]+)\s*|"([^"]+)"\s*')


def set_default_user_agent(user_agent: str) -> None:
    new_addheaders = []
    overwritten = False
    for name, val in url_opener.addheaders:
        if name.lower() == 'user-agent':
            new_addheaders.append(('User-Agent', user_agent))
            overwritten = True
        else:
            new_addheaders.append((name, val))

    # in case there was none previously
    if not overwritten:
        new_addheaders.append(('User-Agent', user_agent))

    url_opener.addheaders = new_addheaders


def update_cookies_from_file(filename="cookies.txt", has_custom_info: bool = True) -> bool:
    """
    filename: Path to cookies file
    has_custom_info: Whether the cookies file has custom information like the User-Agent
                     stored in commented lines
    """
    if not os.path.isfile(filename):
        return False

    success = True
    if has_custom_info:
        user_agent: Optional[str] = None
        # @Speed (partially) reading same file twice, but FileCookieJar doesn't accept
        # a stream or text; can only be fixed by handling cookies ourselves
        with open(filename, "r", encoding='utf-8') as f:
            lines = f.readlines()

        # file has to start with commented lines, loop breaks at first regular line
        for ln in lines:
            # # is a comment, but contains User-Agent in our 'modified' cookies file format
            if ln.startswith("# User-Agent:"):
                user_agent = ln.split('User-Agent: ')[1].strip()
                break
            elif ln[0] != '#':
                break

        if user_agent:
            set_default_user_agent(user_agent)
        else:
            success = False

    # let cookiejar handle loading the cookies
    # since it can also take care of expiring cookies etc.
    # nothing loaded until we call .load
    try:
        cookie_jar.load(filename=filename)
    except http.cookiejar.LoadError:
        logger.warning("Failed to parse cookie file at %s", filename)
        return False
    else:
        return success and True


class MangaDB:
    VALID_SEARCH_COLS = {"title", "language", "language_id", "status", "favorite",
                         "category", "artist", "parody", "character", "collection", "groups",
                         "tag", "list", "status", "status_id", "nsfw", "read_status"}

    def __init__(self, root_dir, db_path, read_only=False, settings=None):
        self.db_con, _ = self._load_or_create_sql_db(db_path, read_only)
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
    def get_language(self, language: str, create_unpresent: bool = False) -> Optional[int]:
        try:
            return self.language_map[language]
        except KeyError:
            if create_unpresent:
                with self.db_con:
                    c = self.db_con.execute("INSERT OR IGNORE INTO Languages (name) VALUES (?)",
                                            (language,))
                if c.lastrowid:
                    self.language_map[language] = c.lastrowid
                    self.language_map[c.lastrowid] = language
                return c.lastrowid
            else:
                return None

    def get_language_by_id(self, lang_id: int) -> Optional[str]:
        try:
            return self.language_map[lang_id]
        except KeyError:
            logger.warning("Invalid language_id: %d", lang_id)
            return None

    @staticmethod
    def download_cover(url: str, dir_path: str, book_id: int, overwrite: bool = False,
                       forced_filename: Optional[str] = None) -> Optional[bool]:
        # NOTE: _0 appended to filename due to filename requirements imposed by the webGUI
        if forced_filename is None:
            cover_path = os.path.join(dir_path, f"{book_id}_0")
        else:
            cover_path = os.path.join(dir_path, forced_filename)

        # TODO use urlopen and add headers
        if not os.path.isfile(cover_path) or overwrite:
            try:
                urllib.request.urlretrieve(url,
                                           cover_path)
            except urllib.error.HTTPError as err:
                logger.warning("HTTP Error %s: %s: \"%s\"",
                               err.code, err.reason, url)
                return False
            else:
                return True
        else:
            logger.debug("Thumb at '%s' was skipped since the path already exists: '%s'",
                         url, cover_path)
            return None

    @staticmethod
    def retrieve_book_data(url: str) -> Tuple[Optional[MangaExtractorData], Optional[str],
                                              Optional[int]]:
        try:
            extractor_cls = extractor.find(url)
            extr = extractor_cls(url)
            data = extr.extract()
        except urllib.error.HTTPError as err:
            # NOTE: the only error that we should get is on code 503 others will
            # not be re-raised
            logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
            logger.info("If the site is reachable with your browser then "
                        "you have to update your cookies.txt")
            return None, None, err.code
        except Exception:
            # logger.exception add exception info automatically
            logger.exception("Exception while extracting '%s'", url)
            return None, None, None

        if data:
            return data, extr.get_cover(), None
        else:
            logger.warning("No book data recieved! URL was '%s'!", url)
            # @Hack this should also return an error code: enum or http code
            return None, None, None

    def book_from_data(self, data: MangaExtractorData) -> Book:
        return Book.from_manga_extr_data(self, data)

    def book_and_ei_from_data(self, data: MangaExtractorData) -> Tuple[Book, ExternalInfo]:
        book = self.book_from_data(data)
        ext_info = ExternalInfo.from_manga_extr_data(self, book, data)
        book.ext_infos = [ext_info]
        return book, ext_info

    @overload
    def import_book(self, url: str, lists: List[str]) -> Tuple[
            Optional[int], Optional[Book], Optional[int]]: ...

    # use mypy to make sure both extr_data as well as the thumb_url are supplied
    @overload
    def import_book(self, url: str, lists: List[str],
                    extr_data: MangaExtractorData, thumb_url: str) -> Tuple[
                            Optional[int], Optional[Book], Optional[int]]: ...

    # NOTE: !IMPORTANT also change single_thread_import in threads when this
    # gets changed as well as webGUI/webGUI.py:import_book
    def import_book(self, url: str, lists: List[str],
                    extr_data: Optional[MangaExtractorData] = None,
                    thumb_url: Optional[str] = None) -> Tuple[
                            Optional[int], Optional[Book], Optional[int]]:
        """
        Imports book into DB and downloads cover
        Either url and lists or book and thumb_url has to be supplied
        """

        if extr_data is None:
            extr_data, thumb_url, err_code = self.retrieve_book_data(url)
            if extr_data is None:
                logger.warning("Importing book failed!")
                return None, None, None

        book, ext_info = self.book_and_ei_from_data(extr_data)
        book.list = lists

        bid, outdated_on_ei_id = book.save(block_update=True)
        if bid is None:
            logger.info("Book at url '%s' was already in DB!",
                        url if url is not None else book.ext_infos[0].url)
            return None, None, None

        # book.save returns list of ext_info_ids but import book only ever has one
        # ext_info per book -> so later just return first one if true
        outdated_on_ei_id = outdated_on_ei_id[0] if outdated_on_ei_id else None

        if not thumb_url:
            logger.warning("Thumb for book %s couldnt be downloaded!", book.title)
        else:
            cover_dir_path = os.path.join(self.root_dir, "thumbs")
            # always pass headers = extr.headers?
            if self.download_cover(thumb_url, cover_dir_path, bid):
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
            title_cond, vals = self._title_cond(title_eng, title_foreign)
            c = self.db_con.execute(f"SELECT * FROM Books {title_cond}", vals)
        else:
            logger.error("At least one of id or (title_eng and title_foreign) "
                         "needs to be supplied!")

        row = c.fetchone()
        return load_instance(self, Book, row) if row else None

    def _title_cond(self, title_eng, title_foreign, first_cond=True):
        # where col = null doesnt work -> use col is null or col isnull
        t_eng_cond = "= ?" if title_eng is not None else "IS NULL"
        t_foreign_cond = "= ?" if title_foreign is not None else "IS NULL"
        vals = [v for v in (title_eng, title_foreign) if v is not None]
        return (f"{'WHERE' if first_cond else 'AND'} title_eng {t_eng_cond} AND "
                f"title_foreign {t_foreign_cond}", vals)

    def get_book_id(self, title_eng, title_foreign):
        """
        Returns internal db id for book with given title or None
        """
        title_cond, vals = self._title_cond(title_eng, title_foreign)
        c = self.db_con.execute(f"SELECT id FROM Books {title_cond}", vals)
        _id = c.fetchone()
        return _id[0] if _id else None

    def get_collection_info(self, name: str) -> Optional[sqlite3.Row]:
        # TODO order by in_collection_idx
        c = self.db_con.execute(f"""
                SELECT b.id, b.title_eng, title_foreign, b.pages, b.my_rating
                FROM Books b, Collection c, BookCollection bc
                WHERE bc.collection_id = c.id
                AND c.name = ?
                AND b.id = bc.book_id
                ORDER BY bc.in_collection_idx""", (name,))
        rows = c.fetchall()
        return rows if rows else None

    def get_collection_id_from_name(self, collection_name: str) -> Optional[int]:
        c = self.db_con.execute("SELECT id FROM Collection WHERE name = ?", (collection_name,))
        collection_id = c.fetchone()
        if not collection_id:
            return None
        else:
            return collection_id[0]

    # TODO generalize these when we do proper associated column representations
    def delete_tag(self, col_name: str, tag_id: int, /) -> None:
        """
        Deletes a 'tag' or rather a value associated to this rowid using a bridge table
        while also making sure the id_map representation is correct
        """
        tag_table = col_name.capitalize()
        # NOTE: does not account for non-existant tag_id
        c = self.db_con.execute(f"SELECT name FROM {tag_table} WHERE id = ?", (tag_id,))
        tag_name, = c.fetchone()

        bridge_id_col = table_name_to_bridge_id_col(tag_table)
        c.execute(f"SELECT book_id FROM Book{tag_table} WHERE {bridge_id_col} = ?", (tag_id,))
        book_ids_with_tag = c.fetchall()

        # NOTE: @Hack need to update books in id_map deleting the tag
        # and also update their _committed_state since we don't have proper
        # representations for those yet and they're just strings in a list
        id_map = self.id_map
        col_name = tag_table.lower()
        for (book_id,) in book_ids_with_tag:
            book = id_map.get((Book, (book_id,)))
            if book is None:
                continue

            tag_was_dirty = col_name in book._committed_state
            tags_before_rename = getattr(book, col_name).copy()

            # remove from current and commited list
            # modifying this will add col_name to _committed_state of DBRow if it wasn't already
            setattr(book, col_name, [tname for tname in getattr(book, col_name) if tname != tag_name])
            book._committed_state[col_name] = [
                tname for tname in book._committed_state[col_name] if tname != tag_name]
            # tag isn't dirty if states are equal
            if getattr(book, col_name) == book._committed_state[col_name]:
                del book._committed_state[col_name]

        with self.db_con:
            # actually delete tag
            c.execute(f"DELETE FROM Book{tag_table} WHERE {bridge_id_col} = ?", (tag_id,))
            c.execute(f"DELETE FROM {tag_table} WHERE id = ?", (tag_id,))

    def update_tag_name(self, col_name: str, tag_id: int, new_tag_name: str, /) -> bool:
        """
        Returns False when renaming fails due to vioalating the unique constraint on name
        """
        tag_table = col_name.capitalize()
        db_con = self.db_con
        c = db_con.execute(
                f"SELECT name FROM {tag_table} WHERE id = ?", (tag_id,))
        # value, = to unpack 1-tuple
        old_tag_name, = c.fetchone()

        bridge_id_col = table_name_to_bridge_id_col(tag_table)
        c.execute(f"SELECT book_id FROM Book{tag_table} WHERE {bridge_id_col} = ?", (tag_id,))
        book_ids_with_tag = c.fetchall()

        # rename tag first so we see if we violate a constraint
        try:
            with db_con:
                db_con.execute(f"UPDATE {tag_table} SET name = ? WHERE id = ?",
                               (new_tag_name, tag_id))
        except sqlite3.IntegrityError:
            logger.warning(
                "Could not rename %s '%s' to '%s' since the new name already exists",
                col_name, old_tag_name, new_tag_name)
            return False

        # NOTE: @Hack need to update books in id_map with the new tag name
        # and also update their _committed_state since we don't have proper
        # representations for those yet and they're just strings in a list
        id_map = self.id_map
        for (book_id,) in book_ids_with_tag:
            book = id_map.get((Book, (book_id,)))
            if book is None:
                continue

            tag_was_dirty = col_name in book._committed_state
            tag_before_rename = getattr(book, col_name).copy()

            # this will add the change to _committed_state of DBRow
            setattr(book, col_name, [tname if tname != old_tag_name else new_tag_name
                                     for tname in getattr(book, col_name)])
            if not tag_was_dirty:
                # we can just remove it since nothing was modified before
                del book._committed_state[col_name]
            else:
                # otherwise we have to re-create the modified state
                if (tag_before_rename == [new_tag_name] and
                        book._committed_state[col_name] == [old_tag_name]):
                    # only our tag -> remove
                    del book._committed_state[col_name]
                else:
                    # rename our tag in _committed_state so the diff
                    # on update will be correct
                    book._committed_state[col_name] = [
                        cname if cname != old_tag_name else new_tag_name
                        for cname in book._committed_state[col_name]]

        return True

    def update_in_collection_order(self, collection_id: int,
                                   book_id_collection_idx: Sequence[Tuple[int, int]]) -> None:
        if len(book_id_collection_idx) < 2:
            return

        # just deleting and re-inserting in the correct order is probably faster
        # than swapping to a temp slot etc.
        with self.db_con:
            c = self.db_con.execute(
                    "DELETE FROM BookCollection WHERE collection_id = ?", (collection_id,))
            # generator book_id, collection_id, in_collection_idx
            bid_cid_cidx = (
                (book_id, collection_id, in_collection_idx)
                for book_id, in_collection_idx in book_id_collection_idx)
            c.executemany("""
            INSERT INTO BookCollection(book_id, collection_id, in_collection_idx)
            VALUES (?, ?, ?)""", bid_cid_cidx)
        # c = self.db_con.execute("""
        # SELECT MAX(in_collection_idx) + 1
        # FROM BookCollection
        # WHERE collection_id = (
        #     SELECT c.id
        #     FROM Collection c
        #     WHERE c.name = ?
        # )""", (collection_name,))

        # # need to use a temp value otherwise unique constraints will fail
        # temp_max = c.fetchone()
        # temp_book_id: Optional[int] = None
        # temp_move_to_cidx: Optional[int] = None

        # upd_str = "UPDATE BookCollection SET in_collection_idx = ? WHERE book_id = ?"
        # for book_id, new_in_cidx in sorted(book_id_collection_idx, key=lambda x: x[1]):
        #     if temp_book_id is not None:
        #         # move temp to idx it was supposed to be at
        #         c.execute(upd_str, (temp_move_to_cidx, temp_book_id))
        #         temp_book_id = None
        #         temp_move_to_cidx = None
        #     c.execute("UPDATE BookCollection SET in_collection_idx = ? WHERE book_id = ?"
        #               (temp_max, book_id))
        #     temp_book_id = book_id
        #     temp_move_to_cidx = new_in_cidx

    @overload
    def get_books_in_collection(self, collection_identifier: str) -> Optional[List[Book]]: ...

    @overload
    def get_books_in_collection(self, collection_identifier: int) -> Optional[List[Book]]: ...

    def get_books_in_collection(
            self, collection_identifier: Union[str, int]) -> Optional[List[Book]]:

        if isinstance(collection_identifier, str):
            id_name = 'name'
        else:
            id_name = 'id'

        c = self.db_con.execute(f"""
                SELECT b.*
                FROM Books b, Collection c, BookCollection bc
                WHERE bc.collection_id = c.id
                AND c.{id_name} = ?
                AND b.id = bc.book_id
                ORDER BY bc.in_collection_idx ASC""", (collection_identifier,))
        rows = c.fetchall()
        if rows:
            books = [load_instance(self, Book, row) for row in rows]
            return books
        else:
            return None

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

        # convert name of Censorship, Language etc. to id
        self.convert_names_to_ids(normal_col_values)

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

    def convert_names_to_ids(self, dictlike):
        try:
            language_id = self.get_language(dictlike["language"], create_unpresent=False)
            if language_id is not None:
                dictlike["language_id"] = language_id
            del dictlike["language"]
        except KeyError:
            pass
        try:
            censor_id = CENSOR_IDS.get(dictlike["censorship"], None)
            if censor_id is not None:
                dictlike["censor_id"] = censor_id
            del dictlike["censorship"]
        except KeyError:
            pass
        try:
            status_id = STATUS_IDS.get(dictlike["status"], None)
            if status_id is not None:
                dictlike["status_id"] = status_id
            del dictlike["status"]
        except KeyError:
            pass

    @staticmethod
    def _load_or_create_sql_db(filename, read_only=False):
        """
        Creates connection to sqlite3 db and a cursor object. Creates the DB if
        it doesn't exist yet.

        If read_only is set to True the database schema won't be created!

        :param filename: Filename string/path to file
        :param read_only: Whether to return a read-only database connection
        :return: connection to sqlite3 db and cursor instance
        """
        if not os.path.isfile(filename):
            if read_only is True:
                raise MangaDBException("Can't create new database in read-only mode!")
            else:
                return MangaDB._create_sql_db(filename)

        if read_only is True:
            # enable uri mode so we can pass mode ro for read-only access
            conn = sqlite3.connect(f"file:{filename}?mode=ro", uri=True,
                                   detect_types=sqlite3.PARSE_DECLTYPES)
        else:
            # PARSE_DECLTYPES -> parse types and search for converter function for
            # it instead of searching for converter func for specific column name
            conn = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES)

            # NOTE: migrate DB; context manager automatically closes connection
            with migrate.Database(filename) as migration:
                migration_success = migration.upgrade_to_latest()
            if not migration_success:
                conn.close()
                raise MangaDBException("Could not migrate DB! Open an issue at "
                                       "github.com/nilfoer/mangadb")

        # use Row as row_factory for easier access
        conn.row_factory = sqlite3.Row
        # after row factory change otherwise cursor will still use tuples!
        c = conn.cursor()

        # make sure foreign key support is activated
        # NOTE: even though i was setting PRAGMA foreign_keys=on in the db creation
        # script it still had the foreign_keys turned off somehow
        # => PRAGMAs are never saved. With the exception of those with the
        # explicit purpose of setting a file's metadata, they always just have
        # an effect on the current connection
        # => so this also does not need to be commited
        c.execute("PRAGMA foreign_keys=on")

        return conn, c

    @staticmethod
    def _create_sql_db(filename, read_only=False):
        conn = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES)
        c = conn.cursor()

        c.executescript("""
            CREATE TABLE Sites (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE Languages (
                     id INTEGER PRIMARY KEY ASC,
                     name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE Censorship (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
            CREATE TABLE Status(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                     """)

        c.executemany("INSERT INTO Sites(id, name) VALUES (?, ?)",
                      [(key, val) for key, val in extractor.SUPPORTED_SITES.items()
                       if isinstance(key, int)])

        id_lang = [(i, v) for i, v in LANG_IDS.items() if type(i) is int]
        c.executemany("INSERT INTO Languages(id, name) VALUES (?, ?)", id_lang)

        cen_stats = [(i, v) for i, v in CENSOR_IDS.items() if type(i) is int]
        c.executemany("INSERT INTO Censorship(id, name) VALUES (?, ?)", cen_stats)

        status = [(i, v) for i, v in STATUS_IDS.items() if type(i) is int]
        c.executemany("INSERT INTO Status(id, name) VALUES (?, ?)", status)

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
        # ON DELETE CASCADE, wenn der eintrag des FK in der primärtabelle gelöscht wird dann
        # auch in dieser (detailtabelle) die einträge löschen -> Löschweitergabe
        create_db_sql = f"""
            PRAGMA foreign_keys=ON; -- make sure foreign key support is activated
            CREATE TABLE Books(
                    id INTEGER PRIMARY KEY ASC,
                    title_eng TEXT,
                    title_foreign TEXT,
                    language_id INTEGER NOT NULL,
                    pages INTEGER NOT NULL,
                    status_id INTEGER NOT NULL,
                    chapter_status TEXT,
                    read_status INTEGER,
                    my_rating REAL,
                    note TEXT,
                    last_change DATE NOT NULL,
                    favorite INTEGER NOT NULL,
                    cover_timestamp REAL NOT NULL DEFAULT 0,
                    nsfw INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (language_id) REFERENCES Languages(id)
                       ON DELETE RESTRICT,
                    FOREIGN KEY (status_id) REFERENCES Status(id)
                       ON DELETE RESTRICT
                );
            -- change collating function that is used for string comparisons (can also be done
            -- on a single select instead: e.g. "name = ? COLLATE NOCASE") to NOCASE for case
            -- insensitive comparison when using '=' operator etc.
            CREATE TABLE List(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            CREATE TABLE BookList(
                    book_id INTEGER NOT NULL,
                    list_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (list_id) REFERENCES List(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, list_id)
                );
            CREATE TABLE Tag(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            CREATE TABLE BookTag(
                    book_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES Tag(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, tag_id)
                 );
            CREATE TABLE ExternalInfo(
                    id INTEGER PRIMARY KEY ASC,
                    book_id INTEGER NOT NULL,
                    id_onpage TEXT NOT NULL,
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
            CREATE TABLE Collection(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            CREATE TABLE BookCollection(
                    book_id INTEGER NOT NULL,
                    collection_id INTEGER NOT NULL,
                    in_collection_idx INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (collection_id) REFERENCES Collection(id)
                    ON DELETE CASCADE,
                    UNIQUE(collection_id, in_collection_idx),
                    PRIMARY KEY (book_id, collection_id)
                );
            CREATE TABLE Category(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            CREATE TABLE BookCategory(
                    book_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (category_id) REFERENCES Category(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, category_id)
                );
            -- Group protected keyword in sql
            CREATE TABLE Groups(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            CREATE TABLE BookGroups(
                    book_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES Groups(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, group_id)
                );
            CREATE TABLE Artist(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    favorite INTEGER NOT NULL DEFAULT 0
                );
            CREATE TABLE BookArtist(
                    book_id INTEGER NOT NULL,
                    artist_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (artist_id) REFERENCES Artist(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, artist_id)
                );
            CREATE TABLE Parody(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            CREATE TABLE BookParody(
                    book_id INTEGER NOT NULL,
                    parody_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (parody_id) REFERENCES Parody(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, parody_id)
                );
            CREATE TABLE Character(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            CREATE TABLE BookCharacter(
                    book_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (character_id) REFERENCES Character(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, character_id)
                );

            -- insert versioning table
            -- migrate uses execute instead of executescript since the latter
            -- auto-commits and execute doesn't allow semicolons
            -- -> append semicolon manually here
            {migrate.VERSION_TABLE_SQL};
            INSERT INTO '{migrate.VERSION_TABLE}' VALUES ({migrate.LATEST_VERSION}, 0);

            CREATE INDEX idx_id_onpage_imported_from ON
            ExternalInfo (id_onpage, imported_from);
            -- set collating function of the index explicitly
            -- has to match the columns' (that the index is on) collating functions otherwise
            -- it won't be used
            CREATE UNIQUE INDEX idx_artist_name ON Artist (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_category_name ON Category (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_character_name ON Character (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_collection_name ON Collection (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_groups_name ON Groups (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_list_name ON List (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_parody_name ON Parody (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_tag_name ON Tag (name COLLATE NOCASE);
            CREATE UNIQUE INDEX idx_title_eng_foreign
                ON Books (title_eng, title_foreign);

            CREATE TRIGGER set_books_last_change
                                 AFTER UPDATE ON Books
                                 BEGIN
                                    UPDATE Books
                                    SET last_change = DATE('now', 'localtime')
                                    WHERE id = NEW.id;
                                 END
                 """
        c.executescript(create_db_sql)
        # commit changes
        conn.commit()

        # use Row as row_factory for easier access
        conn.row_factory = sqlite3.Row
        # get new cursor after row factory change otherwise cursor will still use tuples!
        c = conn.cursor()

        return conn, c
