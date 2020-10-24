import sys
import os
import shutil
import glob

MODULE_DIR = os.path.abspath(os.path.dirname(__file__))

sys.path.insert(0, os.path.realpath(os.path.join(MODULE_DIR, '..')))
sys.path.insert(0, os.path.realpath(os.path.join(MODULE_DIR, '..', 'tests')))

import manga_db.db.migrate as migrate

from manga_db.db.export import export_to_sql
from utils import load_db_from_sql_file, setup_tmpdir


tmpdir = os.path.join(MODULE_DIR, 'tmp')
try:
    shutil.rmtree(tmpdir)
except FileNotFoundError:
    pass
os.makedirs(tmpdir)

for fn in [f for patt in ['tests/all_test_files/*.sql',
                          'tests/db_test_files/*.sql',
                          'tests/threads_test_files/*.sql'] for f in glob.glob(patt)]:
    if 'db_schemas' in fn:
        # NOTE: IMPORTANT never migrate migration test sql file
        assert False

    db_fn = os.path.join(tmpdir, fn.replace(os.sep, '_').replace(os.altsep, '_'))
    print('Migrating test sql file:', fn)
    # just needed to create a db file
    db_con = load_db_from_sql_file(fn, db_fn)
    db_con.close()

    migrate_db = migrate.Database(db_fn)
    assert migrate_db.upgrade_to_latest()
    os.rename(fn, f"{fn[:-4]}.old.sql")
    # @Hack using migrate_db's db_con
    export_to_sql(fn, migrate_db.db_con)
    migrate_db._close()

shutil.rmtree(tmpdir)
