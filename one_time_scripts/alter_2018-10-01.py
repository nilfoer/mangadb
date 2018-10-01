import sqlite3


def _add_tags(_id, tags):
    bid_tags = zip([_id] * len(tags), tags)
    c.executemany("""INSERT OR IGNORE INTO BookTag(book_id, tag_id)
                     SELECT ?, Tag.id FROM Tag
                     WHERE Tag.name = ?""", bid_tags)
    return c

def _add_lists(_id, tags):
    bid_tags = zip([_id] * len(tags), tags)
    c.executemany("""INSERT OR IGNORE INTO BookList(book_id, list_id)
                     SELECT ?, List.id FROM List
                     WHERE List.name = ?""", bid_tags)
    return c


def get_tags_by_book(db_con, _id):
    c = db_con.execute("""SELECT group_concat(Tags.name)
                          FROM Tags, BookTags bt, Books
                          WHERE bt.book_id = Books.id
                          AND Books.id = ?
                          AND bt.tag_id = Tags.tag_id
                          GROUP BY bt.book_id""", (_id, ))
    result = c.fetchone()
    return result[0] if result else None


db_con = sqlite3.connect("./manga_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;

                BEGIN TRANSACTION;

                CREATE TABLE List(
                        id INTEGER PRIMARY KEY ASC,
                        name TEXT UNIQUE NOT NULL
                    );
                CREATE TABLE BookList(
                        book_id INTEGER NOT NULL,
                        list_id INTEGER NOT NULL,
                        FOREIGN KEY (book_id) REFERENCES Books(id)
                        ON DELETE CASCADE,
                        FOREIGN KEY (list_id) REFERENCES List(id)
                        ON DELETE CASCADE,
                        PRIMARY KEY (book_id, list_id)
                    );

                -- insert lists into list
                INSERT INTO List(name)
                SELECT TRIM(Tags.name, 'li_')
                FROM Tags
                WHERE list_bool = 1;

                CREATE TABLE IF NOT EXISTS Tag(
                        id INTEGER PRIMARY KEY ASC,
                        name TEXT UNIQUE NOT NULL
                    );
                CREATE TABLE IF NOT EXISTS BookTag(
                        book_id INTEGER NOT NULL,
                        tag_id INTEGER NOT NULL,
                        FOREIGN KEY (book_id) REFERENCES Books(id)
                        ON DELETE CASCADE,
                        FOREIGN KEY (tag_id) REFERENCES Tag(id)
                        ON DELETE CASCADE,
                        PRIMARY KEY (book_id, tag_id)
                     );
                -- insert tags into new tag table
                INSERT INTO Tag(name)
                SELECT Tags.name
                FROM Tags
                WHERE list_bool = 0;
                -- but dont delete old one yet!!!

                COMMIT;

                PRAGMA foreign_keys=on;
                """)

    # repopulate BookTag table
    c.execute("SELECT id, favorite FROM Books")
    for row in c.fetchall():
        tags = get_tags_by_book(db_con, row[0])
        if not tags:
            continue
        tags = tags.split(",")
        lists = [t[3:] for t in tags if t.startswith("li_")]
        tags = [t for t in tags if not t.startswith("li_")]
        if "best" in lists:
            lists.remove("best")
            if not row[1]:
                print("li_best but not fav -> changed to fav 1 id: %d" % row[0])
                c.execute("UPDATE Books SET favorite = 1 WHERE id = ?", (row[0],))
        else:
            # just to be safe
            if row[1]:
                print("fav but not li_best on id %d" % row[0])
        if tags:
            _add_tags(row[0], tags)
        if lists:
            _add_lists(row[0], lists)
    # del old tables
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;

                BEGIN TRANSACTION;

                DROP TABLE Tags;
                DROP TABLE BookTags;
                -- triggers get deleted with assoc table
                DROP TRIGGER IF EXISTS set_last_change_tags_ins;
                DROP TRIGGER IF EXISTS set_last_change_tags_del;
                DROP TRIGGER IF EXISTS update_favorite_on_tags_insert;
                DROP TRIGGER IF EXISTS update_favorite_on_tags_delete;

                COMMIT;

                PRAGMA foreign_keys=on;
                """)

    # set last_change on Books when new tags get added in bridge table
    c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tag_ins
                 AFTER INSERT ON BookTag
                 BEGIN
                    UPDATE Books
                    SET last_change = DATE('now', 'localtime')
                    WHERE id = NEW.book_id;
                 END""")

    # set last_change on Books when tags get removed in bridge table
    c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_tag_del
                 AFTER DELETE ON BookTag
                 BEGIN
                    UPDATE Books
                    SET last_change = DATE('now', 'localtime')
                    WHERE id = OLD.book_id;
                 END""")

    # set last_change on Books when new lists get added in bridge table
    c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_list_ins
                 AFTER INSERT ON BookList
                 BEGIN
                    UPDATE Books
                    SET last_change = DATE('now', 'localtime')
                    WHERE id = NEW.book_id;
                 END""")

    # set last_change on Books when lists get removed in bridge table
    c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_change_list_del
                 AFTER DELETE ON BookList
                 BEGIN
                    UPDATE Books
                    SET last_change = DATE('now', 'localtime')
                    WHERE id = OLD.book_id;
                 END""")
