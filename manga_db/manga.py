import logging
import datetime

from .db.row import DBRow
from .ext_info import ExternalInfo
from .constants import STATUS_IDS

logger = logging.getLogger(__name__)


class MangaDBEntry(DBRow):
    """
    Fields of data that can have multiple values need to be of type list!!!
    """

    DB_COL_HELPER = ("id", "title", "title_eng", "title_foreign", "language_id", "pages",
                     "status_id", "my_rating", "note", "favorite", "last_change")

    JOINED_COLUMNS = ('category', 'collection', 'groups', 'artist', 'parody', 'character',
                      'lists', 'tags', 'ext_infos')

    def __init__(self, manga_db, data, **kwargs):
        self.id = None
        self.title = None
        self.title_eng = None
        self.title_foreign = None
        self.language_id = None
        self.pages = None
        self.status_id = None
        self.my_rating = None
        # --START-- Muliple values, mb as properties?
        self._category = None
        self._collection = None
        self._groups = None
        self._artist = None
        self._parody = None
        self._character = None
        self._lists = None
        self._tags = None
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
        self._init_add_assoc_column_methods()

        # call to Base class init after assigning all the attributes !IMPORTANT!
        # if called b4 assigning the attributes the ones initalized with data
        # from the base class will be reset to None
        super().__init__(manga_db, data, **kwargs)

        if self.last_change is None:
            self.last_change = datetime.date.today()

    def _from_row(self, row):
        for key in self.DB_COL_HELPER:
            setattr(self, key, row[key])
        for col, val in self.get_associated_columns().items():
            setattr(self, "_" + col, val)

    @classmethod
    def _init_add_assoc_column_methods(cls):
        # ext_infos handled seperately
        for col in cls.JOINED_COLUMNS:
            if col == "ext_infos":
                continue
            # addition func needed due to scoping of for block
            # otherwise all funcs would only use the last value for col
            cls.gen_add_assoc_col_f(cls, col)

    @staticmethod
    def gen_add_assoc_col_f(cls, col):
        # generate function that adds to col and logs the changes
        def add_to_assoc_col(self, value):
            self._changes[col][0].add(value)
            col_li = getattr(self, f"_{col}")
            if col_li is None:
                # col_li =.. doesnt work since its just None and not a mutable type
                setattr(self, f"_{col}", [value])
            else:
                col_li.append(value)
            return getattr(self, col)
        # set function on class so its callable with self.add_{col}
        # needs to be added to class, doesnt work with adding to self
        setattr(cls, f"add_{col}", add_to_assoc_col)

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
    def tags(self):
        return self._tags

    @property
    def lists(self):
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
            self._ext_infos = self._fetch_external_infos()
        return self._ext_infos

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
        Gets columns that are associated to this row by a bridge table
        """
        result = {
            "lists": None,
            "tags": None,
            "category": None,
            "collection": None,
            "groups": None,
            "artist": None,
            "parody": None,
            "character": None
            }

        # split tags and lists
        result["tags"] = self._fetch_associated_column("Tag", "tag_id")
        result["lists"] = self._fetch_associated_column("List", "list_id")
        result["category"] = self._fetch_associated_column("Category", "category_id")
        result["collection"] = self._fetch_associated_column("Collection", "collection_id")
        result["groups"] = self._fetch_associated_column("Groups", "group_id")
        result["artist"] = self._fetch_associated_column("Artist", "artist_id")
        result["parody"] = self._fetch_associated_column("Parody", "parody_id")
        result["character"] = self._fetch_associated_column("Character", "character_id")
        result["ext_infos"] = self._fetch_external_infos()
        return result

    def _fetch_associated_column(self, table_name, bridge_col_name):
        c = self.manga_db.db_con.execute(f"""SELECT group_concat(x.name, ';')
                                             FROM {table_name} x, Book{table_name} bx, Books
                                             WHERE bx.book_id = Books.id
                                             AND Books.id = ?
                                             AND bx.{bridge_col_name} = x.id
                                             GROUP BY bx.book_id""", (self.id, ))
        result = c.fetchone()
        return result[0].split(";") if result else []

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

    def export_for_db(self):
        """
        Returns a dict with all the attributes of self that are stored in the row directly
        """
        result = {"lists": self.lists, "tags": self.tags}
        for attr in self.DB_COL_HELPER:
            val = getattr(self, attr)
            # col/attr where multiple values could occur is always a list
            result[attr] = val
        return result

    def save(self):
        """
        Save changes to DB
        """
        if self.id is None:
            bid = self.manga_db.get_book_id_unique((self.id_onpage, self.imported_from),
                                                   self.title)
            if bid is None:
                logger.debug("Called update on Book with (id_onpage,imported_from)"
                             "(%d,%d) which was not in DB! Addin Book instead!",
                             self.id_onpage, self.imported_from)

                return self.manga_db.add_book(self)
        return self._update_manga_db_entry()

    def _add_associated_column_values(self, table_name, bridge_col_name, values):
        c = self.db_con.executemany(f"INSERT OR IGNORE INTO {table_name}(name) VALUES (?)",
                                    values)
        c.executemany(f"""INSERT OR IGNORE INTO Book{table_name}(book_id, {bridge_col_name})
                          SELECT ?, {table_name}.id
                          FROM {table_name}
                          WHERE {table_name}.name = ?""", (zip([self.id] * len(values), values)))
        logger.debug("Added '%s' to associated column '%s'", ", ".join(values), table_name)

    def _remove_associated_column_values(self, table_name, bridge_col_name, values):
        self.db_con.executemany(f"""
                DELETE FROM Book{table_name}
                WHERE Book{table_name}.tag_id IN
                   (
                   SELECT {table_name}.id FROM {table_name}
                   WHERE
                   ({table_name}.name IN ({', '.join(['?']*len(values))}))
                   )
                AND Book{table_name}.book_id = ?""", (*values, self.id))
        logger.debug("Removed '%s' from associated column '%s'", values, table_name)

    def diff_normal_cols(self, row):
        changed_str = []
        changed_cols = []
        for col in self.DB_COL_HELPER:
            if col == "id":
                assert self.id == row["id"]
                continue
            self_attr = getattr(self, col)
            if row[col] != self_attr:
                changed_str.append(f"Column '{col}' changed from '{self_attr}' to '{row[col]}'")
                changed_cols.append(col)
        return "\n".join(changed_str), changed_cols

    def _update_manga_db_entry(self):
        # TODO update all cols?
        # TODO remove lists, with def param remove_lists=False
        """Commits changes to db,
        lists will ONLY be ADDED not removed"""

        db_con = self.manga_db.db_con
        # get previous value for downloaded and fav from db
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
            c.execute(f"""UPDATE Books SET
                          {','.join((f'{col} = :{col}' for col in changed_cols))}
                          WHERE id = :id""", update_dic)

            # update changes on JOINED_COLUMNS(except ext_infos)
            for col, added_removed in self._changes.items():
                added, removed = added_removed
                # TODO

        # c.lastrowid only works for INSERT/REPLACE
        return self.id, field_change_str

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"MangaDBEntry({selfdict_str})"
