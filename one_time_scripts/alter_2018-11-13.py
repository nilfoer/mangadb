import sqlite3

db_con = sqlite3.connect("./manga_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;

                BEGIN TRANSACTION;

                ALTER TABLE Books RENAME TO temp_table;

                CREATE TABLE IF NOT EXISTS Books(
                        id INTEGER PRIMARY KEY ASC,
                        title_eng TEXT UNIQUE,
                        title_foreign TEXT,
                        language_id INTEGER NOT NULL,
                        pages INTEGER NOT NULL,
                        status_id INTERGER NOT NULL,
                        read_status INTEGER,
                        my_rating REAL,
                        note TEXT,
                        last_change DATE NOT NULL,
                        favorite INTEGER NOT NULL,
                        FOREIGN KEY (language_id) REFERENCES Languages(id)
                           ON DELETE RESTRICT,
                        FOREIGN KEY (status_id) REFERENCES Status(id)
                           ON DELETE RESTRICT
                    );

                INSERT INTO Books
                    SELECT t.id, t.title_eng, t.title_foreign, t.language_id,
                           t.pages, t.status_id, NULL, t.my_rating, t.note,
                           t.last_change, t.favorite
                    FROM temp_table t;

                DROP TABLE temp_table;

                CREATE UNIQUE INDEX IF NOT EXISTS idx_title_eng_foreign
                    ON Books (title_eng, title_foreign);

                CREATE TRIGGER IF NOT EXISTS set_books_last_change
                                     AFTER UPDATE ON Books
                                     BEGIN
                                        UPDATE Books
                                        SET last_change = DATE('now', 'localtime')
                                        WHERE id = NEW.id;
                                     END;

                COMMIT;

                PRAGMA foreign_keys=on;
                """)
