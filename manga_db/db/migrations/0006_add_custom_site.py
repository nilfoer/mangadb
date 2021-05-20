import sqlite3

from typing import Dict, Union

date = '2021-05-18'
# so we can del rows with foreign key constraints and re-insert them
requires_foreign_keys_off = True


SUPPORTED_SITES: Dict[Union[int, str], Union[int, str]] = {
        # site id, site name
        1: "tsumino.com",
        2: "nhentai.net",
        3: "MangaDex",
        4: "Manganelo",
        5: "Toonily",
        6: "MangaSee123",
        7: "MANUAL_ADD",
        # site name, id
        "tsumino.com": 1,
        "nhentai.net": 2,
        "MangaDex": 3,
        "Manganelo": 4,
        "Toonily": 5,
        "MangaSee123": 6,
        "MANUAL_ADD": 7,
}


def upgrade(db_con: sqlite3.Connection, db_filename: str):
    c = db_con.cursor()

    c.executemany("INSERT OR IGNORE INTO Sites(id, name) VALUES (?, ?)",
                  [(key, val) for key, val in SUPPORTED_SITES.items()
                   if isinstance(key, int)])
