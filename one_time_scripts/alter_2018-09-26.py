import sqlite3
import re
db_con = sqlite3.connect("./manga_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)

FOREIGN_RE = re.compile(r"[\u0100-\u02AF\u0370-\u1CFF\u1F00−\u1FFF\u2C00-\u2DFF\u2E80-\uFDFF\uFE30−\uFE4F\uFE70−\uFEFF]")


def count_foreign_chars(string):
    return len(FOREIGN_RE.findall(string))


def is_foreign(string, foreign_chars_to_string_length=0.5):
    # findall returns each non-overlapping match in a list
    foreign_char_amount = count_foreign_chars(string)
    if foreign_char_amount/len(string) >= foreign_chars_to_string_length:
        return True
    else:
        return False


# sqlite doesnt allow to ALTER MODIFY a table
# -> add col, set value so we can later set to NOT NULL, create new table with added col NOT NULL, copy from old, drop old, rename
# prob also possible to add col when creating new table and when inserting specify constant to insert for that col
# -> prob with SELECT col1, col2, "tsumino.com"
# see: http://www.sqlitetutorial.net/sqlite-alter-table/
with db_con:
    c = db_con.execute("""ALTER TABLE Tsumino
                          ADD COLUMN title_foreign TEXT;""")
    # get titles and fill title_foreign col
    id_title = c.execute("SELECT id, title FROM Tsumino").fetchall()
    res_tuples = []
    TITLE_RE = re.compile(r"^(.+) \/ (.+)")
    for rid, title in id_title:
        m_title = re.match(TITLE_RE, title)
        if m_title:
            title_eng = m_title.group(1)
            title_foreign = m_title.group(2)
            if "(DUPLICATE " in title:
                # split at duplicate otherwise (DUPL.. might be in title_eng or title_foreign
                title, dupl_nr = title.split("(DUPLICATE ")
                dupl_nr = dupl_nr.split(")")[0]
                m_title = re.match(TITLE_RE, title)
                title_eng = m_title.group(1)
                title_foreign = m_title.group(2)
                title_eng = f"{title_eng} (DUPLICATE {dupl_nr})"
                title_foreign = f"{title_foreign} (DUPLICATE {dupl_nr})"
        else:
            # dont need to check for (DUPL.. since it should be in title_*
            if is_foreign(title):
                title_eng = None
                title_foreign = title
            else:
                title_eng = title
                title_foreign = None
        res_tuples.append((title_eng, title_foreign, rid))

    c.executemany("UPDATE Tsumino SET title_eng = ?, title_foreign = ? WHERE id = ?", res_tuples)
 
    c.execute("""CREATE TABLE IF NOT EXISTS Sites (
                 id INTEGER PRIMARY KEY ASC,
                 name TEXT UNIQUE NOT NULL)""")
    # insert supported sites
    c.executemany("INSERT OR IGNORE INTO Sites(id, name) VALUES (?, ?)",
                  [(1, "tsumino.com")])

    # use executescript since there are ";" in the code which seperate statements from each other
    # otherwise -> error: sqlite3.Warning: You can only execute one statement at a time
    c = db_con.executescript("""PRAGMA foreign_keys=off;
 
                 BEGIN TRANSACTION;
                  
                 UPDATE Tsumino SET imported_from = 1;
                 UPDATE Tsumino SET downloaded = 0 WHERE downloaded is null;
                 UPDATE Tsumino SET favorite = 0 WHERE favorite is null;
                 ALTER TABLE Tsumino RENAME TO temp_table;
                  
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
                  
                 INSERT INTO Books (id, title, title_eng, title_foreign, url, id_onpage,
                          upload_date, uploader, pages, rating, rating_full, my_rating,
                          category, collection, groups, artist, parody, character,
                          imported_from, last_change, downloaded, favorite)
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

    # since we changed table name of Tsumino to Books we also have to re-do
    # BookTags and the triggers since they reference Tsumino and the references
    # only get (if at all) partly updated
    # e.g. on trigger AFTER .. ON table-name gets updated but the table name in
    # the action (between BEGIN..END) doesnt; FOREGIN KEY also doesnt get updated etc.
    c.executescript("""
                        PRAGMA foreign_keys=off;
 
                         BEGIN TRANSACTION;
                          
                         ALTER TABLE BookTags RENAME TO temp_table;
                         CREATE TABLE BookTags(
                                      book_id INTEGER NOT NULL,
                                      tag_id INTEGER NOT NULL,
                                      FOREIGN KEY (book_id) REFERENCES Books(id)
                                      ON DELETE CASCADE,
                                      FOREIGN KEY (tag_id) REFERENCES Tags(tag_id)
                                      ON DELETE CASCADE,
                                      PRIMARY KEY (book_id, tag_id));
                         INSERT INTO BookTags (book_id, tag_id)
                            SELECT book_id, tag_id
                            FROM temp_table;
                        DROP TABLE temp_table;
                        DROP TRIGGER IF EXISTS set_last_change_tsumino;
                        DROP TRIGGER IF EXISTS set_last_change_tags_ins;
                        DROP TRIGGER IF EXISTS set_last_change_tags_del;
                        DROP TRIGGER IF EXISTS update_downloaded_on_tags_insert;
                        DROP TRIGGER IF EXISTS update_downloaded_on_tags_delete;
                        DROP TRIGGER IF EXISTS update_favorite_on_tags_delete;
                        DROP TRIGGER IF EXISTS update_favorite_on_tags_insert;
                        COMMIT;
                        PRAGMA foreign_keys=on;""")                     

    c.execute("""CREATE TRIGGER set_last_change_tsumino
                 AFTER UPDATE ON Books
                 BEGIN
                    UPDATE Books
                    SET last_change = DATE('now', 'localtime')
                    WHERE id = NEW.id;
                 END""")

    # set last_change on Books when new tags get added in bridge table
    c.execute("""CREATE TRIGGER set_last_change_tags_ins
                 AFTER INSERT ON BookTags
                 BEGIN
                    UPDATE Books
                    SET last_change = DATE('now', 'localtime')
                    WHERE id = NEW.book_id;
                 END""")

    # set last_change on Books when tags get removed in bridge table
    c.execute("""CREATE TRIGGER set_last_change_tags_del
                 AFTER DELETE ON BookTags
                 BEGIN
                    UPDATE Books
                    SET last_change = DATE('now', 'localtime')
                    WHERE id = OLD.book_id;
                 END""")

    # also do this the other way around -> if downloaded get set also add "li_downloaded" to tags?
    # set downloaded to 1 if book gets added to li_downloaded
    c.execute("""CREATE TRIGGER update_downloaded_on_tags_insert
                 AFTER INSERT ON BookTags
                                 WHEN NEW.tag_id IN (
                                 SELECT tag_id FROM Tags WHERE name = 'li_downloaded')
                 BEGIN
                    UPDATE Books
                    SET downloaded = 1
                    WHERE id = NEW.book_id;
                 END""")

    # set downloaded to 0 if book gets removed from li_downloaded
    c.execute("""CREATE TRIGGER update_downloaded_on_tags_delete
                 AFTER DELETE ON BookTags
                                 WHEN OLD.tag_id IN (
                                 SELECT tag_id FROM Tags WHERE name = 'li_downloaded')
                 BEGIN
                    UPDATE Books
                    SET downloaded = 0
                    WHERE id = OLD.book_id;
                 END""")

    # set favorite to 1 if book gets added to li_best
    c.execute("""CREATE TRIGGER update_favorite_on_tags_insert
                 AFTER INSERT ON BookTags
                                 WHEN NEW.tag_id IN (
                                 SELECT tag_id FROM Tags WHERE name = 'li_best')
                 BEGIN
                    UPDATE Books
                    SET favorite = 1
                    WHERE id = NEW.book_id;
                 END""")

    # set favorite to 0 if book gets removed from li_best
    c.execute("""CREATE TRIGGER update_favorite_on_tags_delete
                 AFTER DELETE ON BookTags
                                 WHEN OLD.tag_id IN (
                                 SELECT tag_id FROM Tags WHERE name = 'li_best')
                 BEGIN
                    UPDATE Books
                    SET favorite = 0
                    WHERE id = OLD.book_id;
                 END""")
