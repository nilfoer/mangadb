import sqlite3

from typing import Dict, Union


date = '2021-02-05'
# need to turn of foreign key constraints in order to rename ExternalInfo
requires_foreign_keys_off = True


def upgrade(db_con: sqlite3.Connection, db_filename: str):
    c = db_con.cursor()
    c.execute("INSERT INTO Sites(id, name) VALUES (6, 'MangaSee123')")

    c.execute("ALTER TABLE BookCollection RENAME TO temp")
    c.execute("""
    CREATE TABLE BookCollection(
        book_id INTEGER NOT NULL,
        collection_id INTEGER NOT NULL,
        in_collection_idx INTEGER NOT NULL,
        FOREIGN KEY (book_id) REFERENCES Books(id)
        ON DELETE CASCADE,
        FOREIGN KEY (collection_id) REFERENCES Collection(id)
        ON DELETE CASCADE,
        UNIQUE(collection_id, in_collection_idx),
        PRIMARY KEY (book_id, collection_id)
    )""")

    insert_bid_cid_idx = []
    collection_ids = c.execute("SELECT id FROM Collection").fetchall()
    for collection_id, in collection_ids:
        book_collection_rows = [
            (i + 1, row[0], row[1]) for i, row in enumerate(c.execute("""
            SELECT book_id, collection_id FROM temp WHERE collection_id = ?
            ORDER BY book_id""", (collection_id,)))]
        insert_bid_cid_idx.extend(book_collection_rows)

    c.executemany("""
    INSERT INTO BookCollection(in_collection_idx, book_id, collection_id)
    VALUES (?, ?, ?)""", insert_bid_cid_idx)

    c.execute("DROP TABLE temp")


