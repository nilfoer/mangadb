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


def remove_book(db_con, identifier, id_type):
    """Commits changes itself, since it also deletes book thumb anyway!"""
    book_id = None
    if id_type == "id_internal":
        id_col = "id"
    elif id_type == "id_onpage":
        id_col = "id_onpage"
    elif id_type == "url":
        book_id = book_id_from_url(identifier)
        id_col = "id_onpage"
        identifier = book_id
    else:
        logger.error("%s is an unsupported identifier type!", id_type)
        return

    if not book_id:
        c = db_con.execute(f"SELECT id_onpage FROM Books WHERE {id_col} = ?",
                           (identifier, ))
        book_id = c.fetchone()[0]

    with db_con:
        db_con.execute(f"""DELETE
                           FROM Books
                           WHERE
                           {id_col} = ?""", (identifier, ))

    # also delete book thumb
    os.remove(os.path.join("thumbs", str(book_id)))
    logger.debug("Removed thumb with path %s", f"thumbs/{book_id}")

    logger.info("Successfully removed book with %s: %s", id_type, identifier)
