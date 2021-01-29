import sqlite3
from ...extractor import SUPPORTED_SITES
from ...constants import STATUS_IDS, LANG_IDS

date = '2021-01-24'
requires_foreign_keys_off = False


def upgrade(db_con, db_filename):
    c = db_con.cursor()

    # so we can del rows with foreign key constraints and re-insert them
    c.execute("PRAGMA foreign_keys = OFF")

    #
    # add nsfw column to Books
    #
    c.execute("ALTER TABLE Books ADD COLUMN nsfw INTEGER NOT NULL DEFAULT 0")
    # assume previous imports from nhentai or tsumino are nsfw
    c.execute("""
    UPDATE Books SET nsfw = 1 WHERE (
        SELECT imported_from FROM ExternalInfo ei
        WHERE ei.book_id = Books.id
    ) IS NOT NULL""")

    #
    # add status 'Cancelled'
    #
    c.execute("INSERT INTO Status(id, name) VALUES (?, ?)", (STATUS_IDS['Cancelled'], 'Cancelled'))
    assert c.execute("SELECT * FROM Status").fetchall() == [
            (_id, name) for _id, name in STATUS_IDS.items() if type(_id) is int]

    #
    # add new default languages
    #
    id_lang = [(i, v) for i, v in LANG_IDS.items() if type(i) is int]
    default_langs = {name for name in LANG_IDS if type(name) is str}
    # re-insert languages that were added by the user beyond our reserved languages
    # and update the respective foreign keys in the Books table
    lang_db = c.execute("SELECT * FROM Languages").fetchall()
    if len(lang_db) > 1:
        max_lang_id = max(id_lang, key=lambda x: x[0])[0]
        new_id_start = max_lang_id + 1
        for i, row in enumerate(lang_db[1:]):
            # account for custom language being in default_langs
            if row[1] in default_langs:
                new_id = LANG_IDS[row[1]]
            else:
                new_id = new_id_start + i
                # del old otherwise we violate unique constraint
                c.execute("DELETE FROM Languages WHERE id = ?", (row[0],))
                c.execute("INSERT INTO Languages(id, name) VALUES (?, ?)", (new_id, row[1]))

            # update foreign keys in Books table
            c.execute("UPDATE Books SET language_id = ? WHERE language_id = ?", (new_id, row[0]))

        # delete all language entries but the previous default (1, 'English')
        # and re-inserted user langs
        c.execute("DELETE FROM Languages WHERE id > 1 AND id <= 35")

    # skip 'English'
    c.executemany("INSERT INTO Languages(id, name) VALUES (?, ?)", id_lang[1:])
    assert c.execute("SELECT * FROM Languages WHERE id <= 35").fetchall() == id_lang

    #
    # add mangadex
    #
    site_id_name = [(key, val) for key, val in SUPPORTED_SITES.items()
                    if type(key) is int]

    prev_sites = c.execute("SELECT * FROM Sites").fetchall()
    start = len(prev_sites)
    c.executemany("INSERT INTO Sites(id, name) VALUES (?, ?)", site_id_name[start:])
    assert c.execute("SELECT * FROM Sites").fetchall() == site_id_name

    c.execute("PRAGMA foreign_keys = ON")
