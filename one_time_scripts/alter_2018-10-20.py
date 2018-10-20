import sqlite3

db_con = sqlite3.connect("./manga_db.sqlite", detect_types=sqlite3.PARSE_DECLTYPES)
db_con.row_factory = sqlite3.Row

with db_con:
    c = db_con.executescript("""
                PRAGMA foreign_keys=off;

                BEGIN TRANSACTION;

                DROP INDEX IF EXISTS id_onpage_on_site;
                CREATE INDEX IF NOT EXISTS idx_id_onpage_imported_from ON
                ExternalInfo (id_onpage, imported_from);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_artist_name ON Artist (name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_category_name ON Category (name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_character_name ON Character (name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_name ON Collection (name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_name ON Groups (name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_list_name ON List (name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_parody_name ON Parody (name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tag_name ON Tag (name);

                DROP TRIGGER IF EXISTS set_last_update_ext_info;

                COMMIT;

                PRAGMA foreign_keys=on;
                """)
