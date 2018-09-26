from manga_db import load_or_create_sql_db
from manga_db. import extractor
db_con, _ = load_or_create_sql_db("manga_db.sqlite")

# sqlite doesnt allow to ALTER MODIFY a table
# -> add col, set value so we can later set to NOT NULL, create new table with added col NOT NULL, copy from old, drop old, rename
# prob also possible to add col when creating new table and when inserting specify constant to insert for that col
# -> prob with SELECT col1, col2, "tsumino.com"
# see: http://www.sqlitetutorial.net/sqlite-alter-table/
with db_con:
    c = db_con.execute("""ALTER TABLE Books
                          ADD COLUMN title_foreign TEXT;""")
    # get titles and fill title_foreignive col
    id_title = c.execute("SELECT id, title FROM Books").fetchall()
    res_tuples = []
    for rid, title in id_title:
        title = re.match(self.ENG_TITLE_RE, value)
        if title:
            title_eng = title.group(1)
            title_foreign = title.group(2)
        else:
            # if all alphanum chars then title is english
            if all((c.isalpha() for c in title)):
                title_eng = value
                title_foreign = None
            else:
                title_eng = None
                title_foreign = value
        res_tuples.append((title_foreign, rid))

    c.executemany("UPDATE Books SET title_foreign = ? WHERE id = ?", res_tuples)
 
    c.execute("""CREATE TABLE IF NOT EXISTS Sites (
                 id INTEGER PRIMARY KEY ASC,
                 name TEXT UNIQUE NOT NULL)""")
    # insert supported sites
    c.executemany("INSERT OR IGNORE INTO Sites(id, name) VALUES (?, ?)",
                  extractor.SUPPORTED_SITES)

    # use executescript since there are ";" in the code which seperate statements from each other
    # otherwise -> error: sqlite3.Warning: You can only execute one statement at a time
    c = db_con.executescript("""PRAGMA foreign_keys=off;
 
                 BEGIN TRANSACTION;
                  
                 ALTER TABLE Books RENAME TO temp_table;
                  
                 CREATE TABLE Books
                 (
                     id INTEGER PRIMARY KEY ASC,
                     title TEXT UNIQUE NOT NULL,
                     title_eng TEXT UNIQUE,
                     title_foreign TEXT UNIQUE,
                     url TEXT UNIQUE NOT NULL,
                     id_onpage INTEGER NOT NULL,
                     imported_from INTEGER NOT NULL,
                     upload_date DATE NOT NULL,
                     uploader TEXT,
                     pages INTEGER NOT NULL,
                     rating REAL NOT NULL,
                     rating_full TEXT NOT NULL,
                     my_rating REAL,
                     category TEXT,
                     collection TEXT,
                     groups TEXT,
                     artist TEXT,
                     parody TEXT,
                     character TEXT,
                     last_change DATE NOT NULL,
                     downloaded INTEGER NOT NULL,
                     favorite INTEGER NOT NULL,
                     FOREIGN KEY (imported_from) REFERENCES Sites(id)
                        ON DELETE RESTRICT
                 );
                  
                 INSERT INTO Books (id, title, title_eng, title_foreign, url, id_onpage, upload_date,
                          uploader, pages, rating, rating_full, my_rating, category,
                          collection, groups, artist, parody, character, imported_from,
                          last_change, downloaded, favorite)
                   SELECT id, title, title_eng, title_foreign, url, id_onpage, upload_date,
                          uploader, pages, rating, rating_full, my_rating, category,
                          collection, groups, artist, parody, character, imported_from,
                          last_change, downloaded, favorite
                   FROM temp_table;
                  
                 DROP TABLE temp_table;
                  
                 COMMIT;
                  
                 PRAGMA foreign_keys=on;""")                     
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS id_onpage_on_site ON Books (id_onpage, imported_from)"
    )
