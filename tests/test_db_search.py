import pytest

from utils import setup_mdb_dir

from manga_db.manga_db import MangaDB
from manga_db.db.search import (
        search_assoc_col_string_parse, validate_order_by_str, search_book_by_title,
        search_normal_mult_assoc, keyset_pagination_statment
        )


def test_search_assoc_col_string_parse():
    str_expected = [
            ("incl1;incl2;!excl1;incl3", (["incl1", "incl2", "incl3"], ["excl1"])),
            ("incl1;incl2", (["incl1", "incl2"], [])),
            ("!excl1", ([], ["excl1"]))
            ]
    for s, expected in str_expected:
        assert search_assoc_col_string_parse(s) == expected


def test_validate_order_by():
    str_expected = [
            ("Books.id ASC", True),
            ("Books.title_eng DESC", True),
            ("Blabla.id ASC", False),
            ("Books.note ASC", False),
            ("Books.id DESC ; DROP TABLE Books", False),
            ("Books.id DESC;DROP TABLE Books", False),
            ("Books.id dcse", False)
            ]
    for s, expected in str_expected:
        assert validate_order_by_str(s) == expected


def test_search_book_by_title(setup_mdb_dir):
    tmpdir, mdb_file = setup_mdb_dir
    mdb = MangaDB(tmpdir, mdb_file)
    args_first_len = [
            (("atsu", "Books.id DESC", -1, None), 6, 2),
            (("atsu", "Books.id ASC", -1, None), 2, 2),
            (("atsu", "Books.pages DESC", -1, None), 6, 2),
            (("atsu", "Books.id DESC", 1, None), 6, 1),
            (("top", "Books.id DESC", -1, None), 5, 1),
            (("afhnksagjoiks", "Books.id DESC", -1, None), None, None)
            ]

    for args, first, nr in args_first_len:
        rows = search_book_by_title(mdb.db_con, *args)
        if first is None:
            assert not rows
        else:
            assert rows[0]["id"] == first
            assert len(rows) == nr


def test_keyset_pagination():
    args_expected = [
            # after and before none
            (
                ("""SELECT *
                   FROM Books
                   WHERE title LIKE ?
                   ORDER BY Books.id DESC""", ['%atsu%'], None, None, "Books.id DESC", False),
                ("""SELECT *
                FROM Books
                WHERE title LIKE ?
                ORDER BY Books.id DESC""", ['%atsu%'])
            ),
            # normal col before
            (
                ("""SELECT *
                   FROM Books
                   WHERE pages = ?
                   ORDER BY Books.id DESC""", [15], None, 20, "Books.id DESC", False),
                ("""SELECT *
                FROM (
                    SELECT *
                    FROM Books
                    WHERE pages = ?
                    AND Books.id > ?
                    ORDER BY Books.id ASC
                ) AS t
                ORDER BY t.id DESC""", [15, 20])
            ),
            # first cond after
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.pages ASC""", [], 15, None, "Books.pages ASC", True),
                ("""SELECT *
                FROM Books
                WHERE Books.id > ?
                ORDER BY Books.pages ASC""", [15])  # empty tuple is () not (,)
            ),
            # assoc col after
            (
                ("""SELECT Books.*
                   FROM Books, BookTag bt, Tag t,
                   WHERE Books.id = bt.book_id
                   AND bt.tag_id = t.id
                   AND t.name IN (?, ?, ?)
                   GROUP BY Books.id
                   ORDER BY Books.title_eng DESC""", [1, 2, 3], 15, None, "Books.title_eng DESC", False),
                ("""SELECT Books.*
                   FROM Books, BookTag bt, Tag t,
                   WHERE Books.id = bt.book_id
                   AND bt.tag_id = t.id
                   AND t.name IN (?, ?, ?)
                   AND Books.id < ?
                   GROUP BY Books.id
                   ORDER BY Books.title_eng DESC""", [1, 2, 3, 15])  # empty tuple is () not (,)
            ),
            # assoc col before
            (
                ("""SELECT Books.*
                   FROM Books, BookTag bt, Tag t,
                   WHERE Books.id = bt.book_id
                   AND bt.tag_id = t.id
                   AND t.name IN (?, ?, ?)
                   GROUP BY Books.id
                   ORDER BY Books.id DESC""", [1, 2, 3], None, 100, "Books.id DESC", False),
                ("""SELECT *
                   FROM (
                       SELECT Books.*
                       FROM Books, BookTag bt, Tag t,
                       WHERE Books.id = bt.book_id
                       AND bt.tag_id = t.id
                       AND t.name IN (?, ?, ?)
                       AND Books.id > ?
                       GROUP BY Books.id
                       ORDER BY Books.id ASC
                    ) AS t
                   ORDER BY t.id DESC""", [1, 2, 3, 100])  # empty tuple is () not (,)
            )
            ]

    for args, expected in args_expected:
        q, vals = keyset_pagination_statment(*args)
        # remove format
        q = [l.strip() for l in q.splitlines() if l.strip()]
        exp_q, exp_v = expected
        exp_q = [l.strip() for l in exp_q.splitlines() if l.strip()]
        assert q == exp_q
        assert vals == exp_v
