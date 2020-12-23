import pytest
import sys
import os
import datetime
import shutil
import sqlite3
import importlib

from utils import load_db_from_sql_file, TESTS_DIR, setup_tmpdir, load_db
from manga_db.manga_db import MangaDB
from manga_db.manga import Book
from manga_db.ext_info import ExternalInfo
# from manga_db.db.column import Column
# from manga_db.db.column_associated import AssociatedColumnBase
from manga_db.db.constants import Relationship
from manga_db.db.export import export_to_sql
import manga_db.db.migrate as migrate


# make sure test sql files still match schema of our db
def test_sql_test_files():
    mdb = MangaDB('tmp', ':memory:')
    sql_test_files = [
            os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql"),
            os.path.join(TESTS_DIR, "all_test_files", "manga_db_to_import.sqlite.sql"),
            os.path.join(TESTS_DIR, "db_test_files", "manga_db.sqlite.sql"),
            os.path.join(TESTS_DIR, "threads_test_files", "manga_db_base.sqlite.sql"),
            os.path.join(TESTS_DIR, "threads_test_files", "manga_db_expected.sqlite.sql"),
            ]
    # you can get access to table and index names by doing a SELECT on a
    # special table named "SQLITE_MASTER"
    # CREATE TABLE sqlite_master (
    #   type TEXT,
    #   name TEXT,
    #   tbl_name TEXT,
    #   rootpage INTEGER,  -- first B-tree page
    #   sql TEXT  -- _raw_ sql statement that was used to create item
    #   -- ^ (contains different whitespace etc.)
    # );
    # could compare sql (sql table creation statement) or use:
    # pragma table_info('table_name')
    # this pragma returns one row for each column in the named table. Columns in the
    # result set include the column name, data type, whether or not the column
    # can be NULL, and the default value for the column.

    # reset row_factory
    mdb.db_con.row_factory = None
    for sql_file in sql_test_files:
        memdb = load_db_from_sql_file(sql_file, ":memory:", True)
        memdb.row_factory = None
        # same tables and indices
        expected = mdb.db_con.execute(
                "SELECT type, name, tbl_name FROM sqlite_master ORDER BY name").fetchall()
        actual = memdb.execute(
                "SELECT type, name, tbl_name FROM sqlite_master ORDER BY name").fetchall()
        assert expected == actual

        # same table setups: columns, types, nullable etc.
        for exp_row, act_row in zip(expected, actual):
            # Unfortunately pragma statements do not work with parameters
            exp_tbl = mdb.db_con.execute(
                    f"pragma table_info('{exp_row[2]}')").fetchall()
            act_tbl = memdb.execute(
                    f"pragma table_info('{act_row[2]}')").fetchall()
            assert exp_tbl == act_tbl


def find_col_idx(col_name, rows):
    for i, row in enumerate(rows):
        if row['name'] == col_name:
            return i
    else:
        return None


