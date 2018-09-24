from manga_db import load_or_create_sql_db
db_con, _ = load_or_create_sql_db("manga_db.sqlite")

# sqlite doesnt allow to ALTER MODIFY a table
# -> add col, set value so we can later set to NOT NULL, create new table with added col NOT NULL, copy from old, drop old, rename
# prob also possible to add col when creating new table and when inserting specify constant to insert for that col
# -> prob with SELECT col1, col2, "tsumino.com"
# see: http://www.sqlitetutorial.net/sqlite-alter-table/
with db_con:
    # add col and set all to tsumino.com
    c = db_con.execute("""ALTER TABLE Tsumino
                          ADD COLUMN imported_from TEXT;""")
    c.execute("UPDATE Tsumino SET imported_from = \"tsumino.com\"")                      
 
    # use executescript since there are ";" in the code which seperate statements from each other
    # otherwise -> error: sqlite3.Warning: You can only execute one statement at a time
    c = db_con.executescript("""PRAGMA foreign_keys=off;
 
                 BEGIN TRANSACTION;
                  
                 ALTER TABLE Tsumino RENAME TO temp_table;
                  
                 CREATE TABLE Tsumino
                 (
                     id INTEGER PRIMARY KEY ASC,
                     title TEXT UNIQUE NOT NULL,
                     title_eng TEXT NOT NULL,
                     url TEXT UNIQUE NOT NULL,
                     id_onpage INTEGER UNIQUE NOT NULL,
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
                     imported_from TEXT NOT NULL,
                     last_change DATE NOT NULL,
                     downloaded INTEGER,
                     favorite INTEGER
                 );
                  
                 INSERT INTO Tsumino (id,title,title_eng,url,id_onpage,upload_date,uploader,pages,
                     rating,rating_full,my_rating,category,collection,groups,artist,parody,character,
                     imported_from,last_change,downloaded,favorite)
                   SELECT id,title,title_eng,url,id_onpage,upload_date,uploader,pages,
                     rating,rating_full,my_rating,category,collection,groups,artist,parody,character,
                     imported_from,last_change,downloaded,favorite
                   FROM temp_table;
                  
                 DROP TABLE temp_table;
                  
                 COMMIT;
                  
                 PRAGMA foreign_keys=on;""")                     