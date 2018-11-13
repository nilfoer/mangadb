import os
import sqlite3
import logging
import datetime
import pytest

from utils import setup_mdb_dir, all_book_info
from manga_db.manga_db import MangaDB


TESTS_DIR = os.path.dirname(os.path.realpath(__file__))


def test_mdb_readonly(setup_mdb_dir):
    tmpdir, mdb_file = setup_mdb_dir
    mdb = MangaDB(tmpdir, mdb_file, read_only=True)
    with pytest.raises(sqlite3.OperationalError) as e:
        mdb.db_con.execute("INSERT INTO Tag(name) VALUES ('adkada')")
    assert "attempt to write a readonly database" in str(e.value)


def test_mangadb(setup_mdb_dir, monkeypatch, caplog):
    tmpdir, mdb_file = setup_mdb_dir
    tests_files_dir = os.path.join(TESTS_DIR, "mangadb_test_files")
    mdb = MangaDB(tmpdir, mdb_file)

    # English is added by default
    assert mdb.get_language("English") == 1
    assert mdb.get_language(1) == "English"

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
    url = "http://www.tsumino.com/Book/Info/43492/mirai-tantei-nankin-jiken"
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

    # use mount with uri to mount in read-only mode
    db_con = sqlite3.connect('file:../all_test_files/manga_db_to_import.sqlite?mode=ro',
                             uri=True, detect_types=sqlite3.PARSE_DECLTYPES)
    # select same book from db where its already imported and checked
    expected = all_book_info(db_con, 21, include_id=False)

    actual = all_book_info(mdb.db_con, 18, include_id=False)

    for i, v in enumerate(actual):
        if i == 15:
            assert v == "to-read;to-download"
            continue
        elif i == 7:
            # last_change
            assert v == datetime.date.today()
            continue
        elif i == 27:
            # last_update
            assert v == datetime.date.today()
            continue
        assert v == expected[i]

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
            {"url": "http://www.tsumino.com/Book/Info/43551/kinoko-matsuri-mushroom-festival"}))]
            == [2])
    assert ([b.id for b in list(mdb.get_books(
            {"url": "http://www.tsumino.com/Book/Info/43506/gyaru-ijime"}))]
            == [8])
    assert ([b.id for b in list(mdb.get_books({"id_onpage": 43460, "imported_from": 1}))]
            == [11])
    assert ([b.id for b in list(mdb.get_books({"id_onpage": 43454, "imported_from": 1}))]
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
                [{"favorite": "0", "language_id": 1},
                 {"parody": ["Test", "Incl and incl"],
                  "tag": ["Multi Word Tag", "Test1", "Test2"]},
                 {"parody": ["Test and Test2"], "tag": ["Test3", "Test4"]}]),
            ('parody:"!Test and Test2;Test;Incl and incl" title search '
             'tag:!Test3;Test2;!Test4 list:!to-read" '
             'favorite:0 language:English',
                [{"title": "title search", "favorite": "0", "language_id": 1},
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
    assert dictlike["language_id"] == 1
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
