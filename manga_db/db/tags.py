import logging

from .. import extractor


logger = logging.getLogger(__name__)


def add_tags(db_con, tags):
    """Leaves committing changes to upper scope"""
    tags = [(tag, 1 if tag.startswith("li_") else 0) for tag in tags]
    # executemany accepts a list of tuples (one ? in sqlite code for every member of the tuples)
    # INSERT OR IGNORE -> ignore violation of unique constraint of column -> one has to be
    # unique otherwise new rows inserted
    # It is then possible to tell the database that you want to silently ignore records that
    # would violate such a constraint
    # theres also INSERT OR REPLACE -> replace if unique constraint violated
    c = db_con.executemany(
        "INSERT OR IGNORE INTO Tags(name, list_bool) VALUES(?, ?)", tags)
    # also possible:
    # INSERT INTO memos(id,text)
    # SELECT 5, 'text to insert' <-- values you want to insert
    # WHERE NOT EXISTS(SELECT 1 FROM memos WHERE id = 5 AND text = 'text to insert')

    return c


def add_tags_to_book(db_con, bid, tags):
    """Leaves committing changes to upper scope."""
    c = add_tags(db_con, tags)

    # create list with [(bid, tag), (bid, tag)...
    bid_tags = zip([bid] * len(tags), tags)
    # we can specify normal values in a select statment (that will also get used e.g. 5 as bid)
    # here using ? which will get replaced by bookid from tuple
    # then select value of tag_id column in Tags table where the name matches the current tag
    c.executemany("""INSERT OR IGNORE INTO BookTags(book_id, tag_id)
                     SELECT ?, Tags.tag_id FROM Tags
                     WHERE Tags.name = ?""", bid_tags)
    # ^^taken from example: INSERT INTO Book_Author (Book_ISBN, Author_ID)
    # SELECT Book.Book_ISBN, Book.Author_ID FROM Book GROUP BY Book.Book_ISBN, Book.Author_ID
    # --> GROUP BY to get distinct (no duplicate) values
    # ==> but better to use SELECT DISTINCT!!
    # The DISTINCT clause is an optional clause of the SELECT statement. The DISTINCT clause
    # allows you to remove the duplicate rows in the result set
    logger.debug("Added lists '%s' to book with id %d",
                 [tag for tag in tags if tag.startswith("li_")], bid)
    return c


def remove_tags_from_book_id(db_con, id_internal, tags):
    """Leave commiting changes to upper scope"""

    db_con.execute(f"""DELETE FROM BookTags WHERE BookTags.tag_id IN
                       (SELECT Tags.tag_id FROM Tags
                       WHERE (Tags.name IN ({', '.join(['?']*len(tags))})))
                       AND BookTags.book_id = ?""", (*tags, id_internal))
    logger.info("Tags %s were successfully removed from book with id \"%s\"",
                tags, id_internal)


def remove_tags_from_book(db_con, url, tags):
    """Leave commiting changes to upper scope"""
    extractor_cls = extractor.find(url)
    book_id = extractor_cls.book_id_from_url(url)

    # cant use DELETE FROM with multiple tables or multiple WHERE statements -> use
    # "WITH .. AS" (->Common Table Expressions, but they dont seem to work for me with
    # DELETE -> error no such table, but they work with SELECT ==> this due to acting like
    # temporary views and thus are READ-ONLY) or seperate subquery with "IN"
    # -> we can only use CTE/with for the subqueries/select statements
    # WITH bts AS (
    # SELECT BookTags.*
    # FROM BookTags, Tags
    # WHERE BookTags.book_id = 12
    # AND (Tags.name IN ('Yaoi'))
    # AND BookTags.tag_id = Tags.tag_id
    # )
    # DELETE
    # FROM BookTags
    # WHERE BookTags.book_id IN (select book_id FROM bts)
    # AND BookTags.tag_id IN (select tag_id FROM bts)

    # delete all rows that contain a tagid where the name col in Tags matches one of the
    # tags to delete and the book_id matches id of Books table where id_onpage matches our
    # book_id
    db_con.execute(f"""DELETE FROM BookTags WHERE BookTags.tag_id IN
                       (SELECT Tags.tag_id FROM Tags
                       WHERE (Tags.name IN ({', '.join(['?']*len(tags))})))
                       AND BookTags.book_id IN
                       (SELECT Books.id FROM Books
                       WHERE Books.id_onpage = ?
                       AND imported_from = ?)""", (*tags, book_id, extractor_cls.site_id))

    logger.info("Tags %s were successfully removed from book with url \"%s\"",
                tags, url)


def add_tags_to_book_cl(db_con, url, tags):
    book_id = book_id_from_url(url)
    c = db_con.execute(
        "SELECT Books.id FROM Books WHERE Books.id_onpage = ?",
        (book_id, ))
    id_internal = c.fetchone()[0]
    add_tags_to_book(db_con, id_internal, tags)
    logger.info("Tags %s were successfully added to book with url \"%s\"",
                tags, url)


def get_tags_by_book(db_con, _id):
    c = db_con.execute("""SELECT group_concat(Tags.name)
                          FROM Tags, BookTags bt, Books
                          WHERE bt.book_id = Books.id
                          AND Books.id = ?
                          AND bt.tag_id = Tags.tag_id
                          GROUP BY bt.book_id""", (_id, ))
    result = c.fetchone()
    return result[0] if result else None
