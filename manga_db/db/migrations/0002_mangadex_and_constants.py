import sqlite3

from typing import Dict, Union

date = '2021-01-24'
# so we can del rows with foreign key constraints and re-insert them
requires_foreign_keys_off = True


# NOTE: should not import data structures here since they will get updated
# which could break the migration script
SUPPORTED_SITES: Dict[Union[int, str], Union[int, str]] = {
        # site id, site name
        1: "tsumino.com",
        2: "nhentai.net",
        3: "MangaDex",
        # site name, id
        "tsumino.com": 1,
        "nhentai.net": 2,
        "MangaDex": 3,
}

STATUS_IDS: Dict[Union[str, int], Union[str, int]] = {
    "Unknown": 1, "Ongoing": 2, "Completed": 3, "Unreleased": 4, "Hiatus": 5, "Cancelled": 6,
    1: "Unknown", 2: "Ongoing", 3: "Completed", 4: "Unreleased", 5: "Hiatus", 6: "Cancelled"
}

LANG_IDS: Dict[Union[str, int], Union[str, int]] = {
     1: "English",
     2: "Japanese",
     3: "Chinese",
     4: "Korean",
     5: "Arabic",
     6: "Bengali",
     7: "Bulgarian",
     8: "Burmese",
     9: "Catalan",
    10: "Czech",
    11: "Danish",
    12: "Dutch",
    13: "Filipino",
    14: "Finnish",
    15: "French",
    16: "German",
    17: "Greek",
    18: "Hungarian",
    19: "Indonesian",
    20: "Italian",
    21: "Lithuanian",
    22: "Malay",
    23: "Mongolian",
    24: "Persian",
    25: "Polish",
    26: "Portuguese",
    27: "Romanian",
    28: "Russian",
    29: "Serbo-Croatian",
    30: "Spanish",
    31: "Swedish",
    32: "Thai",
    33: "Turkish",
    34: "Ukrainian",
    35: "Vietnamese",

    "English": 1,
    "Japanese": 2,
    "Chinese": 3,
    "Korean": 4,
    "Arabic": 5,
    "Bengali": 6,
    "Bulgarian": 7,
    "Burmese": 8,
    "Catalan": 9,
    "Czech": 10,
    "Danish": 11,
    "Dutch": 12,
    "Filipino": 13,
    "Finnish": 14,
    "French": 15,
    "German": 16,
    "Greek": 17,
    "Hungarian": 18,
    "Indonesian": 19,
    "Italian": 20,
    "Lithuanian": 21,
    "Malay": 22,
    "Mongolian": 23,
    "Persian": 24,
    "Polish": 25,
    "Portuguese": 26,
    "Romanian": 27,
    "Russian": 28,
    "Serbo-Croatian": 29,
    "Spanish": 30,
    "Swedish": 31,
    "Thai": 32,
    "Turkish": 33,
    "Ukrainian": 34,
    "Vietnamese": 35,
}


def upgrade(db_con: sqlite3.Connection, db_filename: str):
    c = db_con.cursor()

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
    book_id_lang_name = c.execute("""
    SELECT Books.id, Languages.name FROM Books
    JOIN Languages ON Languages.id = Books.language_id""").fetchall()

    c.execute("DELETE FROM Languages")
    c.executemany("INSERT INTO Languages(id, name) VALUES (?, ?)", id_lang)
    lang_map = {k: v for k, v in LANG_IDS.items() if type(k) is str}
    # update language_id based on name one by one, since updating them in bulk
    # gets too complicated for a simple migration
    for book_id, lang_name in book_id_lang_name:
        # check for custom lang
        if lang_name not in lang_map:
            c.execute("INSERT INTO Languages(name) VALUES (?)", (lang_name,))
            lang_map[lang_name] = c.lastrowid

        lang_id = lang_map[lang_name]
        c.execute("UPDATE Books SET language_id = ? WHERE id = ?", (lang_id, book_id))


    assert c.execute(
            "SELECT * FROM Languages WHERE id <= ?", (len(id_lang),)).fetchall() == id_lang

    #
    # add mangadex
    #
    site_id_name = [(key, val) for key, val in SUPPORTED_SITES.items()
                    if type(key) is int]

    prev_sites = c.execute("SELECT * FROM Sites").fetchall()
    start = len(prev_sites)
    c.executemany("INSERT INTO Sites(id, name) VALUES (?, ?)", site_id_name[start:])
    assert c.execute("SELECT * FROM Sites").fetchall() == site_id_name
