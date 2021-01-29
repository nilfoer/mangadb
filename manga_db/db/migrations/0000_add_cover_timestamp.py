import os

date = '2020-12-23'
requires_foreign_keys_off = False


def upgrade(db_con, db_filename):
    sql = """
    ALTER TABLE Books
    ADD COLUMN cover_timestamp REAL NOT NULL DEFAULT 0"""

    db_con.execute(sql)

    db_dir = os.path.dirname(db_filename)
    thumbs_dir = os.path.join(db_dir, "thumbs")
    for fn in os.listdir(thumbs_dir):
        orig_path = os.path.join(thumbs_dir, fn)
        os.rename(orig_path, f"{orig_path}_0")
