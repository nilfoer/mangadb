import logging
import datetime

from .db.row import DBRow
from .db.tags import remove_tags_from_book_id, add_tags_to_book, get_tags_by_book
from .constants import CENSOR_IDS, STATUS_IDS
from .ext_info import ExternalInfo

logger = logging.getLogger(__name__)


class MangaDBEntry(DBRow):
    """
    Fields of data that can have multiple values need to be of type list!!!
    """

    DB_COL_HELPER = ("id", "title", "title_eng", "title_foreign", "language_id", "pages",
                     "status_id", "my_rating", "note", "favorite", "last_change")

    # last_change and last_update get updated by trigger
    # dont update: language(inserted manually in sql statement)
    UPDATE_HELPER = ("title", "title_eng", "title_foreign", "url", "id_onpage",
                     "upload_date", "uploader", "pages", "rating",
                     "rating_full", "my_rating", "category", "collection",
                     "groups", "artist", "parody", "character", "note",
                     "downloaded", "favorite", "imported_from")

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
        self.category = None
        self.collection = None
        self.groups = None
        self.artist = None
        self.parody = None
        self.character = None
        self.lists = None
        self.tags = None
        self.ext_infos = None
        # --END-- Muliple values
        self.last_change = None
        self.note = None
        self.favorite = None

        # call to Base class init after assigning all the attributes !IMPORTANT!
        # if called b4 assigning the attributes the ones initalized with data
        # from the base class will be reset to None
        super().__init__(manga_db, data, **kwargs)

        if self.last_change is None:
            self.last_change = datetime.date.today()
        # id==None -> imported and not from DB
        if self.id is None:
            if self.lists:
                self.favorite = 1 if "li_best" in self.lists else 0
            else:
                self.favorite = 0

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

    def get_external_infos(self):
        if self.id is None:
            logger.warning("Couldn't get external info cause id is None")
            return
        if self.ext_infos is None:
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
            self.ext_infos = ext_infos
            return ext_infos
        else:
            return self.ext_infos()

    def export_for_db(self):
        """
        Returns a dict with all the attributes of self that are stored in the DB
        which are formatted for saving to the DB: e.g. lists but (user)lists and tags
        joined on ", "
        """
        result = {"lists": self.lists, "tags": self.tags}
        for attr in self.DB_COL_HELPER:
            val = getattr(self, attr)
            # col/attr where multiple values could occur is always a list
            if isinstance(val, list):
                if attr not in self.MULTI_VALUE_COL:
                    raise TypeError(f"Type was list for attr {attr} but its not a multi-value "
                                    f"column: {val}")
                result[attr] = list_to_string(val)
            else:
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

    def _update_manga_db_entry(self):
        # TODO update all cols?
        # TODO log changes
        # TODO remove lists, with def param remove_lists=False
        """Commits changes to db,
        lists will ONLY be ADDED not removed"""

        db_con = self.manga_db.db_con
        # get previous value for downloaded and fav from db
        c = db_con.execute(
            "SELECT downloaded, favorite, uploader, upload_date, pages FROM Books WHERE id = ?",
            (self.id, ))
        row = c.fetchone()
        # if dl/fav==1 update that to db else use value from db since it might be 1 there
        if not self.favorite:
            self.downloaded = row["downloaded"]
        if not self.favorite:
            self.favorite = row["favorite"]

        update_dic = self.export_for_db()

        # seems like book id on tsumino just gets replaced with newer uncensored or fixed version
        # -> check if upload_date uploader pages or tags (esp. uncensored + decensored) changed
        # => WARN to redownload book
        field_change_str = []
        # build line str of changed fields
        for key in ("uploader", "upload_date", "pages"):
            if row[key] != update_dic[key]:
                field_change_str.append(
                    f"Field \"{key}\" changed from \"{row[key]}\" "
                    f"to \"{update_dic[key]}\"!"
                )

        # check tags seperately due to using bridge table
        # get column tag names where tag_id in BookTags and Tags match and book_id in BookTags
        # is the book were looking for
        c.execute("""SELECT Tags.name
                     FROM BookTags bt, Tags
                     WHERE bt.tag_id = Tags.tag_id
                     AND bt.book_id = ?""", (self.id, ))
        # filter lists from tags first
        tags = set((tup[0] for tup in c.fetchall() if not tup[0].startswith("li_")))
        tags_page = set(self.tags)
        added_tags = None
        removed_on_page = None
        # compare sorted to see if tags changed, alternatively convert to set and add -> see
        # if len() changed
        if tags != tags_page:
            added_tags = tags_page - tags
            removed_on_page = tags - tags_page
            field_change_str.append(
                f"Field \"tags\" changed -> Added Tags: \"{', '.join(added_tags)}\"; "
                f"Removed Tags: \"{', '.join(removed_on_page)}\"!"
            )

        if field_change_str:
            field_change_str = '\n'.join(field_change_str)
            logger.warning(
                f"Please re-download \"{self.url}\", since the change of following fields suggest "
                f"that someone has uploaded a new version:\n{field_change_str}"
            )

        with db_con:
            c.execute(f"""UPDATE Books SET
                          {','.join((f'{col} = :{col}' for col in self.UPDATE_HELPER))},
                          language = (SELECT id FROM Languages WHERE name = :language)
                          WHERE id = :id""", update_dic)

            if removed_on_page:
                # remove tags that are still present in db but were removed on page
                remove_tags_from_book_id(db_con, self.id, removed_on_page)

            tags_lists_to_add = []
            if self.lists:
                # (micro optimization i know) list concat is faster with + compared with extend
                tags_lists_to_add = tags_lists_to_add + self.lists
            if added_tags:
                # converting set to list and then concat is faster than using s.union(list)
                tags_lists_to_add = tags_lists_to_add + list(added_tags)

            if tags_lists_to_add:
                # WARNING lists will only be added, not removed
                add_tags_to_book(db_con, self.id, tags_lists_to_add)

            logger.info("Updated book with url \"%s\" in database!", self.url)

        # c.lastrowid only works for INSERT/REPLACE
        return self.id, field_change_str

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"MangaDBEntry({selfdict_str})"
