import sys
import sqlite3

db_con = sqlite3.connect(sys.argv[1], detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;

                BEGIN TRANSACTION;

                ALTER TABLE ExternalInfo RENAME TO temp_table;

                -- drop url col and build it from externalinfo so we don't get screwed when
                -- the ext sites change their url scheme
                -- (happend with tsumino: /Book/Info/id to /entry/id)
                CREATE TABLE IF NOT EXISTS ExternalInfo(
                        id INTEGER PRIMARY KEY ASC,
                        book_id INTEGER NOT NULL,
                        id_onpage INTEGER NOT NULL,
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
                    );

                INSERT INTO ExternalInfo SELECT id, book_id, id_onpage, imported_from, upload_date,
                                                uploader, censor_id, rating, ratings, favorites,
                                                downloaded, last_update, outdated FROM temp_table t;

                DROP TABLE temp_table;

                CREATE INDEX IF NOT EXISTS idx_id_onpage_imported_from ON
                    ExternalInfo (id_onpage, imported_from);

                COMMIT;

                PRAGMA foreign_keys=on;
                """)
