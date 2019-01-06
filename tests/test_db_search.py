import os
from utils import setup_mdb_dir, TESTS_DIR

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
            ("Books.id dcse", False),
            ("id", True),
            ("last_change", True),
            ("DELETE", False),

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
            (("top", "Books.id DESC", -1, None), 12, 2),
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
    db_file = os.path.join(TESTS_DIR, "db_test_files", "manga_db.sqlite")
    mdb = MangaDB(os.path.dirname(db_file), db_file, read_only=True)

    args_expected = [
            # after and before none
            (
                ("""SELECT Books.id
                   FROM Books
                   ORDER BY Books.id DESC
                   LIMIT 10""", [], None, None, "Books.id DESC", True),
                (2802, 2801, 2800, 2799, 2798, 2797, 2796, 2795, 2794, 2793)
            ),
            (
                ("""SELECT Books.id
                   FROM Books
                   WHERE pages = ?
                   ORDER BY Books.title_foreign ASC
                   LIMIT 10""",
                 [15], (None, 1600), None, "Books.title_foreign ASC", False),
                (2307, 2666, 1782, 1419, 2277, 2759, 2628, 1590, 2622, 2308)
            ),
            (
                ("""SELECT Books.id
                    FROM Books, Tag, BookTag
                    WHERE Books.id = BookTag.book_id
                    AND Tag.id = BookTag.tag_id
                    AND Tag.name IN (?,?,?)
                    GROUP BY Books.id HAVING COUNT(Books.id) = 3
                    ORDER BY Books.id DESC
                    LIMIT 10""", ['Large Breasts', 'Anal', 'Blowjob'],
                 (2173,), None, "Books.id DESC", False),
                (2166, 2149, 2147, 2140, 2128, 2123, 2121, 2106, 2105, 2093)
            ),
            (
                ("""SELECT Books.id
                    FROM Books, List, BookList
                    WHERE Books.id = BookList.book_id
                    AND List.id = BookList.list_id
                    AND List.name IN (?,?)
                    GROUP BY Books.id HAVING COUNT(Books.id) = 2
                    ORDER BY Books.title_eng DESC
                    LIMIT 7""", ['downloaded', 'good'],
                 ("Dai Nana Chijo Buntai | Squad 7 - Pervert Women Detachment", 795), None,
                 "Books.title_eng DESC", False),
                (773, 758, 752, 762, 754, 792, 761)
            ),
            # no after/before, but non-unique sorting col
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC
                   LIMIT 10""", [], None, None, "Books.title_foreign ASC", True),
                (7, 11, 13, 15, 24, 25, 38, 42, 57, 60)
            ),
            # forwards(after), ASC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC
                   LIMIT 7""", [], (None, 2789), None,
                 "Books.title_foreign ASC", True),
                (2793, 2801, 2802, 158, 2457, 422, 1292)
            ),
            # forwards(after), ASC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC
                   LIMIT 7""", [], ("18号に毎日無理やりザーメン搾り取られる本", 1886), None,
                 "Books.title_foreign ASC", True),
                (1570, 865, 761, 1719, 526, 1446, 1079)
            ),
            # forwards(after), DESC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   WHERE Books.title_eng LIKE ?
                   ORDER BY Books.title_foreign DESC
                   LIMIT 7""", ["%girl%"], (None, 2611), None,
                 "Books.title_foreign DESC", False),
                (2608, 2522, 2521, 2465, 2390, 2379, 2327)
            ),
            # forwards(after), DESC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign DESC
                   LIMIT 7""", [], ("10まで数えるっす!", 1292), None,
                 "Books.title_foreign DESC", True),
                (422, 2457, 158, 2802, 2801, 2793, 2789)
            ),
            # backwards(before), ASC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC
                   LIMIT 7""", [], None, (None, 2729),
                 "Books.title_foreign ASC", True),
                (2710, 2715, 2723, 2724, 2725, 2727, 2728)
            ),
            # backwards(before), ASC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   WHERE Books.title_eng LIKE ?
                   ORDER BY Books.title_foreign ASC
                   LIMIT 13""", ["%hot%"], None, ("お姉さんサーヴァントとショタマスターがズッコンバッコンする本", 1946),
                 "Books.title_foreign ASC", False),
                (1837, 1939, 2120, 2134, 2313, 2627, 2155, 2198, 452, 1109, 2232, 2675, 2674)
            ),
            # backwards(before), DESC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.my_rating DESC
                   LIMIT 7""", [], None, (None, 2797),
                 "Books.my_rating DESC", True),
                (1012, 2784, 2799, 2790, 2802, 2801, 2798)
            ),
            # backwards(before), DESC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.my_rating DESC""", [], None, (3.5, 2784),
                 "Books.my_rating DESC", True),
                (2800, 1780, 2745, 1896, 1508, 1016, 1012)
            ),
            ]

    for args, expected in args_expected:
        q, vals = keyset_pagination_statment(*args)
        c = mdb.db_con.execute(q, vals)
        rows = c.fetchall()
        ids = tuple(b["id"] for b in rows)
        assert ids == expected


