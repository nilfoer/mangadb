import os
import sqlite3
import logging
import datetime
import pytest

from utils import (
    setup_mdb_dir, all_book_info, load_db_from_sql_file, setup_tmpdir,
    load_db
)
from manga_db.manga_db import (
     MangaDB, cookie_jar, url_opener,
     set_default_user_agent, update_cookies_from_file
)
from manga_db.constants import LANG_IDS


TESTS_DIR = os.path.dirname(os.path.realpath(__file__))


def test_set_default_user_agent():
    url_opener.addheaders = []
    set_default_user_agent('foobar')
    assert url_opener.addheaders == [('User-Agent', 'foobar')]

    url_opener.addheaders = [
        ('USeR-aGenT', 'Mozilla 105.0 ...'),
        ('Accept-Content', 'text/html'),
        ('User', 'testuser')
    ]

    set_default_user_agent('foobar')
    assert url_opener.addheaders == [
        ('User-Agent', 'foobar'),
        ('Accept-Content', 'text/html'),
        ('User', 'testuser')
    ]


def test_update_cookies_from_file(setup_tmpdir):
    tmpdir = setup_tmpdir

    cookies_fn = os.path.join(tmpdir, "cookies.txt")
    with open(cookies_fn, 'w') as f:
        # cookie 'fields' separated by \t
        # first line requires: # Netscape HTTP Cookie File 
        f.write("""# Netscape HTTP Cookie File
# aslkfjldsk
# asfsa User-Agent: sfdlkajslk
# User-Agent: Foo 5.0 (Bar 12402)...
# sdfjslksadf
.github.com\tTRUE\t/\tTRUE\t1943851586\tcf_clearance\tcookievalue123
.github.com\tTRUE\t/repo\tTRUE\t1943851586\tuser_id\tuser321cookie
.mangadex.org\tTRUE\t/\tTRUE\t1943835379\tlogin\t239jfoj32l4k5320ok
""")
    
    default_hdrs = [('User-Agent', 'Mozilla 5.0 (Gecko 1243)...')]
    url_opener.addheaders = default_hdrs
    assert update_cookies_from_file(cookies_fn, has_custom_info=False) is True
    # stil on default user-agent
    assert url_opener.addheaders == default_hdrs
    # mainly testing that the file still parsed correctly with our custom info
    # so only testing the cookies are there with the right value
    assert '.github.com' in cookie_jar._cookies
    git = cookie_jar._cookies['.github.com']
    assert git['/']['cf_clearance'].value == 'cookievalue123'
    assert git['/repo']['user_id'].value == 'user321cookie'
    assert '.mangadex.org' in cookie_jar._cookies
    assert cookie_jar._cookies['.mangadex.org']['/']['login'].value == '239jfoj32l4k5320ok'

    # parse user-agent from comment in file
    assert update_cookies_from_file(cookies_fn, has_custom_info=True) is True
    assert url_opener.addheaders == [('User-Agent', 'Foo 5.0 (Bar 12402)...')]

    # non-existant file
    assert update_cookies_from_file(
            'asdflkjaldsfjlkadsflk5345ksld34534534', has_custom_info=True) is False

    #
    # has_custom_info=True and we don't find a User-Agent => should return False
    #
    with open(cookies_fn, 'w') as f:
        # cookie 'fields' separated by \t
        # first line requires: # Netscape HTTP Cookie File 
        f.write("""# Netscape HTTP Cookie File
# aslkfjldsk
# asfsa User-Agent: sfdlkajslk
# sdfjslksadf
.github.com\tTRUE\t/\tTRUE\t1943851586\tcf_clearance\tcookievalue123
.github.com\tTRUE\t/repo\tTRUE\t1943851586\tuser_id\tuser321cookie
.mangadex.org\tTRUE\t/\tTRUE\t1943835379\tlogin\t239jfoj32l4k5320ok
""")
    assert update_cookies_from_file(cookies_fn, has_custom_info=True) is False
    assert update_cookies_from_file(cookies_fn, has_custom_info=False) is True

    #
    # wrong cookie format
    #
    with open(cookies_fn, 'w') as f:
        # OMIT required first line: # Netscape HTTP Cookie File 
        f.write("""# aslkfjldsk
# asfsa User-Agent: sfdlkajslk
# sdfjslksadf
.github.com\tTRUE\t/\tTRUE\t1943851586\tcf_clearance\tcookievalue123
.github.com\tTRUE\t/repo\tTRUE\t1943851586\tuser_id\tuser321cookie
.mangadex.org\tTRUE\t/\tTRUE\t1943835379\tlogin\t239jfoj32l4k5320ok
""")
    assert update_cookies_from_file(cookies_fn, has_custom_info=True) is False
    assert update_cookies_from_file(cookies_fn, has_custom_info=False) is False


