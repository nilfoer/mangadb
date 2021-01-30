import sqlite3

from typing import Dict, Union


date = '2021-01-29'
# need to turn of foreign key constraints in order to rename ExternalInfo
requires_foreign_keys_off = True

SUPPORTED_SITES: Dict[Union[int, str], Union[int, str]] = {
        # site id, site name
        1: "tsumino.com",
        2: "nhentai.net",
        3: "MangaDex",
        4: "Manganelo",
        5: "Toonily",
        # site name, id
        "tsumino.com": 1,
        "nhentai.net": 2,
        "MangaDex": 3,
        "Manganelo": 4,
        "Toonily": 5,
}

LANG_IDS: Dict[Union[str, int], Union[str, int]] = {
     1: "Unknown",
     2: "English",
     3: "Japanese",
     4: "Chinese",
     5: "Korean",
     6: "Arabic",
     7: "Bengali",
     8: "Bulgarian",
     9: "Burmese",
    10: "Catalan",
    11: "Czech",
    12: "Danish",
    13: "Dutch",
    14: "Filipino",
    15: "Finnish",
    16: "French",
    17: "German",
    18: "Greek",
    19: "Hungarian",
    20: "Indonesian",
    21: "Italian",
    22: "Lithuanian",
    23: "Malay",
    24: "Mongolian",
    25: "Persian",
    26: "Polish",
    27: "Portuguese",
    28: "Romanian",
    29: "Russian",
    30: "Serbo-Croatian",
    31: "Spanish",
    32: "Swedish",
    33: "Thai",
    34: "Turkish",
    35: "Ukrainian",
    36: "Vietnamese",

    "Unknown": 1,
    "English": 2,
    "Japanese": 3,
    "Chinese": 4,
    "Korean": 5,
    "Arabic": 6,
    "Bengali": 7,
    "Bulgarian": 8,
    "Burmese": 9,
    "Catalan": 10,
    "Czech": 11,
    "Danish": 12,
    "Dutch": 13,
    "Filipino": 14,
    "Finnish": 15,
    "French": 16,
    "German": 17,
    "Greek": 18,
    "Hungarian": 19,
    "Indonesian": 20,
    "Italian": 21,
    "Lithuanian": 22,
    "Malay": 23,
    "Mongolian": 24,
    "Persian": 25,
    "Polish": 26,
    "Portuguese": 27,
    "Romanian": 28,
    "Russian": 29,
    "Serbo-Croatian": 30,
    "Spanish": 31,
    "Swedish": 32,
    "Thai": 33,
    "Turkish": 34,
    "Ukrainian": 35,
    "Vietnamese": 36,
}


def upgrade(db_con: sqlite3.Connection, db_filename: str):
    c = db_con.cursor()

    c.execute("ALTER TABLE ExternalInfo RENAME TO temp_table")
    # change id_onpage from INT to TEXT so we can store information for external
    # pages that somehow don't use integers for their ids
    # IMPORTANT don't change the order so we can use INSERT without specifying cols
    c.execute("""
    CREATE TABLE ExternalInfo(
        id INTEGER PRIMARY KEY ASC,
        book_id INTEGER NOT NULL,
        id_onpage TEXT NOT NULL,
        imported_from INTEGER NOT NULL,
        upload_date DATE NOT NULL,
        uploader TEXT,
        censor_id INTEGER NOT NULL,
        rating REAL,
        ratings INTEGER, -- number of users that rated the book
        favorites INTEGER,
        downloaded INTEGER NOT NULL,
        last_update DATE NOT NULL,
        outdated INTEGER NOT NULL,
        FOREIGN KEY (book_id) REFERENCES Books(id)
           ON DELETE CASCADE,
        FOREIGN KEY (imported_from) REFERENCES Sites(id)
           ON DELETE RESTRICT,
        FOREIGN KEY (censor_id) REFERENCES Censorship(id)
           ON DELETE RESTRICT
    )""")

    c.execute("DROP INDEX idx_id_onpage_imported_from")
    # recreate index
    c.execute("CREATE INDEX idx_id_onpage_imported_from ON ExternalInfo (id_onpage, imported_from)")
    # re-populate table
    c.execute("INSERT INTO ExternalInfo SELECT * FROM temp_table")

    c.execute("DROP TABLE temp_table")

    #
    # add Unkown to Languages as id 1
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
    # add manganelo to Sites
    #
    site_id_name = [(key, val) for key, val in SUPPORTED_SITES.items()
                    if type(key) is int]

    prev_sites = c.execute("SELECT * FROM Sites").fetchall()
    start = len(prev_sites)
    c.executemany("INSERT INTO Sites(id, name) VALUES (?, ?)", site_id_name[start:])
    assert c.execute("SELECT * FROM Sites").fetchall() == site_id_name

