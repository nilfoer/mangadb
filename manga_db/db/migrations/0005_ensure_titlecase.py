import sqlite3

from typing import Dict, List
from collections import defaultdict
from dataclasses import dataclass


date = '2021-02-16'
requires_foreign_keys_off = True


@dataclass
class Reloc:
    name: str
    old_ids: List[int]
    new_id: int


def upgrade(db_con: sqlite3.Connection, db_filename: str) -> None:
    c = db_con.cursor()

    # deactivate last_change triggers so last_change doesn't get set to the current date
    # for all books
    c.execute("DROP TRIGGER set_books_last_change")

    assert_query = """
    SELECT b.id, group_concat(a.name, ',') as names FROM Books b
    JOIN Book{table_name} ba ON ba.book_id = b.id
    JOIN {table_name} a ON a.id = ba.{fk_name}
    GROUP BY b.id
    ORDER BY b.id
    """
    for table_name in (
            'Artist', 'Category', 'Character', 'Collection', 'Groups', 'List', 'Parody', 'Tag'):
        bridge_table = f"Book{table_name}"
        fk_name = f"{table_name.lower().rstrip('s')}_id"

        before = [(_id, names.lower()) for _id, names in
                  c.execute(assert_query.format(table_name=table_name, fk_name=fk_name))]

        # without the ORDER BY id the rows were returned in a different order
        # since they're is no default order!
        rows = c.execute(f"""
        SELECT id, name FROM {table_name} ORDER BY id""").fetchall()

        # force tag names to be title case for all others use the first occurence
        # (lowest id since we ORDER BY id)
        case_changing_function = (lambda x: x) if table_name != 'Tag' else str.title
        name_to_reloc: Dict[str, Reloc] = {}
        # id/name combos to insert
        in_order = []
        i = 1
        for _id, name in rows:
            same_case = name.lower()
            try:
                reloc = name_to_reloc[same_case]
                reloc.old_ids.append(_id)
            except KeyError:
                new_id = i
                i += 1
                reloc = Reloc(name=case_changing_function(name), old_ids=[_id], new_id=new_id)
                name_to_reloc[same_case] = reloc
                in_order.append((new_id, reloc.name))

        c.execute(f"DELETE FROM {table_name}")
        # Artist table has additional favorite column but it has a default value
        # and it wasn't being used yet so this is fine
        c.executemany(f"INSERT INTO {table_name}(id, name) VALUES (?, ?)", in_order)
        # tbl_after = [(_id, name) for _id, name in c.execute(f"SELECT id, name FROM {table_name} ORDER BY id")]
        # make sure rows were inserted in the correct order
        # assert tbl_after == in_order

        # update foreign keys in Book table
        for reloc in name_to_reloc.values():
            c.execute(f"UPDATE {bridge_table} SET {fk_name} = ? WHERE {fk_name} IN "
                      f"(?{', ?' * (len(reloc.old_ids) - 1)})", (reloc.new_id, *reloc.old_ids))

        after = [(_id, names.lower()) for _id, names in
                 c.execute(assert_query.format(table_name=table_name, fk_name=fk_name))]
        # sanity check: books should still have the same associated column values after
        # unifying the text case
        assert before == after

        # change name column to use NOCASE as collating function
        c.execute(f"ALTER TABLE {table_name} RENAME TO temp_table")
        c.execute(table_creation_statements[table_name])
        c.execute(f"INSERT INTO {table_name} SELECT * FROM temp_table")
        c.execute("DROP TABLE temp_table")

    # reactivate trigger
    c.execute("""
    CREATE TRIGGER set_books_last_change
    AFTER UPDATE ON Books
    BEGIN
        UPDATE Books
        SET last_change = DATE('now', 'localtime')
        WHERE id = NEW.id;
    END""")

    # change collating function that is used for string comparisons (can also be done
    # on a single select instead: e.g. "name = ? COLLATE NOCASE") to NOCASE for case
    # insensitive comparison when using '=' operator etc.
    # just changing the index's collating function means it will only be used when
    # COLLATE NOCASE is explicitly used like: "WHERE name = ? COLLATE NOCASE"
    # since the collating function is determined by the one set on the operator first
    # and then the based on the one that was set for the column second and if none of
    # those are set the default of binary comparison is used
    # for the index to be used it __MUST__ use the same collating function as the column
    # or the specific query
    # NOTE: collating function NOCASE only works with ASCII
    # NOTE: indices should be deleted when dropping the temp table but just to make sure
    c.execute("DROP INDEX IF EXISTS idx_artist_name")
    c.execute("DROP INDEX IF EXISTS idx_category_name")
    c.execute("DROP INDEX IF EXISTS idx_character_name")
    c.execute("DROP INDEX IF EXISTS idx_collection_name")
    c.execute("DROP INDEX IF EXISTS idx_groups_name")
    c.execute("DROP INDEX IF EXISTS idx_list_name")
    c.execute("DROP INDEX IF EXISTS idx_parody_name")
    c.execute("DROP INDEX IF EXISTS idx_tag_name")

    c.execute("CREATE UNIQUE INDEX idx_artist_name ON Artist (name COLLATE NOCASE)")
    c.execute("CREATE UNIQUE INDEX idx_category_name ON Category (name COLLATE NOCASE)")
    c.execute("CREATE UNIQUE INDEX idx_character_name ON Character (name COLLATE NOCASE)")
    c.execute("CREATE UNIQUE INDEX idx_collection_name ON Collection (name COLLATE NOCASE)")
    c.execute("CREATE UNIQUE INDEX idx_groups_name ON Groups (name COLLATE NOCASE)")
    c.execute("CREATE UNIQUE INDEX idx_list_name ON List (name COLLATE NOCASE)")
    c.execute("CREATE UNIQUE INDEX idx_parody_name ON Parody (name COLLATE NOCASE)")
    c.execute("CREATE UNIQUE INDEX idx_tag_name ON Tag (name COLLATE NOCASE)")


table_creation_statements = {
    'List': """
    CREATE TABLE List(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'Tag': """
    CREATE TABLE Tag(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'Collection': """
    CREATE TABLE Collection(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'Category': """
    CREATE TABLE Category(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'Groups': """
    CREATE TABLE Groups(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'Artist': """
    CREATE TABLE Artist(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            favorite INTEGER NOT NULL DEFAULT 0
        )""",
    'Parody': """
    CREATE TABLE Parody(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'Character': """
    CREATE TABLE Character(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
}

    