def test_mdb_readonly(monkeypatch, setup_mdb_dir):
    tmpdir = setup_mdb_dir
    sql_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    mdb_file = os.path.join(tmpdir, "manga_db.sqlite")
    memdb = load_db_from_sql_file(sql_file, mdb_file)
    memdb.close()
    mdb = MangaDB(tmpdir, mdb_file, read_only=True)
    with pytest.raises(sqlite3.OperationalError) as e:
        mdb.db_con.execute("INSERT INTO Tag(name) VALUES ('adkada')")
    assert "attempt to write a readonly database" in str(e.value)


def test_mangadb(setup_mdb_dir, monkeypatch, caplog):
    tmpdir = setup_mdb_dir
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    tests_files_dir = os.path.join(TESTS_DIR, "mangadb_test_files")
    mdb = MangaDB(tmpdir, mdb_file)

    # English is added by default
    assert mdb.get_language("English") == LANG_IDS['English']
    assert mdb.get_language(LANG_IDS['English']) == "English"

    lang_id = mdb.get_language("Klingonian", create_unpresent=True)
    assert mdb.get_language(lang_id) == "Klingonian"
    c = mdb.db_con.execute("SELECT id FROM Languages WHERE name = ?", ("Klingonian",))
    lid = c.fetchone()
    assert lid[0] == lang_id
    assert mdb.get_language(34249) is None
    lang_id = mdb.get_language("Rimouka")
    assert lang_id is None
    assert not mdb.db_con.execute("SELECT 1 FROM Languages WHERE name = 'Rimouka'").fetchone()

    os.makedirs(os.path.join(tmpdir, "thumbs"))

    os.chdir(tmpdir)
    url = "http://www.tsumino.com/entry/43492"
    fn = "tsumino_43492_mirai-tantei-nankin-jiken"
    with open(os.path.join(tests_files_dir, fn + ".html"), "r", encoding="UTF-8") as f:
        html = f.read()
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: None)
    cover_url = os.path.join(tests_files_dir, fn).replace("\\", r"/")
    cover_url = f"file:///{cover_url}"
    # patch get_cover to point to thumb on disk
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover",
                        lambda x: cover_url)

    # test no data receieved first
    caplog.clear()
    assert mdb.import_book(url, ["to-read", "to-download"]) == (None, None, None)
    assert caplog.record_tuples == [
            ("manga_db.extractor.tsumino", logging.WARNING,
             f"Extraction failed! HTML was empty for url '{url}'"),
            ("manga_db.manga_db", logging.WARNING,
             f"No book data recieved! URL was '{url}'!"),
            ("manga_db.manga_db", logging.WARNING,
             f"Importing book failed!"),
            ]

    # have to change get_html to retrieve file from disk instead
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: html)
    bid, book, outdated_on_ei_id = mdb.import_book(url, ["to-read", "to-download"])
    assert bid == 18
    assert len(book.ext_infos) == 1
    assert book.ext_infos[0].id == 19
    assert not outdated_on_ei_id

    db_con = load_db_from_sql_file('../all_test_files/manga_db_to_import.sqlite.sql', ":memory:", True)
    # select same book from db where its already imported and checked
    expected = all_book_info(db_con, 21, include_id=False)

    actual = all_book_info(mdb.db_con, 18, include_id=False)

    for (i, k) in enumerate(actual.keys()):
        v = actual[k]
        if k == 'lists':
            assert v == "to-read;to-download"
        elif k == 'last_change':
            assert v == datetime.date.today()
        elif k == 'last_update':
            assert v == datetime.date.today()
        else:
            assert v == expected[k]

    caplog.set_level(logging.DEBUG)
    # clear logging records
    caplog.clear()
    # try to import same book again
    assert mdb.import_book(url, []) == (None, None, None)
    assert ('manga_db.manga_db', logging.INFO,
            f"Book at url '{url}' was already in DB!") in caplog.record_tuples

    # get_book_id
    titles_expected = [
            (("Shukujo no Tashinami | The Lady's Taste", "淑女のたしなみ"), 1),
            (("Top Princess Bottom Princess", "攻め姫受け姫"), 5),
            (("Venus Nights", None), 13)
            ]
    for args, expected in titles_expected:
        assert mdb.get_book_id(*args) == expected

    # get_book
    b15 = mdb.get_book(15)
    assert b15.id == 15
    assert mdb.get_book(title_eng="Venus Nights", title_foreign=None).id == 13
    assert mdb.get_book(title_eng="Dolls Ch. 8", title_foreign="ドールズ 第8話").id == 14
    assert mdb.get_book(title_eng="afnjkagjfk", title_foreign="ajna") is None

    # ensure get_book returns book from id_map if it is already loaded
    tempdb = mdb.db_con
    mdb.db_con = None
    assert mdb.get_book(15) is b15
    mdb.db_con = tempdb

    # get_books + _validate_identifiers; id and titles just calls to get_book
    ids_expected = [
            ({"adakfaro": None}, False),
            ({"id_onpage": None}, False),
            ({"afnasj": None, "id_onpage": None}, False),
            ({"id_onpage": None, "imported_from": None}, True),
            ({"title_eng": None}, False),
            ({"title_eng": None, "title_foreign": None}, True),
            ({"id": None}, True),
            ({"adadak": None, "id": None}, True),
            ({"url": None}, True)
            ]
    for ids, expected in ids_expected:
        assert mdb._validate_indentifiers_types(ids) is expected

    assert ([b.id for b in list(mdb.get_books(
            {"url": "https://www.tsumino.com/entry/43551"}))]
            == [2])
    assert ([b.id for b in list(mdb.get_books(
            {"url": "http://www.tsumino.com/entry/43506"}))]
            == [8])
    assert ([b.id for b in list(mdb.get_books({"id_onpage": '43460', "imported_from": 1}))]
            == [11])
    assert ([b.id for b in list(mdb.get_books({"id_onpage": '43454', "imported_from": 1}))]
            == [16, 10])

    # search_syntax_parser
    arg_li = []
    kwarg_dic = {}

    def save_args(*args, **kwargs):
        arg_li.clear()
        arg_li.extend(args)
        kwarg_dic.clear()
        kwarg_dic.update(kwargs)
        return []
    monkeypatch.setattr("manga_db.manga_db.MangaDB.get_x_books", save_args)
    monkeypatch.setattr("manga_db.db.search.search_normal_mult_assoc", save_args)
    monkeypatch.setattr("manga_db.db.search.search_normal_mult_assoc", save_args)
    # TODO
    searchstr_expected = [
            ("search for title", [{"title": "search for title"}, {}, {}]),
            ("search for title tag:Test1;Test2",
             [{"title": "search for title"}, {"tag": ["Test1", "Test2"]}, {}]),
            ("tag:Test1;Test2 search for title",
             [{"title": "search for title"}, {"tag": ["Test1", "Test2"]}, {}]),
            ('category:Manga search for title tag:"Multi Word Tag;Test1;!Test3;Test2;!Test4"',
                [{"title": "search for title"},
                 {"tag": ["Multi Word Tag", "Test1", "Test2"], "category": ["Manga"]},
                 {"tag": ["Test3", "Test4"]}]),
            ('parody:"!Test and Test2;Test;Incl and incl" pages:25 '
             'tag:"Multi Word Tag;Test1;!Test3;Test2;!Test4" '
             'favorite:0 language:English',
                [{"favorite": "0", "language_id": LANG_IDS['English']},
                 {"parody": ["Test", "Incl and incl"],
                  "tag": ["Multi Word Tag", "Test1", "Test2"]},
                 {"parody": ["Test and Test2"], "tag": ["Test3", "Test4"]}]),
            ('parody:"!Test and Test2;Test;Incl and incl" title search '
             'tag:!Test3;Test2;!Test4 list:!to-read" '
             'favorite:0 language:English',
                [{"title": "title search", "favorite": "0", "language_id": LANG_IDS['English']},
                 {"parody": ["Test", "Incl and incl"],
                  "tag": ["Test2"]},
                 {"parody": ["Test and Test2"], "tag": ["Test3", "Test4"],
                  "list": ["to-read"]}]),
            ]
    caplog.clear()
    for srchstr, expected in searchstr_expected:
        if "pages:" in srchstr:
            mdb._search_sytnax_parser(srchstr, order_by="dad.ad SAA")
            del arg_li[0]
            # not in allowed search types
            caplog.record_tuples == [("manga_db.manga_db", logging.INFO,
                                      "'pages' is not a supported search type!"),
                                     ("manga_db.manga_db", logging.WARNING,
                                      "Sorting dad.ad SAA is not supported")]
            assert arg_li == expected
            continue
        mdb._search_sytnax_parser(srchstr)
        # first arg is connection for search_normal_mult_assoc
        del arg_li[0]
        assert arg_li == expected

    dictlike = {"language": "English", "censorship": "Invalid", "status_id": 1}
    mdb.convert_names_to_ids(dictlike)
    assert dictlike["language_id"] == LANG_IDS['English']
    assert "language" not in dictlike
    assert "censor_id" not in dictlike
    assert "censorship" not in dictlike
    assert dictlike["status_id"] == 1

    dictlike = {"language": "adjkal", "censorship": "Uncensored", "status": "Unknown"}
    mdb.convert_names_to_ids(dictlike)
    assert "language" not in dictlike
    assert "language_id" not in dictlike
    # test that get_language with create_unpresent=False didnt create languages entry
    assert not mdb.db_con.execute("SELECT 1 FROM Languages WHERE name = 'adjkal'").fetchone()
    assert "censorship" not in dictlike
    assert dictlike["censor_id"] == 4
    assert "status" not in dictlike
    assert dictlike["status_id"] == 1


