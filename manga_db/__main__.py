import logging

from .manga_db import MangaDB
from .db.export import export_csv_from_sql

logger = logging.getLogger(__name__)


try:
    mdb = MangaDB("./", "./manga_db.sqlite")
except FileNotFoundError:
    logger.error("Couldn't find manga_db.sqlite in current working directory")
else:
    pass
