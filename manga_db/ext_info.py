import logging
import datetime

from .db.row import DBRow
from .db.column import Column
from .db.column_associated import AssociatedColumnOne
from .db.constants import Relationship
from .constants import CENSOR_IDS
from .extractor import SUPPORTED_SITES

logger = logging.getLogger(__name__)


class ExternalInfo(DBRow):

    id = Column(int, primary_key=True)
    book_id = Column(int, nullable=False)
    url = Column(str, nullable=False)
    id_onpage = Column(int, nullable=False)
    imported_from = Column(int, nullable=False)
    upload_date = Column(datetime.date, nullable=False)
    uploader = Column(str)
    censor_id = Column(int, nullable=False)
    rating = Column(float)
    ratings = Column(int)
    favorites = Column(int)
    downloaded = Column(int)
    last_update = Column(datetime.date)
    outdated = Column(int)
    book = AssociatedColumnOne("Books", Relationship.MANYTOONE)

    def __init__(
                self, manga_db, book,
                id=None,
                book_id=None,
                url=None,
                id_onpage=None,
                imported_from=None,
                upload_date=None,
                uploader=None,
                censor_id=None,
                rating=None,
                ratings=None,
                favorites=None,
                downloaded=None,
                last_update=None,
                outdated=None,
                **kwargs):
        super().__init__(manga_db, **kwargs)
        self.book = book
        self.id = id
        self.url = url
        self.id_onpage = id_onpage
        self.imported_from = imported_from
        self.upload_date = upload_date
        self.uploader = uploader
        self.censor_id = censor_id
        self.rating = rating
        self.ratings = ratings
        self.favorites = favorites
        self.downloaded = downloaded
        self.last_update = last_update
        self.outdated = outdated

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
        for col in self.COLUMNS:
            # never update id, last_update
            if col in ("id", "last_update"):
                continue
            try:
                new = dic[col]
            except KeyError:
                pass
            else:
                setattr(self, col, new)

    def update_from_url(self, force=False):
        if not self.id and self.book:
            logger.info("Cant update external info without id and assoicated book!")
            return "id_or_book_missing", None
        # TODO mb propagate updates to Book?
        book, ext_info, _ = self.manga_db.retrieve_book_data(self.url)
        if book is None:
            return "no_data", None
        if book.title != self.book.title:
            logger.warning("Title at URL of external info doesnt match title of associated "
                           "book! Aborting update! Use force=True to force update!\n"
                           "URL: %s\nTitle of associated book: %s\nTitle at URL: %s".
                           self.url, self.book.title, book.title)
            if not force:
                return "title_mismatch", None
        for col in self.COLUMNS:
            if col == "id":
                continue
            setattr(self, col, getattr(ext_info, col))
        return "updated", book

    def save(self):
        # idea is that ExternalInfo only gets edited when also editing Book
        # and except downloaded everything else is edited by importing
        if self.id is None:
            if self.book is None or self.book.id is None:
                raise ValueError("ExternalInfo can only be saved with an id or Book.id!")
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
        if self.outdated is None:
            self.outdated = 0

        # check if id_onpage,imported_from is already in db and warn
        # since it prob means that there is a new version available on the site
        c = self.manga_db.db_con.execute("""
                SELECT ei.id, ei.url
                FROM ExternalInfo ei
                WHERE ei.id_onpage = ?
                AND ei.imported_from = ?""", (self.id_onpage, self.imported_from))
        outdated = c.fetchall()
        if outdated:
            logger.warning("External info(s) with (id_onpage, imported_from): "
                           "(%d, %d) were already in DB which means it's/their "
                           "link(s) are outdated! Probably means a new version is "
                           "available!:\n%s", self.id_onpage, self.imported_from,
                           "\n".join((o[1] for o in outdated)))
        else:
            outdated = None

        db_dict = self.export_for_db()
        cols = [col for col in self.COLUMNS if col != "id"]

        with self.manga_db.db_con:
            c = self.manga_db.db_con.execute(f"""
                    INSERT INTO ExternalInfo ({','.join(cols)})
                    VALUES ({','.join((f':{col}' for col in cols))}
                    )""", db_dict)
            self.id = c.lastrowid
            # insert connection in bridge table
            c.execute("""INSERT INTO ExternalInfoBooks(book_id, ext_info_id)
                         VALUES (?, ?)""", (self.book.id, self.id))
            if outdated:
                # set invalid_link on external infos with same id_onpage,imported_from
                # save to insert them like this since vals are from the db
                c.execute(f"""
                    UPDATE ExternalInfo SET outdated = 1
                    WHERE ExternalInfo.id in ({', '.join((str(o[0]) for o in outdated))})""")

        return self.id, outdated

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

    def get_outdated_links_same_pageid(self):
        c = self.manga_db.db_con.execute("""
                SELECT Books.id, ei.url
                FROM Books, ExternalInfo ei, ExternalInfoBooks eib
                WHERE eib.book_id = Books.id
                AND eib.ext_info_id = ei.id
                AND ei.id_onpage = ?
                AND ei.imported_from = ?
                AND ei.outdated = 1
                """, (self.id_onpage, self.imported_from))
        rows = c.fetchall()
        return rows if rows else None

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()
                                  if attr != "book"))
        # dont use Book's repr otherwise the circular reference will spam the console
        book_info = f"id: '{self.book.id}', title: '{self.book.title}'"
        return f"<ExternalInfo(book: 'Book({book_info})', {selfdict_str})>"

    def to_export_string(self):
        # !! changes censor_id to sth human-readable (without lookin up the id that is)
        lines = []
        for col in self.COLUMNS:
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
