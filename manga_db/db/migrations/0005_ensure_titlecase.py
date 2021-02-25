import sqlite3

from typing import Dict, List, Set, Tuple
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

        # NOTE: might have 'multiple' artists with same name but differently cased letters
        # so we have to de-dupe those
        before = [(_id, ','.join(n for n in sorted(set(names.lower().split(','))))) for _id, names in
                  c.execute(assert_query.format(table_name=table_name, fk_name=fk_name))]

        # without the ORDER BY id the rows were returned in a different order
        # since they're is no default order!
        rows = c.execute(f"""
        SELECT id, name FROM {table_name} ORDER BY id""").fetchall()

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
                reloc = Reloc(name=name, old_ids=[_id], new_id=new_id)
                name_to_reloc[same_case] = reloc
                in_order.append((new_id, reloc.name))

        c.execute(f"DROP TABLE {table_name}")
        # change name column to use NOCASE as collating function
        c.execute(table_creation_statements[table_name])
        # Artist table has additional favorite column but it has a default value
        # and it wasn't being used yet so this is fine
        c.executemany(f"INSERT INTO {table_name}(id, name) VALUES (?, ?)", in_order)
        # tbl_after = [(_id, name) for _id, name in c.execute(f"SELECT id, name FROM {table_name} ORDER BY id")]
        # make sure rows were inserted in the correct order
        # assert tbl_after == in_order

        # NOTE: FK from bridge table will still point to renamed table so we have to re-create
        # the bridge tables as well to update what table the FK references
        c.execute(f"ALTER TABLE Book{table_name} RENAME TO temp_table")
        c.execute(table_creation_statements[f"Book{table_name}"])

        old_id_to_reloc = {old_id: reloc for reloc in name_to_reloc.values() for old_id in reloc.old_ids}
        # can't udpate all the FKs to the new one if we have more than one since
        # the combination of book_id and *_id has to be unique (its a combined PK)
        # and two artists with the same name but different text case might point
        # to the same book and those would get changed to the same PK
        # -> have to make sure to only insert one ( book_id, new_id ) combo
        relocated_combo: Set[Tuple[int, int]] = set()
        # NOTE: iterating over the cursor (so we don't have to load the whole table into
        # a list first using fetchall) will break when modifying the table using THE SAME
        # cursor
        bridge_table_rows = c.execute("SELECT * FROM temp_table").fetchall()
        # Collection table also has in_collection_idx
        has_third_col = table_name == "Collection"
        for row in bridge_table_rows:
            if has_third_col:
                book_id, old_id, in_collection_idx = row
            else:
                book_id, old_id = row
            reloc = old_id_to_reloc[old_id]
            combo = (book_id, reloc.new_id)
            if combo in relocated_combo:
                continue

            relocated_combo.add(combo)
            new_row = combo if not has_third_col else (*combo, in_collection_idx)
            c.execute(f"INSERT INTO {bridge_table} VALUES (?, ?{', ?' if has_third_col else ''})",
                      new_row)

        c.execute("DROP TABLE temp_table")

        after = [(_id, ','.join(n for n in sorted(set(names.lower().split(','))))) for _id, names in
                 c.execute(assert_query.format(table_name=table_name, fk_name=fk_name))]
        # sanity check: books should still have the same associated column values after
        # unifying the text case
        assert before == after

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
    'BookList': """
    CREATE TABLE BookList(
        book_id INTEGER NOT NULL,
        list_id INTEGER NOT NULL,
        FOREIGN KEY (book_id) REFERENCES Books(id)
        ON DELETE CASCADE,
        FOREIGN KEY (list_id) REFERENCES List(id)
        ON DELETE CASCADE,
        PRIMARY KEY (book_id, list_id)
    )""",
    'Tag': """
    CREATE TABLE Tag(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'BookTag': """
    CREATE TABLE BookTag(
        book_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        FOREIGN KEY (book_id) REFERENCES Books(id)
        ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES Tag(id)
        ON DELETE CASCADE,
        PRIMARY KEY (book_id, tag_id)
    )""",
    'Collection': """
    CREATE TABLE Collection(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'BookCollection': """
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
        )""",
    'Category': """
    CREATE TABLE Category(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'BookCategory': """
    CREATE TABLE BookCategory(
            book_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES Books(id)
            ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES Category(id)
            ON DELETE CASCADE,
            PRIMARY KEY (book_id, category_id)
        )""",
    'Groups': """
    CREATE TABLE Groups(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'BookGroups': """
    CREATE TABLE BookGroups(
            book_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES Books(id)
            ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES Groups(id)
            ON DELETE CASCADE,
            PRIMARY KEY (book_id, group_id)
        )""",
    'Artist': """
    CREATE TABLE Artist(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            favorite INTEGER NOT NULL DEFAULT 0
        )""",
    'BookArtist': """
    CREATE TABLE BookArtist(
            book_id INTEGER NOT NULL,
            artist_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES Books(id)
            ON DELETE CASCADE,
            FOREIGN KEY (artist_id) REFERENCES Artist(id)
            ON DELETE CASCADE,
            PRIMARY KEY (book_id, artist_id)
        )""",
    'Parody': """
    CREATE TABLE Parody(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'BookParody': """
    CREATE TABLE BookParody(
            book_id INTEGER NOT NULL,
            parody_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES Books(id)
            ON DELETE CASCADE,
            FOREIGN KEY (parody_id) REFERENCES Parody(id)
            ON DELETE CASCADE,
            PRIMARY KEY (book_id, parody_id)
        )""",
    'Character': """
    CREATE TABLE Character(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE
        )""",
    'BookCharacter': """
    CREATE TABLE BookCharacter(
            book_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES Books(id)
            ON DELETE CASCADE,
            FOREIGN KEY (character_id) REFERENCES Character(id)
            ON DELETE CASCADE,
            PRIMARY KEY (book_id, character_id)
        )""",
}

    
