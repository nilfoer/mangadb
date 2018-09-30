import sqlite3
import re
import datetime


def get_tags_by_book(db_con, _id):
    c = db_con.execute("""SELECT group_concat(Tags.name)
                          FROM Tags, BookTags bt, Books
                          WHERE bt.book_id = Books.id
                          AND Books.id = ?
                          AND bt.tag_id = Tags.tag_id
                          GROUP BY bt.book_id""", (_id, ))
    result = c.fetchone()
    return result[0] if result else None


UNESCAPED, ESCAPED = 0, 1
def string_to_list(string, escape_char="\\", sep=","):
    if string is None:
        return None
    result = []
    state = UNESCAPED
    current_item = ""
    for c in string:
        if state == ESCAPED:
            # if we had more special chars we could handle them here
            current_item += c
            # escape is only for one char (unlike quotes) -> reset to unescaped
            state = UNESCAPED
        else:
            if c == escape_char:
                state = ESCAPED
            elif c == sep:
                result.append(current_item)
                current_item = ""
            else:
                current_item += c
    result.append(current_item)
    return result


db_con = sqlite3.connect("./manga_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    c = db_con.execute("""CREATE TABLE Censorship
                        (
                            id INTEGER PRIMARY KEY ASC,
                            name TEXT UNIQUE NOT NULL
                        )""")
    cen_stats = [("Unknown",), ("Censored",), ("Decensored",), ("Uncensored",)]
    c.executemany("INSERT OR IGNORE INTO Censorship(name) VALUES (?)", cen_stats)
    # create and fill external info and bridge table
    c = db_con.execute("""
                        CREATE TABLE ExternalInfo
                        (
                            id INTEGER PRIMARY KEY ASC,
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
                            FOREIGN KEY (imported_from) REFERENCES Sites(id)
                               ON DELETE RESTRICT,
                            FOREIGN KEY (censor_id) REFERENCES Censorship(id)
                               ON DELETE RESTRICT
                        )
                        """)
    c.execute("""CREATE TABLE ExternalInfoBooks(
                     book_id INTEGER NOT NULL,
                     ext_info_id INTEGER NOT NULL,
                     FOREIGN KEY (book_id) REFERENCES Books(id)
                     ON DELETE CASCADE,
                     FOREIGN KEY (ext_info_id) REFERENCES ExternalInfo(id)
                     ON DELETE CASCADE,
                     PRIMARY KEY (book_id, ext_info_id))""")

    c.execute("DROP INDEX id_onpage_on_site")
    c.execute(
        "CREATE INDEX IF NOT EXISTS id_onpage_on_site ON ExternalInfo (id_onpage, imported_from)"
    )

    # trigger not needed anymore since there can be multiple external links per book
    c.execute("DROP TRIGGER update_downloaded_on_tags_insert")
    c.execute("DROP TRIGGER update_downloaded_on_tags_delete")

    c.execute("SELECT id, rating_full, url, id_onpage, imported_from, upload_date, uploader,"
              "rating, downloaded FROM Books")
    lupdate = datetime.datetime.strptime("2017 January 01", "%Y %B %d").date()
    rating_rull_re = re.compile(r"\d\.\d{1,2} \((\d+) users / (\d+) favs\)")
    for row in c.fetchall():
        # split rating_full into ratings and favorites
        rat_full = row["rating_full"]
        rat_full = rating_rull_re.match(rat_full)
        ratings = int(rat_full.group(1))
        favorites = int(rat_full.group(2))
        # correctly fill in censor status
        tags = get_tags_by_book(db_con, row["id"])
        if tags is None:
            censor_id = 1
        else:
            tags = tags.split(",")
            if "Decensored" in tags:
                censor_id = 3
            elif "Uncensored" in tags:
                censor_id = 4
            else:
                censor_id = 2

        c.execute("INSERT INTO ExternalInfo(url, id_onpage, imported_from,"
                  "upload_date, uploader, rating, downloaded, last_update,"
                  "censor_id, ratings, favorites) VALUES "
                  "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  row[2:] + (lupdate, censor_id, ratings, favorites))
        ext_info_id = c.lastrowid
        c.execute("INSERT INTO ExternalInfoBooks(book_id, ext_info_id) VALUES (?, ?)",
                  (row[0], ext_info_id))

    c.execute("""CREATE TRIGGER IF NOT EXISTS set_last_update_ext_info
                 AFTER UPDATE ON ExternalInfo
                 BEGIN
                    UPDATE ExternalInfo
                    SET last_update = DATE('now', 'localtime')
                    WHERE id = NEW.id;
                 END""")

    c.execute("""CREATE TABLE Status
                    (
                        id INTEGER PRIMARY KEY ASC,
                        name TEXT UNIQUE NOT NULL
                    )""")
    status = [("Unknown",), ("Ongoing",), ("Completed",), ("Unreleased",),
              ("Hiatus",)]
    c.executemany("INSERT OR IGNORE INTO Status(name) VALUES (?)", status)

    c.executescript("""
                CREATE TABLE Collection
                (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                CREATE TABLE BookCollection
                (
                    book_id INTEGER NOT NULL,
                    collection_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (collection_id) REFERENCES Collection(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, collection_id)
                );

                CREATE TABLE Category
                (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                CREATE TABLE BookCategory
                (
                    book_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (category_id) REFERENCES Category(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, category_id)
                );
                -- Group protected keyword in sql
                CREATE TABLE Groups
                (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                CREATE TABLE BookGroups
                (
                    book_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES Groups(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, group_id)
                );
                CREATE TABLE Artist
                (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                CREATE TABLE BookArtist
                (
                    book_id INTEGER NOT NULL,
                    artist_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (artist_id) REFERENCES Artist(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, artist_id)
                );
                CREATE TABLE Parody
                (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                CREATE TABLE BookParody
                (
                    book_id INTEGER NOT NULL,
                    parody_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (parody_id) REFERENCES Parody(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, parody_id)
                );
                CREATE TABLE Character
                (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
                CREATE TABLE BookCharacter
                (
                    book_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    FOREIGN KEY (book_id) REFERENCES Books(id)
                    ON DELETE CASCADE,
                    FOREIGN KEY (character_id) REFERENCES Character(id)
                    ON DELETE CASCADE,
                    PRIMARY KEY (book_id, character_id)
                );
                """)

    MULTI_VALUE_COL = (("category", "Category"),
                       ("collection", "Collection"),
                       ("groups", "Groups"),
                       ("artist", "Artist"),
                       ("parody", "Parody"),
                       ("character", "Character"))
    # since category, collection etc. are multi-value columns converting them
    # using sql doesnt work
    # i know slow and spaghetti but im only doing it once so...
    c.execute("""SELECT id, collection, category, groups, artist, parody, character
                 FROM Books""")
    for row in c.fetchall():
        for col, table_name in MULTI_VALUE_COL:
            col_list = string_to_list(row[col])
            if col_list is None:
                continue
            for val in col_list:
                c.execute(f"INSERT OR IGNORE INTO {table_name}(name) VALUES (?)", (val,))
                # ingored -> no c.lastrowid so use WHERE name=? etc.
                c.execute(f"""INSERT INTO Book{table_name} VALUES (?, (
                            SELECT id FROM {table_name} WHERE name = ?))""", (row["id"], val))

    # -- -> single line comment in sql
    # /* .... */ multi-line comment
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;
 
                BEGIN TRANSACTION;
                  
                ALTER TABLE Books RENAME TO temp_table;

                CREATE TABLE Books
                (
                    id INTEGER PRIMARY KEY ASC,
                    title TEXT UNIQUE NOT NULL,
                    title_eng TEXT UNIQUE,
                    title_foreign TEXT,
                    language_id INTEGER NOT NULL,
                    pages INTEGER NOT NULL,
                    status_id INTERGER NOT NULL,
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
                  SELECT id, title, title_eng, title_foreign, 1, pages, 1,
                  my_rating, note, last_change, favorite
                  FROM temp_table;
                 
                DROP TABLE temp_table;
                 
                COMMIT;
                 
                PRAGMA foreign_keys=on;""")                     
