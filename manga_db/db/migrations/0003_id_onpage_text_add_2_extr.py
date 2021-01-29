date = '2021-01-29'
# need to turn of foreign key constraints in order to rename ExternalInfo
requires_foreign_keys_off = True


def upgrade(db_con, db_filename):
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

