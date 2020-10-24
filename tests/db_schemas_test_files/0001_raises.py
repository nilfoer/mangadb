date = '2020-10-22'


def upgrade(db_con):
    db_con.execute("ALTER TABLE Books RENAME TO rolled_back")
    raise Exception('testing exception raised')
