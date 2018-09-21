import datetime


class MangaDBEntry:

    ROW_SET_HELPER = ("id", "title", "title_eng", "url", "id_onpage", "upload_date", "uploader",
                      "pages", "rating", "rating_full", "my_rating", "category", "collection",
                      "groups", "artist", "parody", "character", "last_change", "downloaded")
    def __init__(self, imported_from, data):
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
        self.tags = None
        if isinstance(data, dict):
            self.update_from_dict(data)
        else:
            self.update_from_row(data)
        if self.last_change is None:
            self.last_change = datetime.date.today()

    def update_from_dict(self, dic):
        self.__dict__.update(dic)

    def update_from_row(self, row):
        for i, key in enumerate(self.ROW_SET_HELPER):
            setattr(self, key, row[i])