def test_update_in_collection_order(setup_tmpdir):
    tmpdir = setup_tmpdir
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    tmp_db_file = os.path.join(tmpdir, "manga_db.slite")
    db = load_db_from_sql_file(mdb_file, tmp_db_file, True)
    c = db.executemany(
            "INSERT INTO BookCollection(book_id, collection_id, in_collection_idx)"
            "VALUES (?, ?, ?)",
            [(5, 1, 3), (13, 1, 4), (11, 1, 5), (7, 1, 6), (16, 1, 7)])
    db.commit()
    db.close()

    book_id_new_coll_idx = [
        (14, 1),
        (13, 2),
        (11, 3),
        (7,  4),
        (5,  5),
        (3,  6),
        (16, 7),
    ]
    mdb = MangaDB(tmpdir, tmp_db_file)
    mdb.update_in_collection_order(1, book_id_new_coll_idx)
    mdb.db_con.close()

    other_con = load_db(tmp_db_file)
    actual = other_con.execute(
        "SELECT book_id, in_collection_idx FROM BookCollection "
        "WHERE collection_id = 1").fetchall()
    other_con.close()
    assert actual == book_id_new_coll_idx


def test_update_collection_name(setup_tmpdir):
    tmpdir = setup_tmpdir
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    tmp_db_file = os.path.join(tmpdir, "manga_db.slite")
    db = load_db_from_sql_file(mdb_file, tmp_db_file, True)
    c = db.executemany(
            "INSERT INTO BookCollection(book_id, collection_id, in_collection_idx)"
            "VALUES (?, ?, ?)",
            [(5, 1, 3), (13, 1, 4), (11, 1, 5), (7, 1, 6), (16, 1, 7)])
    # add books to other coll for _committed_state verification
    c.executemany("INSERT INTO BookCollection(book_id, collection_id, in_collection_idx)"
                  "VALUES (?, ?, ?)", [(5, 2, 2), (11, 2, 3)])
    db.commit()
    db.close()

    # load some books into the idmap so we can test that their collection
    # lists get updated
    mdb = MangaDB(tmpdir, tmp_db_file)
    # safe ref so it doesnt get deallocated and we can iterate over it later
    in_id_map = [
        mdb.get_book(_id=3),
        mdb.get_book(_id=5),  # also in coll2
        mdb.get_book(_id=7),
        mdb.get_book(_id=11),  # also in coll2
        mdb.get_book(_id=13),
        mdb.get_book(_id=14),
        mdb.get_book(_id=16),
    ]

    # modify some collection values that we later verify in _committed_state
    in_id_map[0].collection.append("Added coll")
    # 11 remove coll2
    coll2 = "Takabisha Elf Kyousei Konin!!"
    in_id_map[3].collection.remove(coll2)
    in_id_map[4].collection = []

    not_in_coll = mdb.get_book(_id=10)  # only one not in coll 1
    
    old_coll_name = "Dolls"
    new_coll_name = "Renamed Collection"
    mdb.update_collection_name(1, new_coll_name)

    other_con = load_db(tmp_db_file)
    actual, = other_con.execute("SELECT name FROM Collection WHERE id = 1").fetchone()
    other_con.close()
    assert actual == new_coll_name

    b4 = mdb.get_collection_info(new_coll_name)

    # make sure the collection lists from books in idmap were update
    # book not in collection was not modified
    assert not_in_coll.collection == [coll2]
    assert not not_in_coll._committed_state

    # verify _committed_state of books that were modified
    assert in_id_map[0].collection == [new_coll_name, "Added coll"]
    assert in_id_map[0]._committed_state['collection'] == [new_coll_name]

    # nothing changed before rename -> only renamed in .collection
    assert in_id_map[1].collection == [new_coll_name, coll2]
    assert 'collection' not in in_id_map[1]._committed_state

    # empty _committed_state for the ones that only have renamed coll
    for i in (2, 5, 6):
        assert in_id_map[i].collection == [new_coll_name]
        assert 'collection' not in in_id_map[i]._committed_state

    # coll2 removed
    assert in_id_map[3].collection == [new_coll_name]
    assert in_id_map[3]._committed_state['collection'] == [new_coll_name, coll2]

    assert in_id_map[4].collection == []
    assert in_id_map[4]._committed_state['collection'] == [new_coll_name]


    assert b4 == mdb.get_collection_info(new_coll_name)
    mdb.db_con.close()

