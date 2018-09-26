import datetime

from .db.util import list_to_string, string_to_list


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
            self._update_from_dict(data)
        else:
            self._update_from_row(data)
        if self.last_change is None:
            self.last_change = datetime.date.today()
        # so we can pass e.g. tag-list that isnt included in slite3.Row as kwarg
        for k, v in kwargs.items():
            setattr(self, k, v)

    def _update_from_dict(self, dic):
        self.__dict__.update(dic)

    def _update_from_row(self, row):
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

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"MangaDBEntry({selfdict_str})"
