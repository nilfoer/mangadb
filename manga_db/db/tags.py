import logging

from .. import extractor


logger = logging.getLogger(__name__)


def add_tags_to_book_cl(db_con, url, tags):
    book_id = book_id_from_url(url)
    c = db_con.execute(
        "SELECT Books.id FROM Books WHERE Books.id_onpage = ?",
        (book_id, ))
    id_internal = c.fetchone()[0]
    add_tags_to_book(db_con, id_internal, tags)
    logger.info("Tags %s were successfully added to book with url \"%s\"",
                tags, url)
