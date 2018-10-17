import sqlite3

db_con = sqlite3.connect("./manga_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;

                BEGIN TRANSACTION;

                ALTER TABLE ExternalInfo RENAME TO temp_table;

                CREATE TABLE IF NOT EXISTS ExternalInfo(
                        id INTEGER PRIMARY KEY ASC,
                        book_id INTEGER NOT NULL,
                        -- url could be built from id but idk if thats true for all sites
                        -- so keep it for now
                        url TEXT NOT NULL,
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

                INSERT INTO ExternalInfo
                    SELECT t.id, (
                                    SELECT book_id
                                    FROM ExternalInfoBooks eib
                                    WHERE eib.ext_info_id = t.id
                                 ),
                           t.url, t.id_onpage, t.imported_from, t.upload_date,
                           t.uploader, t.censor_id, t.rating, t.ratings, t.favorites,
                           t.downloaded, t.last_update, t.outdated
                    FROM temp_table t;

                DROP TABLE temp_table;
                DROP TABLE ExternalInfoBooks;

                COMMIT;

                PRAGMA foreign_keys=on;
                """)
