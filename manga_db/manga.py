import logging
import datetime

from .db.tags import remove_tags_from_book_id, add_tags_to_book
from .db.util import list_to_string, string_to_list

logger = logging.getLogger(__name__)


class MangaDBEntry:
    """
    Fields of data that can have multiple values need to be of type list!!!
    """

    DB_COL_HELPER = ("id", "title", "title_eng", "title_foreign", "url", "id_onpage", "upload_date",
                     "uploader", "pages", "rating", "rating_full", "my_rating", "category",
                     "collection", "groups", "artist", "parody", "character", "last_change",
                     "downloaded", "favorite", "imported_from")
    # according to html on tsumino
    # when displayed as anchor there can be multiple
    # if the text is directly in the div there is only one value
    MULTI_VALUE_COL = ("category", "collection", "groups", "artist", "parody", "character")

    def __init__(self, manga_db, imported_from, data, **kwargs):
        self.manga_db = manga_db
        self.imported_from = imported_from
        self.id = None
        self.id_onpage = None
        self.title = None
        self.title_eng = None
        self.title_foreign = None
        self.url = None
        self.upload_date = None
        self.uploader = None
        self.pages = None
        self.rating = None
        # split this up?
        self.rating_full = None
        self.my_rating = None
        self.category = None
        self.collection = None
        self.groups = None
        self.artist = None
        self.parody = None
        self.character = None
        self.last_change = None
        self.downloaded = None
        self.favorite = None
        self.lists = None
        self.tags = None
        if isinstance(data, dict):
            self._from_dict(data)
        else:
            self._from_row(data)
        if self.last_change is None:
            self.last_change = datetime.date.today()
        # so we can pass e.g. tag-list that isnt included in slite3.Row as kwarg
        for k, v in kwargs.items():
            setattr(self, k, v)
        # id==None -> imported and not from DB
        if self.id is None and self.lists:
            self.downloaded = 1 if "li_downloaded" in self.lists else 0
            self.favorite = 1 if "li_best" in self.lists else 0

    def _from_dict(self, dic):
        self.__dict__.update(dic)

    def _from_row(self, row):
        for key in self.DB_COL_HELPER:
            val = row[key]
            if key in self.MULTI_VALUE_COL:
                val = string_to_list(val)
            setattr(self, key, val)

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
                result[attr] = list_to_string(val)
            else:
                result[attr] = val
        return result

    def update_in_db(self):
        if self.id is None:
            c = self.manga_db.db_con.execute("SELECT id FROM Books WHERE id_onpage = ?"
                                             "AND imported_from = ?",
                                             (self.id_onpage, self.imported_from))
            bid = c.fetchone()
            if bid is None:
                logger.debug("Called update on Book with (id_onpage,imported_from)"
                             "(%d,%d) which was not in DB! Addin Book instead!",
                             self.id_onpage, self.imported_from)

                return self.manga_db.add_book(self)
        return self._update_manga_db_entry()

    def _update_manga_db_entry(self):
        """Commits changes to db,
        lists will ONLY be ADDED not removed"""

        db_con = self.manga_db.db_con
        # get previous value for downloaded and fav from db
        c = db_con.execute(
            "SELECT downloaded, favorite, uploader, upload_date, pages FROM Books WHERE id = ?",
            (self.id, ))
        row = c.fetchone()
        # if dl/fav==1 update that to db if its 0 else use value from db since
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
        tags = set(
            (tup[0] for tup in c.fetchall() if not tup[0].startswith("li_")))
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
            # dont update: title = :title, title_eng = :title_eng,
            c.execute("""UPDATE Books SET
                         upload_date = :upload_date, uploader = :uploader, pages = :pages,
                         rating = :rating, rating_full = :rating_full, category = :category,
                         collection = :collection, groups = :groups, artist = :artist,
                         parody = :parody, character = :character, imported_from = :imported_from,
                         last_change = :last_change, downloaded = :downloaded, favorite = :favorite
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
