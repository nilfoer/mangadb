import logging
import datetime

from .db.row import DBRow
from .constants import CENSOR_IDS

logger = logging.getLogger(__name__)


class ExternalInfo(DBRow):

    DB_COL_HELPER = ("id", "url", "id_onpage", "imported_from", "upload_date", "uploader",
                     "censor_id", "rating", "ratings", "favorites", "downloaded", "last_update")

    def __init__(self, manga_db_entry, data, **kwargs):
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
        self.downloaded = None
        self.last_update = None

        # call to Base class init after assigning all the attributes !IMPORTANT!
        # if called b4 assigning the attributes the ones initalized with data
        # from the base class will be reset to None
        super().__init__(manga_db_entry.manga_db, data, **kwargs)

        if self.last_update is None:
            self.last_update = datetime.date.today()

    @property
    def censorship(self):
        return CENSOR_IDS[self.censor_id]

    @censorship.setter
    def status(self, value):
        self.censor_id = CENSOR_IDS[value]

    def _update_entry(self):
        # @CopyPasta
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