def test_keyset_pagination_statement():
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
                   ORDER BY Books.id DESC""", [15], None, (20,), "Books.id DESC", False),
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
                   ORDER BY Books.pages ASC""", [], (20, 25), None, "Books.pages ASC", True),
                ("""SELECT *
                FROM Books
                WHERE (Books.pages > ? OR (Books.pages == ? AND Books.id > ?) )
                ORDER BY Books.pages ASC, Books.id ASC""", [20, 20, 25])  # empty tuple is () not (,)
            ),
            # assoc col after
            (
                ("""SELECT Books.*
                   FROM Books, BookTag bt, Tag t,
                   WHERE Books.id = bt.book_id
                   AND bt.tag_id = t.id
                   AND t.name IN (?, ?, ?)
                   GROUP BY Books.id
                   ORDER BY Books.title_eng DESC""", [1, 2, 3], ("test_title", 15),
                 None, "Books.title_eng DESC", False),
                ("""SELECT Books.*
                   FROM Books, BookTag bt, Tag t,
                   WHERE Books.id = bt.book_id
                   AND bt.tag_id = t.id
                   AND t.name IN (?, ?, ?)
                   AND (Books.title_eng < ? OR (Books.title_eng == ? AND Books.id < ?) OR (Books.title_eng IS NULL))
                   GROUP BY Books.id
                   ORDER BY Books.title_eng DESC, Books.id DESC""", [1, 2, 3, "test_title", "test_title", 15])  # empty tuple is () not (,)
            ),
            # assoc col before
            (
                ("""SELECT Books.*
                   FROM Books, BookTag bt, Tag t,
                   WHERE Books.id = bt.book_id
                   AND bt.tag_id = t.id
                   AND t.name IN (?, ?, ?)
                   GROUP BY Books.id
                   ORDER BY Books.id DESC""", [1, 2, 3], None, [100], "Books.id DESC", False),
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
            ),
            # no after/before, but non-unique sorting col
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC""", [], None, None,
                 "Books.title_foreign ASC", True),
                ("""SELECT *
                FROM Books
                ORDER BY Books.title_foreign ASC, Books.id ASC""", [])
            ),
            # forwards(after), ASC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC""", [], (None, 250), None,
                 "Books.title_foreign ASC", True),
                ("""SELECT *
                FROM Books
                WHERE (Books.title_foreign > ? OR (Books.title_foreign IS NULL AND Books.id > ?) OR (Books.title_foreign IS NOT NULL))
                ORDER BY Books.title_foreign ASC, Books.id ASC""", [None, 250])
            ),
            # forwards(after), ASC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC""", [], ("test", 250), None,
                 "Books.title_foreign ASC", True),
                ("""SELECT *
                FROM Books
                WHERE (Books.title_foreign > ? OR (Books.title_foreign == ? AND Books.id > ?) )
                ORDER BY Books.title_foreign ASC, Books.id ASC""", ["test", "test", 250])
            ),
            # forwards(after), DESC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   WHERE Books.title_foreign LIKE ?
                   ORDER BY Books.title_foreign DESC""", ["%test%"], (None, 250), None,
                 "Books.title_foreign DESC", False),
                ("""SELECT *
                FROM Books
                WHERE Books.title_foreign LIKE ?
                AND (Books.title_foreign < ? OR (Books.title_foreign IS NULL AND Books.id < ?) )
                ORDER BY Books.title_foreign DESC, Books.id DESC""", ["%test%", None, 250])
            ),
            # forwards(after), DESC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   WHERE Books.title_foreign LIKE ?
                   ORDER BY Books.title_foreign DESC""", ["%test%"], ("ftitle", 250), None,
                 "Books.title_foreign DESC", False),
                ("""SELECT *
                FROM Books
                WHERE Books.title_foreign LIKE ?
                AND (Books.title_foreign < ? OR (Books.title_foreign == ? AND Books.id < ?) OR (Books.title_foreign IS NULL))
                ORDER BY Books.title_foreign DESC, Books.id DESC""", ["%test%", "ftitle", "ftitle", 250])
            ),
            # backwards(before), ASC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign ASC""", [], None, (None, 250),
                 "Books.title_foreign ASC", True),
                ("""SELECT *
                    FROM (
                       SELECT *
                       FROM Books
                       WHERE (Books.title_foreign < ? OR (Books.title_foreign IS NULL AND Books.id < ?) )
                       ORDER BY Books.title_foreign DESC, Books.id DESC
                   ) AS t
                   ORDER BY t.title_foreign ASC, t.id ASC
                """, [None, 250])
            ),
            # backwards(before), ASC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   WHERE Books.title_foreign LIKE ?
                   ORDER BY Books.title_foreign ASC""", ["%alfa%"], None, ("test", 250),
                 "Books.title_foreign ASC", False),
                ("""SELECT *
                    FROM (
                       SELECT *
                       FROM Books
                       WHERE Books.title_foreign LIKE ?
                       AND (Books.title_foreign < ? OR (Books.title_foreign == ? AND Books.id < ?) OR (Books.title_foreign IS NULL))
                       ORDER BY Books.title_foreign DESC, Books.id DESC
                   ) AS t
                   ORDER BY t.title_foreign ASC, t.id ASC
                """, ["%alfa%", "test", "test", 250])
            ),
            # backwards(before), DESC, NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign DESC""", [], None, (None, 250),
                 "Books.title_foreign DESC", True),
                ("""SELECT *
                    FROM (
                       SELECT *
                       FROM Books
                       WHERE (Books.title_foreign > ? OR (Books.title_foreign IS NULL AND Books.id > ?) OR (Books.title_foreign IS NOT NULL))
                       ORDER BY Books.title_foreign ASC, Books.id ASC
                   ) AS t
                   ORDER BY t.title_foreign DESC, t.id DESC
                """, [None, 250])
            ),
            # backwards(before), DESC, NOT NULL value as primary
            (
                ("""SELECT *
                   FROM Books
                   ORDER BY Books.title_foreign DESC""", [], None, ("test", 250),
                 "Books.title_foreign DESC", True),
                ("""SELECT *
                    FROM (
                       SELECT *
                       FROM Books
                       WHERE (Books.title_foreign > ? OR (Books.title_foreign == ? AND Books.id > ?) )
                       ORDER BY Books.title_foreign ASC, Books.id ASC
                   ) AS t
                   ORDER BY t.title_foreign DESC, t.id DESC
                """, ["test", "test", 250])
            ),
            ]

    for args, expected in args_expected:
        q, vals = keyset_pagination_statment(*args)
        # remove format
        q = [l.strip() for l in q.splitlines() if l.strip()]
        exp_q, exp_v = expected
        exp_q = [l.strip() for l in exp_q.splitlines() if l.strip()]
        assert q == exp_q
        assert vals == exp_v