def test_created_db_matches_row_classes():
    mdb = MangaDB('tmp', ':memory:')

    type_map = {
            'INTEGER': int,
            'TEXT': str,
            'REAL': float,
            'DATE': datetime.date,
            }
    all_expected_tables = mdb.db_con.execute(
            "SELECT tbl_name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    all_expected_tables = sorted([r[0] for r in all_expected_tables])

    all_tables = []
    for cls in (Book, ExternalInfo):
        tbl_name = cls.__name__ if cls is not Book else 'Books'
        all_tables.append(tbl_name)
        # cid, name, type, notnull, dflt_value, pk
        cls_table_pragma = mdb.db_con.execute(f"PRAGMA table_info('{tbl_name}')").fetchall()

        # normal columns matching
        col_names_expected = sorted([r['name'] for r in cls_table_pragma])
        col_names_actual = sorted(cls.COLUMNS + cls.PRIMARY_KEY_COLUMNS)
        assert col_names_expected == col_names_actual

        colname_info = {r['name']: r for r in cls_table_pragma}

        for col_name in cls.COLUMNS:
            col = getattr(cls, col_name)
            info = colname_info[col_name]
            assert col.nullable is not bool(info['notnull'])
            try:
                assert col.default == col.type(info['dflt_value'])
            except (AssertionError, TypeError):
                assert (col.default is None and
                        (info['dflt_value'] is None or info['dflt_value'] == 'None'))
            assert col.primary_key is bool(info['pk'])

            # @Hack TODO db creation statement has a typo in it - ignore for now since it
            # has no effect
            if info['type'] == 'INTERGER':
                continue
            assert col.type is type_map[info['type']]

        if cls is ExternalInfo:
            assert cls.ASSOCIATED_COLUMNS is None
            continue

        all_assoc_tables = []
        # NOTE: associated columns can't be tested completely right now
        # since we don't use DBRow classes for the most of the associated cols
        # => only testing that we have the same tables for associated cols
        # those mostly only have a pk id and name anyway
        for assoc_name in cls.ASSOCIATED_COLUMNS:
            col = getattr(cls, assoc_name)
            all_assoc_tables.append(col.table_name)
            try:
                assoc_bridge_table = col.assoc_table
            except AttributeError:
                pass
            else:
                if col.relationship is Relationship.ONETOMANY:
                    assert col.assoc_table is None
                    continue

                assert col.relationship is Relationship.MANYTOMANY
                all_assoc_tables.append(assoc_bridge_table)

                # cid, name, type, notnull, dflt_value, pk
                cls_table_pragma = mdb.db_con.execute(
                        f"PRAGMA table_info('{assoc_bridge_table}')").fetchall()

                # checking keys for bridge table
                col_names_expected = sorted([r['name'] for r in cls_table_pragma])
                col_names_actual = sorted([f"{cls.__name__.lower()}_id",
                                           f"{assoc_name.lower()}_id"])
        all_tables.extend(all_assoc_tables)

    # Censorship, Languages, Sites and Status are extra tables not used by any DBRow object
    # they're used in MangaDB class directly (manual sql code)
    # make unique since we might have duplicate entries: one for the TableName(DBRow) class
    # and one or more as associated column
    all_tables = list(set(all_tables))
    assert sorted(all_tables +
                  ["Censorship", "Languages", "Sites", "Status",
                   migrate.VERSION_TABLE]) == all_expected_tables


def test_export_to_sql(setup_tmpdir):
    tmpdir = setup_tmpdir

    sql_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    db_expected = load_db_from_sql_file(sql_file, ":memory:", True)
    db_expected.row_factory = None

    # same tables, indices and sql stmt
    c_exp = db_expected.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    expected = c_exp.fetchall()

    exported_sql = os.path.join(tmpdir, 'exported.sql')
    export_to_sql(exported_sql, db_expected)
    # export_to_sql uses sqlite3.Row check that it was reset
    assert db_expected.row_factory is None

    db_actual = load_db_from_sql_file(exported_sql, ":memory:", True)
    db_actual.row_factory = None

    # same tables, indices and sql stmt
    c_act = db_actual.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY name")
    actual = c_act.fetchall()
    assert expected == actual

    # technically already the same since we compare sql statements
    # same table setups: columns, types, nullable etc.
    for exp_row, act_row in zip(expected, actual):
        # Unfortunately pragma statements do not work with parameters
        exp_tbl = c_exp.execute(
                f"pragma table_info('{exp_row[2]}')").fetchall()
        act_tbl = c_act.execute(
                f"pragma table_info('{act_row[2]}')").fetchall()
        assert exp_tbl == act_tbl

    # compare all rows of all tables
    for sql_master_row in expected:
        if sql_master_row[0] != 'table':
            continue
        tbl_name = sql_master_row[2]

        expected = c_exp.execute(f"SELECT * FROM {tbl_name}").fetchall()
        actual = c_act.execute(f"SELECT * FROM {tbl_name}").fetchall()
        assert expected == actual


def test_db_migration(setup_tmpdir, monkeypatch, caplog):
    tmpdir = setup_tmpdir
    test_files = os.path.join(TESTS_DIR, 'db_schemas_test_files')

    migrations_dirname = 'migrations'
    tmp_migrations = os.path.join(tmpdir, migrations_dirname)
    # so importlib finds our 'package'
    sys.path.insert(0, tmpdir)
    monkeypatch.setattr("manga_db.db.migrate.MODULE_DIR", tmpdir)
    monkeypatch.setattr("manga_db.db.migrate.MIGRATIONS_PATH", tmp_migrations)
    monkeypatch.setattr("manga_db.db.migrate.LATEST_VERSION", -1)

    tmp_db_fn = os.path.join(tmpdir, 'test.sqlite')
    db = load_db_from_sql_file(os.path.join(test_files, 'manga_db.sqlite.sql'),
                               tmp_db_fn)
    db.close()

    m = migrate.Database(tmp_db_fn)
    assert m.is_versionized is False
    assert m.is_dirty is False
    assert m.version == -1

    #
    # begin transaction, commit, rollback
    #
    with pytest.raises(migrate.DatabaseError, match='No transaction in progress'):
        m._commit()
    with pytest.raises(migrate.DatabaseError, match='No transaction in progress'):
        m._rollback()
    with pytest.raises(migrate.DatabaseError, match=r'Another transaction .* in progress'):
        m._begin_transaction()
        m._begin_transaction()
    m._rollback()
    with pytest.raises(sqlite3.OperationalError, match=r'.*database is locked.*'):
        # main attributes of err are .type, .value and .traceback
        m._begin_transaction()
        assert m.transaction_in_progress is True
        # 2nd param is timeout
        db = sqlite3.connect(tmp_db_fn, 0.1)
        db.execute("SELECT 1 FROM Books LIMIT 1")
    db.close()  # still needs to be closed even though no conection was established
    m._close()

    #
    # alrdy on latest version
    #

    m = migrate.Database(tmp_db_fn)
    assert m.upgrade_to_latest()
    assert m.is_versionized is True
    assert m._is_versionized()
    assert m.is_dirty is False
    assert m.version == -1
    m._close()

    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    migrated_db.close()
    assert len(rows) == 1
    assert rows[0][0] == -1
    assert rows[0][1] == 0

    #
    # check db gets closed when using 'with', last upgrade missing,
    # check bu old version, upgraded one version
    #

    os.makedirs(tmp_migrations)
    migration_0_fn = '0000_add_column.py'
    shutil.copy(os.path.join(test_files, migration_0_fn),
                tmp_migrations)

    monkeypatch.setattr("manga_db.db.migrate.LATEST_VERSION", 1)

    unpatched_load_module = migrate.Migration.load_module

    def patched_load_module(self):
        self.module = importlib.import_module(
                f"{migrations_dirname}.{self.filename.rsplit('.', 1)[0]}")
        self.loaded = True
        self.date = self.module.date
        self.upgrade = self.module.upgrade

    monkeypatch.setattr("manga_db.db.migrate.Migration.load_module", patched_load_module)

    unpatched_close = migrate.Database._close
    close_called = False

    def patched_close(x):
        nonlocal close_called
        close_called = True
        unpatched_close(x)

    monkeypatch.setattr("manga_db.db.migrate.Database._close", patched_close)
    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == -1

        with pytest.raises(migrate.MigrationMissing, match=r"No such version '1'.*"):
            assert not m.upgrade_to_latest()
        assert os.path.isfile(tmp_db_fn + '.bak')
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

    assert close_called
    monkeypatch.setattr("manga_db.db.migrate.Database._close", unpatched_close)

    # above updated to version 0
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db.execute(
            "SELECT test FROM Books LIMIT 1").fetchall()
    migrated_db.close()
    assert rows[0][0] == "migration success"

    # check backup
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == -1
    assert rows[0][1] == 0
    with pytest.raises(sqlite3.OperationalError):
        rows = migrated_db_bu.execute(
                "SELECT test FROM Books LIMIT 1").fetchall()
    migrated_db_bu.close()

    #
    # no migrations to upgrade to latest and already on latest available migration
    # + check backup removed and recopied
    #

    monkeypatch.setattr("manga_db.db.migrate.LATEST_VERSION", 3)

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

        with pytest.raises(migrate.MigrationMissing,
                           match=r"No migrations available .* latest.*"):
            assert not m.upgrade_to_latest()
        assert os.path.isfile(tmp_db_fn + '.bak')
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

    # check backup of now current version
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Books LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()

    #
    # check rolled back changes on exception
    #

    unpatched_rollback = migrate.Database._rollback
    rollback_called = False

    def patched_rollback(x):
        nonlocal rollback_called
        rollback_called = True
        unpatched_rollback(x)

    monkeypatch.setattr("manga_db.db.migrate.Database._rollback", patched_rollback)

    migration_1_fn = '0001_raises.py'
    shutil.copy(os.path.join(test_files, migration_1_fn),
                tmp_migrations)

    monkeypatch.setattr("manga_db.db.migrate.LATEST_VERSION", 1)

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

        with pytest.raises(Exception, match='testing exception raised'):
            assert not m.upgrade_to_latest()
        assert rollback_called
        assert m.is_versionized is True
        assert m.is_dirty is False  # rollback resets this
        assert m.version == 0

    #
    # changes of renaming test column and updating version rolled back!!!
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db.execute(
            "SELECT test FROM Books LIMIT 1").fetchall()
    migrated_db.close()
    assert rows[0][0] == "migration success"

    #
    # backup still on old version
    #
    assert os.path.isfile(tmp_db_fn + '.bak')
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Books LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()

    #
    # patch rollback so we can check that we flagged db as dirty etc.
    #
    rollback_called = False

    def patched_no_rollback(x):
        nonlocal rollback_called
        rollback_called = True
        x.db_con.commit()  # otherwise close just rolls back
        x.db_con.close()

    monkeypatch.setattr("manga_db.db.migrate.Database._rollback", patched_no_rollback)

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 0

        with pytest.raises(Exception, match='testing exception raised'):
            assert not m.upgrade_to_latest()
        assert rollback_called
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 0

    #
    # new version and flagged as dirty
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1] == 1
    rows = migrated_db.execute(
            "SELECT test FROM rolled_back LIMIT 1").fetchall()
    assert rows[0][0] == 'migration success'
    migrated_db.close()

    #
    # backup still on old version
    #
    assert os.path.isfile(tmp_db_fn + '.bak')
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Books LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()

    monkeypatch.setattr("manga_db.db.migrate.Database._rollback", unpatched_rollback)
    #
    # check that DB gets restored from backup if dirty!
    # + that upgrade fails if there is no backup
    #

    # overwrite exception raising migration
    with open(os.path.join(tmp_migrations, migration_1_fn), 'w') as f:
        f.write("date = '2020-10-24'\ndef upgrade(db_con):\n  "
                "db_con.execute('ALTER TABLE Sites RENAME TO no_exc')")
    # needs to be reloaded otherwise cached version will be used
    importlib.reload(m.migrations[1].module)

    # rename backup file to test if upgrading gets aborted
    os.rename(os.path.join(tmpdir, f"{tmp_db_fn}.bak"),
              os.path.join(tmpdir, 'renamed.bak'))

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 1

        with pytest.raises(migrate.DatabaseError, match=r'.*upgrade failed.*no backup.*Aborting!'):
            assert not m.upgrade_to_latest()
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 1

    #
    # new version and flagged as dirty
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1] == 1
    rows = migrated_db.execute(
            "SELECT test FROM rolled_back LIMIT 1").fetchall()
    assert rows[0][0] == 'migration success'
    migrated_db.close()

    # rename back
    os.rename(os.path.join(tmpdir, 'renamed.bak'),
              os.path.join(tmpdir, f"{tmp_db_fn}.bak"))

    caplog.clear()

    #
    # continue with backup
    #

    with migrate.Database(tmp_db_fn) as m:
        assert m.is_versionized is True
        assert m.is_dirty is True
        assert m.version == 1

        assert m.upgrade_to_latest()
        # TODO
        assert "DB is dirty! Restoring from back-up!" in caplog.text
        assert m.is_versionized is True
        assert m.is_dirty is False
        assert m.version == 1
        # db vacuumed
        assert "Optimizing DB after migration" in caplog.text

    #
    # new version
    #
    migrated_db = load_db(tmp_db_fn)
    rows = migrated_db.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1] == 0
    rows = migrated_db.execute(
            "SELECT name FROM no_exc LIMIT 1").fetchall()
    assert rows[0][0] == 'tsumino.com'
    migrated_db.close()

    #
    # backup still on old version
    #
    assert os.path.isfile(tmp_db_fn + '.bak')
    migrated_db_bu = load_db(f"{tmp_db_fn}.bak")
    rows = migrated_db_bu.execute(
            f"SELECT version_id, dirty FROM {migrate.VERSION_TABLE}").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    rows = migrated_db_bu.execute(
            "SELECT test FROM Books LIMIT 1").fetchall()
    assert rows[0][0] == "migration success"
    migrated_db_bu.close()


