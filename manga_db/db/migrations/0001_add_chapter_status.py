date = '2021-01-14'
requires_foreign_keys_off = False


def upgrade(db_con, db_filename):
    sql = """
    ALTER TABLE Books
    ADD COLUMN chapter_status TEXT"""

    db_con.execute(sql)