def test_search_normal_mult_assoc(setup_mdb_dir):
    tmpdir, mdb_file = setup_mdb_dir
    mdb = MangaDB(tmpdir, mdb_file)
    # db_con, normal_col_values, int_col_values_dict, ex_col_values_dict,
    # order_by="Books.id DESC", limit=-1,  # no row limit when limit is neg. nr
    # after=None, before=None

    args_expected = [
            (
                (
                    # normal col
                    {},
                    # int assoc
                    {},
                    # ex assoc
                    {},
                    # order_by,     limit, after, before
                    "Books.id DESC", -1, None, None
                ),
                list(range(17, 0, -1))
            ),
            (
                (
                    # normal col
                    {},
                    # int assoc
                    {},
                    # ex assoc
                    {},
                    "Books.id DESC", 5, None, None
                ),
                list(range(17, 12, -1))
            ),
            (
                (
                    # normal col
                    {},
                    # int assoc
                    {},
                    # ex assoc
                    {},
                    "Books.id ASC", 4, None, (6,)
                ),
                list(range(2, 6))
            ),
            (
                (
                    # normal col
                    {},
                    # int assoc
                    {},
                    # ex assoc
                    {},
                    "Books.id DESC", 3, (6,), None
                ),
                list(range(5, 2, -1))
            ),
            (
                (
                    # normal col
                    {"pages": 25},
                    # int assoc
                    {},
                    # ex assoc
                    {},
                    "Books.id ASC", -1, None, None
                ),
                [3, 4]
            ),
            (
                (
                    # normal col
                    {"pages": 25},
                    # int assoc
                    {"tag": ["Large Breasts", "Big Ass"]},
                    # ex assoc
                    {},
                    "Books.id DESC", -1, None, None
                ),
                [4, 3]
            ),
            (
                (
                    # normal col
                    {"pages": 25},
                    # int assoc
                    {"tag": ["Large Breasts", "Big Ass"]},
                    # ex assoc
                    {"artist": ["Jirou"]},
                    "Books.id DESC", -1, None, None
                ),
                [3]
            ),
            (
                (
                    # normal col
                    {},
                    # int assoc
                    {"tag": ["Nakadashi"]},
                    # ex assoc
                    {},
                    "Books.id DESC", -1, None, None
                ),
                [17, 15, 14, 13, 12, 11, 10, 9, 8, 6, 5, 4, 3, 2, 1]
            ),
            (
                (
                    # normal col
                    {},
                    # int assoc
                    {"tag": ["Nakadashi"]},
                    # ex assoc
                    {},
                    # order_by,     limit, after, before
                    "Books.id DESC", 5, None, (3,)
                ),
                [9, 8, 6, 5, 4]
            )
        ]

    for args, expected in args_expected:
        rows = search_normal_mult_assoc(mdb.db_con, *args)
        for i, row in enumerate(rows):
            assert row["id"] == expected[i]
