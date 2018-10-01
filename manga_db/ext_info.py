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
