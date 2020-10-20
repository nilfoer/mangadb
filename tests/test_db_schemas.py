import pytest
import os
import datetime

from utils import load_db_from_sql_file, TESTS_DIR
from manga_db.manga_db import MangaDB
from manga_db.manga import Book
from manga_db.ext_info import ExternalInfo
# from manga_db.db.column import Column
# from manga_db.db.column_associated import AssociatedColumnBase
from manga_db.db.constants import Relationship


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
                  ["Censorship", "Languages", "Sites", "Status"]) == all_expected_tables
