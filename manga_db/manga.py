import os
import logging
import datetime

from .db.loading import load_instance
from .db.row import DBRow
from .db.column import Column, ColumnWithCallback
from .db.column_associated import AssociatedColumnMany
from .db.constants import Relationship
from .ext_info import ExternalInfo
from .constants import STATUS_IDS
from .db.util import joined_col_name_to_query_names
from .util import diff_update

logger = logging.getLogger(__name__)


class Book(DBRow):
    """
    Fields of data that can have multiple values need to be of type list!!!
    """

    TABLENAME = "Books"

    MANGA_TITLE_FORMAT = "{english} / {foreign}"

    id = Column(int, primary_key=True)
    title = Column(str, nullable=False)
    title_eng = ColumnWithCallback(str)
    title_foreign = ColumnWithCallback(str)
    language_id = Column(int, nullable=False)
    pages = Column(int, nullable=False)
    status_id = Column(int, nullable=False)
    my_rating = Column(float)
    category = AssociatedColumnMany("Category", Relationship.MANYTOMANY,
                                    assoc_table="BookCategory")
    collection = AssociatedColumnMany("Collection", Relationship.MANYTOMANY,
                                      assoc_table="BookCollection")
    groups = AssociatedColumnMany("Groups", Relationship.MANYTOMANY, assoc_table="BookGroups")
    artist = AssociatedColumnMany("Artist", Relationship.MANYTOMANY, assoc_table="BookArtist")
    parody = AssociatedColumnMany("Parody", Relationship.MANYTOMANY, assoc_table="BookParody")
    character = AssociatedColumnMany("Character", Relationship.MANYTOMANY,
                                     assoc_table="BookCharacter")
    list = AssociatedColumnMany("List", Relationship.MANYTOMANY,
                                assoc_table="BookList")
    tag = AssociatedColumnMany("Tag", Relationship.MANYTOMANY,
                               assoc_table="BookTag")
    ext_infos = AssociatedColumnMany("ExternalInfo", Relationship.ONETOMANY)
    last_change = Column(datetime.date)
    note = Column(str)
    favorite = Column(int, nullable=False)

    def __init__(
            self,
            manga_db,
            id=None,
            title=None,
            title_eng=None,
            title_foreign=None,
            language_id=None,
            pages=None,
            status_id=None,
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
            **kwargs):
        super().__init__(manga_db, **kwargs)
        self.id = id
        # dont change title yourself use reformat_title
        self.title = title
        self.title_eng = title_eng
        self.title_foreign = title_foreign
        # add callbacks to reformat title when either eng or foreign title changes
        Book.title_eng.add_callback("title_eng", self._title_change_callback)
        Book.title_foreign.add_callback("title_foreign", self._title_change_callback)
        self.language_id = language_id
        self.pages = pages
        self.status_id = status_id
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

        # load associated columns
        # TODO lazy loading
        self.update_assoc_columns()

        if self.last_change is None:
            self.set_last_change()

    def _apply_changes(self):
        for col, added_removed in self._changes.items():
            added, removed = added_removed
            if added:
                self._add_associated_column_values(col, tuple(added))
            if removed:
                self._remove_associated_column_values(col, tuple(removed))
        self._reset_changes()

    def set_last_change(self):
        self.last_change = datetime.date.today()
        return self.last_change

    @staticmethod
    def _title_change_callback(instance, name, before, after):
        instance.reformat_title(**{name: after})

    def reformat_title(self, title_eng=None, title_foreign=None):
        """Please dont assign title yourself only ever modify title_eng and title_foreign
        and use reformat_title to combine them"""
        # build title ourselves so title is the correct format
        if title_eng is None:
            title_eng = self.title_eng
        if title_foreign is None:
            title_foreign = self.title_foreign

        if title_eng and title_foreign:
            self.title = self.MANGA_TITLE_FORMAT.format(
                    english=title_eng, foreign=title_foreign)
        else:
            self.title = title_eng or title_foreign

    def update_from_dict(self, dic):
        """Values for ASSOCIATED_COLUMNS have to be of tuple/set/list
        Can also be used for book that is not in DB yet, since self._changes gets
        ignored and reset after adding"""
        # TODO validate input
        for col in self.COLUMNS:
            # never update id, last_change from dict, handle title and fav ourselves
            if col in ("id", "last_change", "title", "favorite"):
                continue
            try:
                new = dic[col]
            except KeyError:
                pass
            else:
                setattr(self, col, new)
        for col in self.ASSOCIATED_COLUMNS:
            if col == "ext_infos":
                continue
            try:
                new = dic[col]
            except KeyError:
                pass
            else:
                old = getattr(self, f"_{col}")
                setattr(self, f"_{col}", new)
                added, removed = diff_update(old, new)
                if added:
                    self._changes[col][0].update(added)
                if removed:
                    self._changes[col][1].update(removed)

        # TODO ext_infos
        fav = dic.get("favorite", None)
        if fav is not None:
            self.favorite = fav
        # build title ourselves so title is the correct format
        self.reformat_title()

    def update_ext_infos(self):
        self._ext_infos = self._fetch_external_infos()
        return self._ext_infos

    @property
    def avg_ext_rating(self):
        if self.ext_infos:
            ratings = [ei.rating for ei in self.ext_infos if ei.rating]
            return sum(ratings)/len(ratings)
        else:
            return None

    # @property
    # def ext_infos(self):
    #     if self.id is None:
    #         # initialized from extracotr dict
    #         if self._ext_infos and len(self._ext_infos) == 1:
    #             return self._ext_infos
    #         logger.warning("Couldn't get external info cause id is None")
    #         return
    #     if self._ext_infos is None:
    #         self.update_ext_infos()
    #     return self._ext_infos

    # # has to come after defining the property!
    # @ext_infos.setter
    # def ext_infos(self, ext_infos):
    #     if self._ext_infos is None:
    #         self._ext_infos = ext_infos
    #     else:
    #         self._ext_infos = [ei for ei in self._ext_infos if ei not in ext_infos] + ext_infos

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

    def update_assoc_columns(self):
        for col, val in self.get_associated_columns().items():
            setattr(self, col, val)

    def get_associated_columns(self):
        """
        Gets columns that are associated to this row by a bridge table from DB
        """
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
            self.language_id = self.manga_db.get_language(value)
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

    def save(self):
        """
        Save changes to DB
        """
        if self.id is None:
            bid = self.manga_db.get_book_id(self.title)
            if bid is None:
                logger.debug("Called save on Book with title '%s' which was not "
                             "in DB! Adding Book instead!", self.title)
                return self._add_entry()
        return self._update_manga_db_entry()

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
                    if self._ext_infos:
                        # also save ext_infos
                        for ext_info in self._ext_infos:
                            eid, outdated = ext_info.save()
                            if outdated:
                                # save ext_info id that triggered outdated warning
                                outdated_on_ei_ids.append(eid)
                    continue
                value = getattr(self, f"_{col}")
                if value is not None:
                    self._add_associated_column_values(col, value)

        logger.info("Added book with title \"%s\"  as id '%d' to database!", self.title, self.id)
        # also reset changes here since update_from_dict couldve been used which modifies _changes
        # and if book would be updated after adding it would write unnecessary changes to DB
        self._reset_changes()

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
        ext_info = next((ei for ei in self.ext_infos if ei.id == _id))
        if not ext_info:
            logger.error("No external info with id %d found!", _id)
            return None
        url = ext_info.url
        self._ext_infos = [ei for ei in self.ext_infos if ei.id != _id]
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

        c.executemany(f"""INSERT OR IGNORE INTO Book{table_name}(book_id, {bridge_col_name})
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

    def _update_manga_db_entry(self):
        """
        Commits changes to db
        Doesnt save changes in ext_infos
        """

        db_con = self.manga_db.db_con
        # @Speed remove getting data from db b4 update (replae with sth like
        # setters for normal cols that also log the changes)
        # get previous values from db
        c = db_con.execute(
            "SELECT * FROM Books WHERE id = ?",
            (self.id, ))
        row = c.fetchone()
        changed_str, changed_cols = self.diff_normal_cols(row)
        logger.info("Updating Book with id '%d' with the following changes:\n%s", self.id,
                    changed_str)

        update_dic = self.export_for_db()
        self.set_last_change()
        update_dic["last_change"] = self.last_change

        if changed_cols or self.assoc_col_changes():
            with db_con:
                # addd ['last_change'] so we always write last_change
                c.execute(f"""UPDATE Books SET
                              {','.join((f'{col} = :{col}' for col in
                               changed_cols + ['last_change']))}
                              WHERE id = :id""", update_dic)

                # update changes on ASSOCIATED_COLUMNS(except ext_infos)
                self._apply_changes()

            logger.info("Updated book with id %d in DB!", self.id)
            # c.lastrowid only works for INSERT/REPLACE
            return self.id, changed_str
        else:
            logger.debug("_update_manga_db_entry was called but there were no changes "
                         "for book with id %d", self.id)
            return self.id, None

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
            attr = getattr(self, f"_{col}")
            if attr is None:
                val = ""
            else:
                val = ", ".join(attr)
            lines.append(f"{col}: {val}")

        for ei in self._ext_infos:
            lines.append("\n")
            lines.append(f"External link:")
            lines.append(ei.to_export_string())

        return "\n".join(lines)

    def diff(self, manga_db_entry):
        # doesnt diff ext_infos
        changes = {}
        change_str = []
        for col in self.COLUMNS:
            val_self = getattr(self, col)
            val_other = getattr(manga_db_entry, col)
            if val_self != val_other:
                changes[col] = val_other
                change_str.append(f"Column '{col}' changed from '{val_self}' to '{val_other}'")
        for col in self.ASSOCIATED_COLUMNS:
            if col == "ext_infos":
                continue
            val_self = getattr(self, col)
            val_other = getattr(manga_db_entry, col)
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
    def set_favorite_id(db_con, book_id, fav_intbool):
        with db_con:
            db_con.execute("UPDATE Books SET favorite = ? WHERE id = ?",
                           (fav_intbool, book_id))

    @staticmethod
    def rate_book_id(db_con, book_id, rating):
        with db_con:
            db_con.execute("UPDATE Books SET my_rating = ? WHERE id = ?",
                           (rating, book_id))

    @staticmethod
    def add_assoc_col_on_book_id(db_con, book_id, col_name, values):
        table_name, bridge_col_name = joined_col_name_to_query_names(col_name)
        # values gotta be list/tuple of lists/tuples
        li_of_tup = [(val,) for val in values]
        with db_con:
            c = db_con.executemany(
                    f"INSERT OR IGNORE INTO {table_name}(name) VALUES (?)", li_of_tup)

            c.executemany(f"""INSERT OR IGNORE INTO Book{table_name}(book_id, {bridge_col_name})
                              SELECT ?, {table_name}.id
                              FROM {table_name}
                              WHERE {table_name}.name = ?""", zip([book_id] * len(values), values))
        logger.debug("Added '%s' to associated column '%s'", ", ".join(values), table_name)

    @staticmethod
    def remove_assoc_col_on_book_id(db_con, book_id, col_name, values):
        table_name, bridge_col_name = joined_col_name_to_query_names(col_name)
        with db_con:
            db_con.execute(f"""
                    DELETE FROM Book{table_name}
                    WHERE Book{table_name}.{bridge_col_name} IN
                       (
                       SELECT {table_name}.id FROM {table_name}
                       WHERE
                       ({table_name}.name IN ({', '.join(['?']*len(values))}))
                       )
                    AND Book{table_name}.book_id = ?""", (*values, book_id))
        logger.debug("Removed '%s' from associated column '%s'", values, table_name)
