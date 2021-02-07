import os
import logging
import datetime

from typing import TYPE_CHECKING, ClassVar, Tuple

from .db.loading import load_instance
from .db.row import DBRow
from .db.column import Column, ColumnWithCallback
from .db.column_associated import AssociatedColumnMany
from .db.constants import Relationship
from .ext_info import ExternalInfo
from .constants import STATUS_IDS
from .db.util import joined_col_name_to_query_names
from .util import diff_update

if TYPE_CHECKING:
    from .manga_db import MangaDB
    from .extractor.base import MangaExtractorData

logger = logging.getLogger(__name__)


class Book(DBRow):
    """
    Fields of data that can have multiple values need to be of type list!!!
    """

    TABLENAME = "Books"

    MANGA_TITLE_FORMAT = "{english} / {foreign}"

    id = Column(int, primary_key=True)
    title_eng = ColumnWithCallback(str)
    title_foreign = ColumnWithCallback(str)
    language_id = Column(int, nullable=False)
    pages = Column(int, nullable=False)
    status_id = Column(int, nullable=False)
    chapter_status = Column(str, nullable=True)
    read_status = Column(int, nullable=True)
    my_rating = Column(float)
    # @Incomplete custom 'ORM' not fully implemented yet so no way to express
    # this relationship properly; currently just loading the name columns
    category: AssociatedColumnMany[str] = AssociatedColumnMany(
            "Category", Relationship.MANYTOMANY,
            assoc_table="BookCategory")
    collection: AssociatedColumnMany[str] = AssociatedColumnMany(
            "Collection", Relationship.MANYTOMANY, assoc_table="BookCollection")
    groups: AssociatedColumnMany[str] = AssociatedColumnMany(
            "Groups", Relationship.MANYTOMANY, assoc_table="BookGroups")
    artist: AssociatedColumnMany[str] = AssociatedColumnMany(
            "Artist", Relationship.MANYTOMANY, assoc_table="BookArtist")
    parody: AssociatedColumnMany[str] = AssociatedColumnMany(
            "Parody", Relationship.MANYTOMANY, assoc_table="BookParody")
    character: AssociatedColumnMany[str] = AssociatedColumnMany(
            "Character", Relationship.MANYTOMANY, assoc_table="BookCharacter")
    list: AssociatedColumnMany[str] = AssociatedColumnMany(
            "List", Relationship.MANYTOMANY, assoc_table="BookList")
    tag: AssociatedColumnMany[str] = AssociatedColumnMany(
            "Tag", Relationship.MANYTOMANY, assoc_table="BookTag")
    ext_infos: AssociatedColumnMany[ExternalInfo] = AssociatedColumnMany(
            "ExternalInfo", Relationship.ONETOMANY)
    last_change = Column(datetime.date, nullable=False)
    note = Column(str)
    favorite = Column(int, nullable=False)
    cover_timestamp = Column(float, nullable=False, default=0.0)
    nsfw = Column(int, nullable=False, default=0)

    def __init__(
            self,
            manga_db,
            id=None,
            title_eng=None,
            title_foreign=None,
            language_id=None,
            pages=None,
            status_id=None,
            chapter_status=None,
            read_status=None,
            my_rating=None,
            category=None,
            collection=None,
            groups=None,
            artist=None,
            parody=None,
            character=None,
            list=None,
            tag=None,
            ext_infos=None,
            last_change=None,
            note=None,
            favorite=None,
            cover_timestamp=None,
            nsfw=None,
            in_db=False,
            **kwargs):
        super().__init__(manga_db, in_db, **kwargs)
        self.id = id
        self.title_eng = title_eng
        self.title_foreign = title_foreign
        self.language_id = language_id
        self.pages = pages
        self.status_id = status_id
        self.chapter_status = chapter_status
        self.read_status = read_status
        self.my_rating = my_rating
        self.category = category
        self.collection = collection
        self.groups = groups
        self.artist = artist
        self.parody = parody
        self.character = character
        self.list = list
        self.tag = tag
        self.ext_infos = ext_infos
        self.last_change = last_change
        self.note = note
        self.favorite = favorite
        self.cover_timestamp = cover_timestamp
        self.nsfw = nsfw
        if in_db:
            # load associated columns
            # TODO lazy loading
            self.update_assoc_columns_from_db()

        if self.last_change is None:
            self.set_last_change()

    def set_last_change(self):
        self.last_change = datetime.date.today()
        return self.last_change

    @property
    def title(self):
        return self.build_title(self.title_eng, self.title_foreign)

    @staticmethod
    def build_title(title_eng, title_foreign):
        # build title ourselves so title is the correct format
        if title_eng and title_foreign:
            return Book.MANGA_TITLE_FORMAT.format(
                    english=title_eng, foreign=title_foreign)
        else:
            return title_eng or title_foreign

    def update_from_dict(self, dic):
        # TODO validate input
        for col in self.COLUMNS + self.ASSOCIATED_COLUMNS:
            # never update id, last_change from dict, handle title and fav ourselves
            if col in ("favorite", "ext_infos"):
                continue
            try:
                new = dic[col]
            except KeyError:
                pass
            else:
                setattr(self, col, new)

        # TODO ext_infos
        fav = dic.get("favorite", None)
        if fav is not None:
            self.favorite = fav

    def update_ext_infos(self):
        self._ext_infos = self._fetch_external_infos()
        return self._ext_infos

    @property
    def avg_ext_rating(self):
        if self.ext_infos:
            ratings = [ei.rating for ei in self.ext_infos if ei.rating]
            if ratings:
                return sum(ratings)/len(ratings)
            else:
                return None
        else:
            return None

    def _fetch_external_infos(self):
        ext_infos = []
        c = self.manga_db.db_con.execute("""
                        SELECT ei.*
                        FROM ExternalInfo ei, Books
                        WHERE Books.id = ei.book_id
                        AND Books.id = ?""", (self.id,))
        for row in c.fetchall():
            ei = load_instance(self.manga_db, ExternalInfo, row, self)
            ext_infos.append(ei)
        return ext_infos

    def update_assoc_columns_from_db(self):
        for col, val in self.get_associated_columns().items():
            setattr(self, col, val)
        # possible changes overwritten -> remove assoc cols from _committed_state
        self._committed_state = {k: v for k, v in self._committed_state.items() if k not in
                                 self.ASSOCIATED_COLUMNS}

    def get_associated_columns(self):
        """
        Gets columns that are associated to this row by a bridge table from DB
        """
        if self.id is None:
            raise ValueError("Id must be set in order to get associated columns from DB!")

        result = {
            "list": None,
            "tag": None,
            "category": None,
            "collection": None,
            "groups": None,
            "artist": None,
            "parody": None,
            "character": None
            }

        for col in result:
            result[col] = self._fetch_associated_column(col)
        result["ext_infos"] = self._fetch_external_infos()
        return result

    def _fetch_associated_column(self, col_name):
        table_name, bridge_col_name = joined_col_name_to_query_names(col_name)
        c = self.manga_db.db_con.execute(f"""SELECT group_concat(x.name, ';')
                                             FROM {table_name} x, Book{table_name} bx, Books
                                             WHERE bx.book_id = Books.id
                                             AND Books.id = ?
                                             AND bx.{bridge_col_name} = x.id
                                             GROUP BY bx.book_id""", (self.id, ))
        result = c.fetchone()
        return result[0].split(";") if result else []

    def get_all_options_for_assoc_columns(self):
        result = {
            "list": None,
            "tag": None,
            "category": None,
            "collection": None,
            "groups": None,
            "artist": None,
            "parody": None,
            "character": None
            }
        for col in result:
            c = self.manga_db.db_con.execute(f"SELECT id, name FROM {col.capitalize()}")
            result[col] = c.fetchall()
        return result

    def get_all_options_for_assoc_column(self, col_name):
        c = self.manga_db.db_con.execute(f"SELECT id, name FROM {col_name.capitalize()}")
        return c.fetchall()

    def update(self):
        """Discards changes and updates from DB"""
        # TODO
        raise NotImplementedError

    # TODO implement Column subclass/option for that
    @property
    def language(self):
        return self.manga_db.language_map[self.language_id]

    @language.setter
    def language(self, value):
        if isinstance(value, str):
            self.language_id = self.manga_db.get_language(value, create_unpresent=True)
        else:
            logger.warning("Type of language needs to be string!")

    @property
    def status(self):
        return STATUS_IDS[self.status_id]

    @status.setter
    def status(self, value):
        if isinstance(value, str):
            try:
                self.status_id = STATUS_IDS[value]
            except KeyError:
                logger.warning("No such status: %s", value)
        else:
            logger.warning("Type of status needs to be string!")

    def save(self, block_update=False, force=False):
        """
        Save changes to DB
        """
        if self.id is None:
            bid = self.manga_db.get_book_id(self.title_eng, self.title_foreign)
            if bid is None:
                return self._add_entry()
            elif block_update:
                # NOTE: currently assuming that saving with block_update=True means we
                # wanted to add the book to the DB and it since we landed here
                # the title eng+foreign combination was already present
                # -> append sth. unique to the title and try again ONCE
                if force:
                    logger.info("The combination of the english and foreign title was not "
                                "unique for this book and thus has been renamed!")
                    self.title_eng = f"{self.title_eng} (DUPLICATE {datetime.datetime.now()})"
                    return self.save(block_update=True, force=False)

                logger.debug("Book was found in DB(id %d) but saving was blocked due to "
                             "block_update option!", bid)
                return None, None
        return self._update_entry()

    def _add_entry(self):
        """Commits changes to db"""
        if self.favorite is None:
            self.favorite = 0
        db_dict = self.export_for_db()
        cols = [col for col in self.COLUMNS if col != "id"]

        # since were saving ext_infos we also have to pass along if we had
        # outdated links
        outdated_on_ei_ids = []
        with self.manga_db.db_con:
            c = self.manga_db.db_con.execute(f"""
                    INSERT INTO Books ({','.join(cols)})
                    VALUES ({','.join((f':{col}' for col in cols))}
                    )""", db_dict)
            self.id = c.lastrowid

            for col in self.ASSOCIATED_COLUMNS:
                if col == "ext_infos":
                    if self.ext_infos:
                        # also save ext_infos
                        for ext_info in self.ext_infos:
                            eid, outdated = ext_info.save()
                            if outdated:
                                # save ext_info id that triggered outdated warning
                                outdated_on_ei_ids.append(eid)
                    continue
                value = getattr(self, col)
                # assoc col many returns empty trackable if no value whereas assoc col one
                # returns None
                if ((isinstance(value, list) and value) or
                        (not isinstance(value, list) and value is not None)):
                    self._add_associated_column_values(col, value)

        logger.info("Added book with title \"%s\"  as id '%d' to database!", self.title, self.id)
        self._in_db = True
        # add self to id_map so we always work on the same instance even if we re-fetch this
        # book from db
        self.manga_db.id_map.add_unprecedented(self)
        # reset committed state since we just committed
        self._committed_state = {}

        return self.id, outdated_on_ei_ids

    def remove(self):
        """Commits changes itself, since it also deletes book thumb anyway!"""
        # triggers will delete all joined cols when associated manga_db_entry is deleted
        # or rather the entries in the connection tables
        # ext infos have to be deleted manually

        # ensure that all ext_infos are loaded
        ext_infos = self._fetch_external_infos()
        for ext_info in ext_infos:
            ext_info.remove()

        with self.manga_db.db_con:
            self.manga_db.db_con.execute(f"""
                                DELETE
                                FROM Books
                                WHERE
                                id = ?""", (self.id, ))

        self._in_db = False
        # delete from id_map
        self.manga_db.id_map.remove(self.key)

        # also delete book thumb
        try:
            os.remove(os.path.join("thumbs", str(self.id)))
        except FileNotFoundError:
            logger.debug("No cover or cover was already deleted for id %d", self.id)
        logger.debug("Removed thumb with path thumbs/%d", self.id)

        logger.info("Successfully removed book with id %d", self.id)

    def remove_ext_info(self, _id):
        if not self.ext_infos:
            logger.warning("No external infos on book with id %d or not fetched from DB yet!",
                           self.id)
            return None
        try:
            ext_info = next((ei for ei in self.ext_infos if ei.id == _id))
        except StopIteration:
            ext_info = None
        if ext_info is None:
            logger.error("No external info with id %d found!", _id)
            return None
        url = ext_info.url
        self.ext_infos = [ei for ei in self.ext_infos if ei.id != _id]
        ext_info.remove()
        logger.info("Removed external info with id %d from book with id %d",
                    _id, self.id)
        return url

    def _add_associated_column_values(self, col_name, values):
        table_name, bridge_col_name = joined_col_name_to_query_names(col_name)
        # values gotta be list/tuple of lists/tuples
        li_of_tup = [(val,) for val in values]
        c = self.manga_db.db_con.executemany(
                f"INSERT OR IGNORE INTO {table_name}(name) VALUES (?)", li_of_tup)

        # NOTE: careful! since OR IGNORE ignores the insert if sth. like a unique constraint
        # is violated it also doesn't raise an exception etc. and a bug of not adding
        # rows might get unnoticed
        # we don't need OR IGNORE here, since our we only add values that weren't present
        # on the book; could only happen if our id_map is buggy or our db was modified
        # form another connection
        # TODO @Hack need to treat this specially since we need the max in_collection_idx
        if col_name == "collection":
            # use max in_collection_idx + 1 for a collection that was newly added
            c.executemany("""INSERT INTO BookCollection(book_id, collection_id, in_collection_idx)
                             SELECT ?, Collection.id, (
                                SELECT MAX(bc.in_collection_idx) + 1
                                FROM BookCollection bc
                             )
                             FROM Collection
                             WHERE Collection.name = ?""", zip([self.id] * len(values), values))
        else:
            c.executemany(f"""INSERT INTO Book{table_name}(book_id, {bridge_col_name})
                              SELECT ?, {table_name}.id
                              FROM {table_name}
                              WHERE {table_name}.name = ?""", zip([self.id] * len(values), values))
        logger.debug("Added '%s' to associated column '%s'", ", ".join(values), table_name)

    def _remove_associated_column_values(self, col_name, values):
        table_name, bridge_col_name = joined_col_name_to_query_names(col_name)
        self.manga_db.db_con.execute(f"""
                DELETE FROM Book{table_name}
                WHERE Book{table_name}.{bridge_col_name} IN
                   (
                   SELECT {table_name}.id FROM {table_name}
                   WHERE
                   ({table_name}.name IN ({', '.join(['?']*len(values))}))
                   )
                AND Book{table_name}.book_id = ?""", (*values, self.id))
        logger.debug("Removed '%s' from associated column '%s'", values, table_name)

    def _update_entry(self):
        """
        Commits changes to db
        Doesnt save changes in ext_infos
        """

        if not self._committed_state:
            logger.debug("No changes to save for book with id %d", self.id)
            return self.id, None

        db_con = self.manga_db.db_con
        logger.info("Updating Book with id '%d'", self.id)

        self.set_last_change()
        update_dic = self.export_for_db()
        changed_cols = [col for col in self._committed_state if col in self.COLUMNS]

        with db_con:
            db_con.execute(f"""UPDATE Books SET
                          {','.join((f'{col} = :{col}' for col in changed_cols))}
                          WHERE id = :id""", update_dic)

            self._update_associated_columns()

        logger.info("Updated book with id %d in DB!", self.id)
        # reset _committed_state
        self._committed_state = {}
        # c.lastrowid only works for INSERT/REPLACE
        return self.id, None

    def _update_associated_columns(self):
        changed_cols = [col for col in self._committed_state if col in self.ASSOCIATED_COLUMNS]
        for col in changed_cols:
            if col == "ext_infos":
                continue
            if getattr(Book, col).relationship in (
                    Relationship.MANYTOONE, Relationship.ONETOONE):
                # TODO
                raise NotImplementedError
            else:
                old = self._committed_state[col]
                new = getattr(self, col)
                added, removed = diff_update(old, new)
                if added:
                    self._add_associated_column_values(col, added)
                if removed:
                    self._remove_associated_column_values(col, removed)

    # repr -> unambiguos
    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"<Book({selfdict_str})>"

    # str -> readable
    def __str__(self):
        return self.__repr__()

    def to_export_string(self):
        lines = []
        for col in self.COLUMNS:
            val = getattr(self, col)
            col_name = col
            if col == "language_id":
                val = self.manga_db.language_map[val]
                col_name = "language"
            elif col == "status_id":
                val = STATUS_IDS[val]
                col_name = "status"
            lines.append(f"{col_name}: {val}")
        for col in self.ASSOCIATED_COLUMNS:
            if col == "ext_infos":
                continue
            attr = getattr(self, col)
            if attr is None:
                val = ""
            else:
                val = ", ".join(attr)
            lines.append(f"{col}: {val}")

        for ei in self.ext_infos:
            lines.append("\n")
            lines.append(f"External link:")
            lines.append(ei.to_export_string())

        return "\n".join(lines)

    def diff(self, other):
        # doesnt diff ext_infos
        changes = {}
        change_str = []
        for col in self.COLUMNS:
            val_self = getattr(self, col)
            val_other = getattr(other, col)
            if val_self != val_other:
                changes[col] = val_other
                change_str.append(f"Column '{col}' changed from '{val_self}' to '{val_other}'")
        for col in self.ASSOCIATED_COLUMNS:
            if col == "ext_infos":
                continue
            val_self = getattr(self, col)
            val_other = getattr(other, col)
            if val_self != val_other:
                added, removed = diff_update(val_self, val_other)
                if added is None and removed is None:
                    continue
                changes[col] = (added, removed)
                if added or removed:
                    change_str.append(f"Column '{col}' changed:")
                    if added:
                        change_str.append(f"Added: {';'.join(added)}")
                    if removed:
                        change_str.append(f"Removed: {';'.join(removed)}")

        change_str = "\n".join(change_str)
        return changes, change_str

    @staticmethod
    def set_favorite_id(mdb, book_id, fav_intbool):
        # if book is loaded in id_map changes in db wont propagate
        # so try to get it from db and apply changes
        book = mdb.id_map.get((Book, (book_id,)))
        if book is not None:
            book.favorite = fav_intbool
            # remove entry in commited so it wont save again
            del book._committed_state["favorite"]
        with mdb.db_con:
            mdb.db_con.execute("UPDATE Books SET favorite = ?, "
                               "last_change = DATE('now', 'localtime') WHERE id = ?",
                               (fav_intbool, book_id))

    @staticmethod
    def rate_book_id(mdb, book_id, rating):
        book = mdb.id_map.get((Book, (book_id,)))
        if book is not None:
            book.my_rating = rating
            # remove entry in commited so it wont save again
            del book._committed_state["my_rating"]
        with mdb.db_con:
            mdb.db_con.execute("UPDATE Books SET my_rating = ?, "
                               "last_change = DATE('now', 'localtime') WHERE id = ?",
                               (rating, book_id))

    @staticmethod
    def add_assoc_col_on_book_id(mdb, book_id, col_name, values, before):
        book = mdb.id_map.get((Book, (book_id,)))
        if book is not None:
            # we need to use set to overwrite possible prior changes
            # otherwise .save() would produce unpredictable results
            setattr(book, col_name, before + values)
            # remove entry in commited so it wont save again
            del book._committed_state[col_name]

        table_name, bridge_col_name = joined_col_name_to_query_names(col_name)
        # values gotta be list/tuple of lists/tuples
        li_of_tup = [(val,) for val in values]
        with mdb.db_con:
            c = mdb.db_con.executemany(
                    f"INSERT OR IGNORE INTO {table_name}(name) VALUES (?)", li_of_tup)

            c.executemany(f"""INSERT OR IGNORE INTO Book{table_name}(book_id, {bridge_col_name})
                              SELECT ?, {table_name}.id
                              FROM {table_name}
                              WHERE {table_name}.name = ?""", zip([book_id] * len(values), values))
            
            c.execute("UPDATE Books SET last_change = DATE('now', 'localtime') WHERE id = ?",
                      (book_id,))

        logger.debug("Added '%s' to associated column '%s'", ", ".join(values), table_name)

    @staticmethod
    def remove_assoc_col_on_book_id(mdb, book_id, col_name, values, before):
        book = mdb.id_map.get((Book, (book_id,)))
        if book is not None:
            # we need to use set to overwrite possible prior changes
            # otherwise .save() would produce unpredictable results
            setattr(book, col_name, [v for v in before if v not in values])
            # remove entry in commited so it wont save again
            del book._committed_state[col_name]

        table_name, bridge_col_name = joined_col_name_to_query_names(col_name)
        with mdb.db_con:
            c = mdb.db_con.execute(f"""
                    DELETE FROM Book{table_name}
                    WHERE Book{table_name}.{bridge_col_name} IN
                       (
                       SELECT {table_name}.id FROM {table_name}
                       WHERE
                       ({table_name}.name IN ({', '.join(['?']*len(values))}))
                       )
                    AND Book{table_name}.book_id = ?""", (*values, book_id))

            c.execute("UPDATE Books SET last_change = DATE('now', 'localtime') WHERE id = ?",
                      (book_id,))

        logger.debug("Removed '%s' from associated column '%s'", values, table_name)

    @classmethod
    def from_manga_extr_data(cls, mdb: 'MangaDB', data: 'MangaExtractorData') -> 'Book':
        # @Cleanup @Temporary convert lanugage in data to id
        language_id = mdb.get_language(data.language, create_unpresent=True)

        return cls(
            manga_db=mdb,
            title_eng=data.title_eng,
            title_foreign=data.title_foreign,
            language_id=language_id,
            pages=data.pages,
            status_id=data.status_id,
            nsfw=data.nsfw,
            note=data.note,
            category=data.category,
            collection=data.collection,
            groups=data.groups,
            artist=data.artist,
            parody=data.parody,
            character=data.character,
            tag=data.tag,
        )
