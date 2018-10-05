import logging
import datetime

from .db.row import DBRow
from .ext_info import ExternalInfo
from .constants import STATUS_IDS
from .db.util import joined_col_name_to_query_names

logger = logging.getLogger(__name__)


class MangaDBEntry(DBRow):
    """
    Fields of data that can have multiple values need to be of type list!!!
    """

    DB_COL_HELPER = ("id", "title", "title_eng", "title_foreign", "language_id", "pages",
                     "status_id", "my_rating", "note", "favorite", "last_change")

    JOINED_COLUMNS = ('category', 'collection', 'groups', 'artist', 'parody', 'character',
                      'list', 'tag', 'ext_infos')

    # cols that cant be NULL (and arent set in __init__)
    NOT_NULL_COLS = ("title", "language_id", "pages", "status_id")

    MANGA_TITLE_FORMAT = "{english} / {foreign}"

    def __init__(self, manga_db, data, **kwargs):
        self.id = None
        self.title = None
        self.title_eng = None
        self.title_foreign = None
        self.language_id = None
        self.pages = None
        self.status_id = None
        self.my_rating = None
        # --START-- Muliple values
        self._category = None
        self._collection = None
        self._groups = None
        self._artist = None
        self._parody = None
        self._character = None
        self._list = None
        self._tag = None
        self._ext_infos = None
        # --END-- Muliple values
        self.last_change = None
        self.note = None
        self.favorite = None
        # assoc column: (set of adds, sets of removes)
        self._changes = {col: (set(), set()) for col in self.JOINED_COLUMNS
                         if col != "ext_infos"}
        # dynamically create functions that add/remove to joined cols
        # and log the changes
        self._init_assoc_column_methods()

        # call to Base class init after assigning all the attributes !IMPORTANT!
        # if called b4 assigning the attributes the ones initalized with data
        # from the base class will be reset to None
        super().__init__(manga_db, data, **kwargs)

        if self.last_change is None:
            self.last_change = self.set_last_change()
        if self.favorite is None:
            self.favorite = 0

    def _from_row(self, row):
        for key in self.DB_COL_HELPER:
            setattr(self, key, row[key])
        for col, val in self.get_associated_columns().items():
            setattr(self, "_" + col, val)

    def _from_dict(self, dic):
        filtered = self.filter_dict(dic)
        # need to update "private" _assoc-col-name, not the properties assoc-col-name
        # key_a if x else key_b: value -> if else on line only one value (or tuple, list etc)
        self.__dict__.update({f"_{col}" if col in self.JOINED_COLUMNS else col: val
                              for col, val in filtered.items()})

    def set_last_change(self):
        self.last_change = datetime.date.today()
        return self.last_change

    def update_from_dict(self, dic):
        """Values for JOINED_COLUMNS have to be of tuple/set/list"""
        # TODO validate input
        for col in self.DB_COL_HELPER:
            # never update id, last_change from dict, handle title and fav ourselves
            if col in ("id", "last_change", "title", "favorite"):
                continue
            try:
                new = dic[col]
            except KeyError:
                pass
            else:
                setattr(self, col, new)
        for col in self.JOINED_COLUMNS:
            if col == "ext_infos":
                continue
            try:
                new = dic[col]
            except KeyError:
                pass
            else:
                old = set(getattr(self, f"_{col}"))
                setattr(self, f"_{col}", new)
                new = set(new)
                if new == old:
                    continue
                added = new - old
                self._changes[col][0].update(added)
                removed = old - new
                self._changes[col][1].update(removed)

        # TODO ext_infos
        fav = dic.get("favorite", None)
        if fav is not None:
            self.favorite = fav
        # build title ourselves so title is the correct format
        if self.title_eng and self.title_foreign:
            self.title = self.MANGA_TITLE_FORMAT.format(
                    english=self.title_eng, foreign=self.title_foreign)
        else:
            self.title = self.title_eng or self.title_foreign

    @classmethod
    def _init_assoc_column_methods(cls):
        # ext_infos handled seperately
        for col in cls.JOINED_COLUMNS:
            if col == "ext_infos":
                continue
            # addition func needed due to scoping of for block
            # otherwise all funcs would only use the last value for col
            cls.gen_add_assoc_col_f(cls, col)
            cls.gen_remove_assoc_col_f(cls, col)

    @staticmethod
    def gen_add_assoc_col_f(cls, col):
        # generate function that adds to col and logs the changes
        def add_to_assoc_col(self, value):
            # always log change even if we dont add it to the list later (since val might not
            # be in db etc.)
            self._changes[col][0].add(value)
            col_li = getattr(self, f"_{col}")
            if col_li is None:
                # col_li =.. doesnt work since its just None and not a mutable type
                setattr(self, f"_{col}", [value])
            else:
                # @Speed switch to sets if this gets too slow
                if value not in col_li:
                    col_li.append(value)
            return getattr(self, col)
        # set function on class so its callable with self.add_{col}
        # needs to be added to class, doesnt work with adding to self
        setattr(cls, f"add_{col}", add_to_assoc_col)

    @staticmethod
    def gen_remove_assoc_col_f(cls, col):
        # generate function that removes from col and logs the changes
        def remove_from_assoc_col(self, value):
            self._changes[col][1].add(value)
            col_li = getattr(self, f"_{col}")
            # col_li is None doesnt matter for removing (since it might be present in db)
            # also removing sth thats not present in the list doesnt matter
            if col_li is not None:
                # list comprehension more efficient (only downside it creates a
                # new list instaed of changing the old one
                setattr(self, f"_{col}", [x for x in col_li if x != value])
            return getattr(self, col)
        setattr(cls, f"remove_{col}", remove_from_assoc_col)

    @property
    def category(self):
        return self._category

    @property
    def collection(self):
        return self._collection

    @property
    def groups(self):
        return self._groups

    @property
    def artist(self):
        return self._artist

    @property
    def parody(self):
        return self._parody

    @property
    def character(self):
        return self._character

    @property
    def tag(self):
        return self._tag

    @property
    def list(self):
        return self._list

    def update_ext_infos(self):
        self._ext_infos = self._fetch_external_infos()
        return self._ext_infos

    @property
    def ext_infos(self):
        if self.id is None:
            logger.warning("Couldn't get external info cause id is None")
            return
        if self._ext_infos is None:
            self.update_ext_infos()
        return self._ext_infos

    # has to come after defining the property!
    @ext_infos.setter
    def ext_infos(self, ext_infos):
        if self._ext_infos is None:
            self._ext_infos = ext_infos
        else:
            self._ext_infos = [ei for ei in self._ext_infos if ei not in ext_infos] + ext_infos

    def _fetch_external_infos(self):
        ext_infos = []
        c = self.manga_db.db_con.execute("""
                        SELECT ei.*
                        FROM ExternalInfo ei, ExternalInfoBooks eib, Books
                        WHERE Books.id = eib.book_id
                        AND ei.id = eib.ext_info_id
                        AND Books.id = ?""", (self.id,))
        for row in c.fetchall():
            ei = ExternalInfo(self, row)
            ext_infos.append(ei)
        return ext_infos

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

    @property
    def language(self):
        return self.manga_db.language_map[self.language_id]

    @language.setter
    def language(self, value):
        if isinstance(value, str):
            self.manga_db.add_language(value)
            self.language_id = self.manga_db.language_map[value]
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
                logger.debug("Called update on Book with title '%s' which was not "
                             "in DB! Adding Book instead!", self.title)
                bid, _ = self._add_entry()
                self.id = bid
                return self.id, None
        return self._update_manga_db_entry()

    def _add_entry(self):
        """Commits changes to db"""
        db_dict = self.export_for_db()
        cols = [col for col in self.DB_COL_HELPER if col != "id"]

        with self.manga_db.db_con:
            c = self.manga_db.db_con.execute(f"""
                    INSERT INTO Books ({','.join(cols)})
                    VALUES ({','.join((f':{col}' for col in cols))}
                    )""", db_dict)
            self.id = c.lastrowid

            for col in self.JOINED_COLUMNS:
                if col == "ext_infos" and self._ext_infos:
                    # also save ext_infos
                    for ext_info in self._ext_infos:
                        ext_info.save()
                    continue
                value = getattr(self, f"_{col}")
                if value is not None:
                    self._add_associated_column_values(col, value)

        logger.info("Added book with title \"%s\" to database!", self.title)

        return self.id, None

    def remove(self):
        """Commits changes itself, since it also deletes book thumb anyway!"""
        # TODO
        # triggers will delete all joined cols when associated manga_db_entry is deleted
        if not book_id:
            c = db_con.execute(f"SELECT id_onpage FROM Books WHERE {id_col} = ?",
                               (identifier, ))
            book_id = c.fetchone()[0]

        with db_con:
            db_con.execute(f"""DELETE
                               FROM Books
                               WHERE
                               {id_col} = ?""", (identifier, ))

        # also delete book thumb
        os.remove(os.path.join("thumbs", str(book_id)))
        logger.debug("Removed thumb with path %s", f"thumbs/{book_id}")

        logger.info("Successfully removed book with %s: %s", id_type, identifier)

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

        # if fav==1 update that to db else use value from db since it might be 1 there
        if not self.favorite:
            self.favorite = row["favorite"]

        update_dic = self.export_for_db()

        with db_con:
            if changed_cols:
                c.execute(f"""UPDATE Books SET
                              {','.join((f'{col} = :{col}' for col in changed_cols))}
                              WHERE id = :id""", update_dic)

            # update changes on JOINED_COLUMNS(except ext_infos)
            for col, added_removed in self._changes.items():
                added, removed = added_removed
                if added:
                    self._add_associated_column_values(col, tuple(added))
                if removed:
                    self._remove_associated_column_values(col, tuple(removed))

        logger.info("Updated book with id %d in DB!", self.id)
        # c.lastrowid only works for INSERT/REPLACE
        return self.id, changed_str

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"MangaDBEntry({selfdict_str})"

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
