date = '2020-10-22'


def upgrade(db_con, db_filename):
    db_con.execute("ALTER TABLE Books ADD COLUMN test TEXT NOT NULL DEFAULT 'migration success'")
