import os
import sqlite3


def rate_manga(db_con, url, rating):
    """Leaves commiting changes to upper scope!!"""
    book_id = book_id_from_url(url)
    db_con.execute("UPDATE Books SET my_rating = ? WHERE id_onpage = ?",
                   (rating, book_id))
    logger.info("Successfully updated rating of book with id \"%s\" to \"%s\"",
                book_id, rating)


def get_books_low_usr_count(db_con, min_users=15, keep_row_fac=False):
    db_con.row_factory = sqlite3.Row
    c = db_con.cursor()
    if not keep_row_fac:
        db_con.row_factory = None

    c.execute("""SELECT id, id_onpage, url, rating_full FROM Books""")
    rows = c.fetchall()
    result = []
    for row in rows:
        # 4.44 (25 users / 665 favs)
        usrs = int(row["rating_full"].split("(")[1].split(" users /")[0])
        if usrs < min_users:
            result.append(row)

    return result