def test_delete_collection(setup_tmpdir):
    tmpdir = setup_tmpdir
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    tmp_db_file = os.path.join(tmpdir, "manga_db.slite")
    db = load_db_from_sql_file(mdb_file, tmp_db_file, True)
    c = db.executemany(
            "INSERT INTO BookCollection(book_id, collection_id, in_collection_idx)"
            "VALUES (?, ?, ?)",
            [(5, 1, 3), (13, 1, 4), (11, 1, 5), (7, 1, 6), (16, 1, 7)])
    # add books to other coll for _committed_state verification
    c.executemany("INSERT INTO BookCollection(book_id, collection_id, in_collection_idx)"
                  "VALUES (?, ?, ?)", [(5, 2, 2), (11, 2, 3)])
    db.commit()
    db.close()

    # load some books into the idmap so we can test that their collection
    # lists get updated
    mdb = MangaDB(tmpdir, tmp_db_file)
    # safe ref so it doesnt get deallocated and we can iterate over it later
    in_id_map = [
        mdb.get_book(_id=3),
        mdb.get_book(_id=5),  # also in coll2
        mdb.get_book(_id=7),
        mdb.get_book(_id=11),  # also in coll2
        mdb.get_book(_id=13),
        mdb.get_book(_id=14),
        mdb.get_book(_id=16),
    ]

    # modify some collection values that we later verify in _committed_state
    in_id_map[0].collection.append("Added coll")
    # 11 remove coll2
    coll2 = "Takabisha Elf Kyousei Konin!!"
    in_id_map[3].collection.remove(coll2)
    in_id_map[4].collection = []

    not_in_coll = mdb.get_book(_id=10)  # only one not in coll 1
    
    coll_name = "Dolls"
    mdb.delete_collection(1)
    mdb.db_con.close()

    other_con = load_db(tmp_db_file)
    actual = other_con.execute("SELECT name FROM Collection WHERE id = 1").fetchone()
    other_con.close()
    assert actual is None

    # make sure the collection lists from books in idmap were update

    # book not in collection was not modified
    assert not_in_coll.collection == [coll2]
    assert not not_in_coll._committed_state

    # verify _committed_state of books that were modified
    assert in_id_map[0].collection == ["Added coll"]
    assert in_id_map[0]._committed_state['collection'] == []

    # nothing changed before del -> only coll2 in .collection
    assert in_id_map[1].collection == [coll2]
    assert 'collection' not in in_id_map[1]._committed_state

    # empty _committed_state for the ones that only have del coll
    for i in (2, 5, 6):
        assert in_id_map[i].collection == []
        assert 'collection' not in in_id_map[i]._committed_state

    # coll2 removed
    assert in_id_map[3].collection == []
    assert in_id_map[3]._committed_state['collection'] == [coll2]

    # deleted everything but only had deleted collection which is now
    # already removed so it should be empty
    assert in_id_map[4].collection == []
    assert 'collection' not in in_id_map[4]._committed_state