def test_gather_migrations(setup_tmpdir, monkeypatch):
    tmpdir = setup_tmpdir

    monkeypatch.setattr("manga_db.db.migrate.MODULE_DIR", tmpdir)
    monkeypatch.setattr("manga_db.db.migrate.MIGRATIONS_PATH", tmpdir)

    # create a bunch of empty files in the migration dir
    open(os.path.join(tmpdir, '__init__.py'), 'w').close()
    open(os.path.join(tmpdir, '_private.py'), 'w').close()
    open(os.path.join(tmpdir, '0000_zero.py'), 'w').close()
    open(os.path.join(tmpdir, '0001_one.py'), 'w').close()
    open(os.path.join(tmpdir, '0002_two.py'), 'w').close()
    open(os.path.join(tmpdir, '0003_three.py'), 'w').close()
    open(os.path.join(tmpdir, '0004_four.py'), 'w').close()
    open(os.path.join(tmpdir, '0005_five.py'), 'w').close()
    open(os.path.join(tmpdir, '5432_test.py'), 'w').close()
    open(os.path.join(tmpdir, '1234_7894_test.py'), 'w').close()
    open(os.path.join(tmpdir, 'other.pyc'), 'w').close()
    open(os.path.join(tmpdir, 'other.txt'), 'w').close()
    open(os.path.join(tmpdir, 'other.ini'), 'w').close()

    migrations = migrate.gather_migrations()

    found = [
             '0000_zero.py',
             '0001_one.py',
             '0002_two.py',
             '0003_three.py',
             '0004_four.py',
             '0005_five.py',
             '1234_7894_test.py',
             '5432_test.py']
    assert type(migrations) is dict
    assert sorted([migrations[v].filename for v in migrations]) == sorted(found)

    for v in range(6):
        assert migrations[v].version_id == v and migrations[v].filename == found[v]
    v = 1234
    assert migrations[v].version_id == v and migrations[v].filename == found[6]
    v = 5432
    assert migrations[v].version_id == v and migrations[v].filename == found[7]

    migrations = migrate.gather_migrations(version=3)

    found = [
             '0004_four.py',
             '0005_five.py',
             '1234_7894_test.py',
             '5432_test.py']
    assert type(migrations) is dict
    assert sorted([migrations[v].filename for v in migrations]) == sorted(found)

    v = 4
    assert migrations[v].version_id == v and migrations[v].filename == found[0]
    v = 5
    assert migrations[v].version_id == v and migrations[v].filename == found[1]
    v = 1234
    assert migrations[v].version_id == v and migrations[v].filename == found[2]
    v = 5432
    assert migrations[v].version_id == v and migrations[v].filename == found[3]
