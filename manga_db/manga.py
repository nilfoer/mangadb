import datetime


class MangaDBEntry:

    ROW_SET_HELPER = ("id", "title", "title_eng", "url", "id_onpage", "upload_date", "uploader",
                      "pages", "rating", "rating_full", "my_rating", "category", "collection",
                      "groups", "artist", "parody", "character", "last_change", "downloaded")

    def __init__(self, manga_db, imported_from, data, **kwargs):
        self.manga_db = manga_db
        self.imported_from = imported_from
        self.id = None
        self.id_onpage = None
        self.title = None
        self.title_eng = None
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
        # TODO apply changes first like comma-sep character string to list etc.
        self.__dict__.update(dic)

    def _update_from_row(self, row):
        for i, key in enumerate(self.ROW_SET_HELPER):
            setattr(self, key, row[i])

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"MangaDBEntry({selfdict_str})"

    def add_to_db(self):
        pass
