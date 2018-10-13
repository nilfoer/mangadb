import logging
import datetime

from .db.row import DBRow
from .constants import CENSOR_IDS
from .extractor import SUPPORTED_SITES

logger = logging.getLogger(__name__)


class ExternalInfo(DBRow):

    DB_COL_HELPER = ("id", "url", "id_onpage", "imported_from", "upload_date", "uploader",
                     "censor_id", "rating", "ratings", "favorites", "downloaded", "last_update")

    NOT_NULL_COLS = ("url", "id_onpage", "imported_from", "upload_date", "censor_id")

    def __init__(self, manga_db, manga_db_entry, data, **kwargs):
        self.manga_db_entry = manga_db_entry
        self.id = None
        self.url = None
        self.id_onpage = None
        self.imported_from = None
        self.upload_date = None
        self.uploader = None
        self.censor_id = None
        self.rating = None
        self.ratings = None
        self.favorites = None
        # 0 or 1
        self.downloaded = None
        self.last_update = None

        # call to Base class init after assigning all the attributes !IMPORTANT!
        # if called b4 assigning the attributes the ones initalized with data
        # from the base class will be reset to None
        super().__init__(manga_db, data, **kwargs)

        if self.last_update is None:
            self.last_update = datetime.date.today()

    def __eq__(self, other):
        return all(self.id_onpage == other.id_onpage, self.imported_from == other.imported_from,
                   self.uploader == other.uploader, self.upload_date == other.upload_date,
                   self.downloaded == other.downloaded)

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def censorship(self):
        return CENSOR_IDS[self.censor_id]

    @censorship.setter
    def censorship(self, value):
        self.censor_id = CENSOR_IDS[value]

    @property
    def site(self):
        return SUPPORTED_SITES[self.imported_from]

    def update_from_dict(self, dic):
        for col in self.DB_COL_HELPER:
            # never update id, last_update
            if col in ("id", "last_update"):
                continue
            try:
                new = dic[col]
            except KeyError:
                pass
            else:
                setattr(self, col, new)

    def update_from_url(self, back_update=None):
        # TODO
        book, thumb = self.manga_db.retrieve_book_data(self.url)
        if book is None:
            return

    def save(self):
        # idea is that ExternalInfo only gets edited when also editing MangaDBEntry
        # and except downloaded everything else is edited by importing
        if self.id is None:
            if self.manga_db_entry is None or self.manga_db_entry.id is None:
                raise ValueError("ExternalInfo can only be saved with an id or MangaDBEntry.id!")
            return self._add_entry()
        else:
            # pass boolean if we have correct information for downloaded
            if self.downloaded is None:
                downloaded_null = True
            else:
                downloaded_null = False
            return self._update_entry(downloaded_null=downloaded_null)

    def _add_entry(self):
        if self.downloaded is None:
            self.downloaded = 0
        db_dict = self.export_for_db()
        cols = [col for col in self.DB_COL_HELPER if col != "id"]

        with self.manga_db.db_con:
            c = self.manga_db.db_con.execute(f"""
                    INSERT INTO ExternalInfo ({','.join(cols)})
                    VALUES ({','.join((f':{col}' for col in cols))}
                    )""", db_dict)
            self.id = c.lastrowid
            # insert connection in bridge table
            c.execute("""INSERT INTO ExternalInfoBooks(book_id, ext_info_id)
                         VALUES (?, ?)""", (self.manga_db_entry.id, self.id))
        return self.id, None

    def _update_entry(self, downloaded_null=None):
        db_con = self.manga_db.db_con
        # get previous value for downloaded and fav from db
        c = db_con.execute(
            "SELECT * FROM ExternalInfo WHERE id = ?",
            (self.id, ))
        row = c.fetchone()

        # if we dont have correct info on downloaded use value from db
        if downloaded_null:
            self.downloaded = row["downloaded"]

        field_change_str, changed_cols = self.diff_normal_cols(row)

        update_dic = self.export_for_db()

        # seems like book id on tsumino just gets replaced with newer uncensored or fixed version
        # -> check if upload_date uploader pages or tags (esp. uncensored + decensored) changed
        # => WARN to redownload book
        redl_on_field_change = ("censor_id", "uploader", "upload_date", "pages")
        if any((True for col in changed_cols if col in redl_on_field_change)):
            print("WARNIGN CHANGE")
            # automatic joining of strings only works inside ()
            field_change_str = (f"Please re-download \"{self.url}\", since the "
                                "change of the following fields suggest that someone has "
                                f"uploaded a new version:\n{field_change_str}")
            logger.warning(field_change_str)
            # set downloaded to 0 since its a diff version
            update_dic["downloaded"] = 0
        else:
            logger.info("Updating ExternalInfo with id '%d' with the following changes:"
                        "\n%s", self.id, field_change_str)

        with db_con:
            if changed_cols:
                c.execute(f"""UPDATE ExternalInfo SET
                              {','.join((f'{col} = :{col}' for col in changed_cols))}
                              WHERE id = :id""", update_dic)
            logger.info("Updated ext_info with url \"%s\" in database!", self.url)
        return self.id, field_change_str

    def remove(self):
        if self.id is None:
            logger.error("Remove was called on  an external info instance without id!")
            return None

        with self.manga_db.db_con:
            self.manga_db.db_con.execute("""
                DELETE
                FROM ExternalInfo
                WHERE
                id = ?""", (self.id, ))

        logger.info("Removed external info with id %d and url %s", self.id, self.url)

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()
                                  if attr != "manga_db_entry"))
        # dont use MangaDBEntry's repr otherwise the circular reference will spam the console
        mdb_entry_info = f"id: '{self.manga_db_entry.id}', title: '{self.manga_db_entry.title}'"
        return f"<ExternalInfo(manga_db_entry: 'MangaDBEntry({mdb_entry_info})', {selfdict_str})>"

    def to_export_string(self):
        # !! changes censor_id to sth human-readable (without lookin up the id that is)
        lines = []
        for col in self.DB_COL_HELPER:
            val = getattr(self, col)
            col_name = col
            if col == "censor_id":
                val = CENSOR_IDS[val]
                col_name = "censorship"
            elif col == "imported_from":
                val = SUPPORTED_SITES[val]
            lines.append(f"{col_name}: {val}")
        return "\n".join(lines)

    @staticmethod
    def set_downloaded_id(db_con, ext_info_id, intbool):
        with db_con:
            db_con.execute("UPDATE ExternalInfo SET downloaded = ? WHERE id = ?",
                           (intbool, ext_info_id))
