import os
import datetime
import logging
import sqlite3
import pytest

from utils import setup_mdb_dir, all_book_info, load_db_from_sql_file, TESTS_DIR
from manga_db.manga_db import MangaDB
from manga_db.manga import Book
from manga_db.ext_info import ExternalInfo

@pytest.mark.parametrize("title_eng, title_foreign, expected", [
    ("English", "Foreign", "English / Foreign"),
    ("English", None, "English"),
    (None, "Foreign", "Foreign")])
def test_build_title(title_eng, title_foreign, expected):
    assert Book.build_title(title_eng, title_foreign) == expected


def test_fetch_extinfo(monkeypatch, setup_mdb_dir):
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)

    b = Book(mdb, in_db=False, id=16)
    assert b.ext_infos == []

    db_con = memdb
    ei_rows_man = db_con.execute("SELECT * FROM ExternalInfo WHERE id IN (16, 18)").fetchall()
    ei1 = ExternalInfo(mdb, b, **ei_rows_man[0])
    ei2 = ExternalInfo(mdb, b, **ei_rows_man[1])
    assert b._fetch_external_infos() == [ei1, ei2]


def test_fetch_assoc_col(monkeypatch, setup_mdb_dir):
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)

    b = Book(mdb, in_db=False, id=14)
    tags = ["Ahegao", "Anal", "Collar", "Large Breasts", "Maid", "Mind Break",
            "Mind Control",  "Nakadashi", "Office Lady",  "Pantyhose",  "Rape", "Stockings",
            "X-ray"]
    assert sorted(b._fetch_associated_column("tag")) == sorted(tags)
    assert b._fetch_associated_column("character") == []
    assert b._fetch_associated_column("artist") == ["Fan no Hitori"]


def test_upd_assoc_col(monkeypatch, setup_mdb_dir):
    # update_assoc_columns/get_assoc_cols
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))

    mdb = MangaDB(tmpdir, mdb_file)
    db_con = memdb

    # pass last_change kwarg so it doesnt get auto set and counts as change
    b = Book(mdb, in_db=False, id=12, last_change=datetime.date.today())
    ei_row = db_con.execute("SELECT * FROM ExternalInfo WHERE id = 12").fetchone()
    ei = ExternalInfo(mdb, b, **ei_row)
    tags = ("Anal;Femdom;Large Breasts;Nakadashi;Straight Shota;Big Ass;Short Hair;Hat"
            ";Royalty;Dark Skin;Huge Penis;Big Areola;Defloration;Double Penetration;"
            "Elder Sister;Tall Girl".split(";"))
    artists = ["Kaneda Asou"]
    category = ["Doujinshi"]
    groups = ["Dokumushi Shokeitai"]
    lists = ["to-read"]
    assoc_cols = b.get_associated_columns()
    assert assoc_cols["tag"] == tags
    assert assoc_cols["artist"] == artists
    assert assoc_cols["category"] == category
    assert assoc_cols["groups"] == groups
    assert assoc_cols["list"] == lists
    assert assoc_cols["character"] == []
    assert assoc_cols["collection"] == []
    assert assoc_cols["parody"] == []
    assert assoc_cols["ext_infos"] == [ei]
    # upd
    # changes
    b.tag = ["delchange1", "delchange"]
    b.category = ["testcat"]
    b.update_assoc_columns_from_db()
    # changes should be reset
    assert not b._committed_state
    assert b.tag == tags
    assert b.artist == artists
    assert b.category == category
    assert b.groups == groups
    assert b.list == lists
    assert b.character == []
    assert b.collection == []
    assert b.parody == []
    assert b.ext_infos == [ei]

    b = Book(mdb, in_db=False, id=16, last_change=datetime.date.today())
    ei_rows = db_con.execute("SELECT * FROM ExternalInfo WHERE id IN (16, 18)").fetchall()
    ei1 = ExternalInfo(mdb, b, **ei_rows[0])
    ei2 = ExternalInfo(mdb, b, **ei_rows[1])
    tags = ("Blowjob;Ahegao;Megane;Happy Sex;Threesome;Group Sex;Layer Cake;Selfcest".split(";"))
    artists = ["bariun"]
    category = ["Doujinshi"]
    characters = ["Akira Kurusu", "Futaba Sakura"]
    parodies = ["Persona 5 / ペルソナ5"]
    lists = ["to-read"]
    assoc_cols = b.get_associated_columns()
    assert assoc_cols["tag"] == tags
    assert assoc_cols["artist"] == artists
    assert assoc_cols["category"] == category
    assert assoc_cols["groups"] == []
    assert assoc_cols["list"] == lists
    assert assoc_cols["character"] == characters
    assert assoc_cols["collection"] == []
    assert assoc_cols["parody"] == parodies
    assert assoc_cols["ext_infos"] == [ei1, ei2]
    # upd
    # changes
    b.groups = ["delchange1", "delchange"]
    b.artist = ["tartist"]
    b.update_assoc_columns_from_db()
    # changes should be reset
    assert not b._committed_state
    assert b.tag == tags
    assert b.artist == artists
    assert b.category == category
    assert b.groups == []
    assert b.list == lists
    assert b.character == characters
    assert b.collection == []
    assert b.parody == parodies
    assert b.ext_infos == [ei1, ei2]


def test_diff(monkeypatch, setup_mdb_dir):
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)

    # not testing change_str
    b1_data = dict(
            id=None,
            title_eng="Same",
            title_foreign="Different1",
            language_id=1,
            pages=25,
            status_id=1,
            my_rating=4.3,
            category=["Manga"],
            collection=["Diff collection1"],
            groups=["Artistgroup"],
            artist=["Diff1", "Diff2"],
            parody=["Blabla"],
            character=["Char1", "Char2", "Char3"],
            list=["to-read", "to-download"],
            tag=["Tag1", "Tag2", "Tag3"],
            ext_infos=None,
            last_change=datetime.date(2018, 6, 3),
            note=None,
            favorite=0
            )
    b1 = Book(mdb, **b1_data)

    b2_data = dict(
            id=None,
            title_eng="Same",
            title_foreign="Different2",
            language_id=1,
            pages=27,
            status_id=1,
            my_rating=None,
            category=["Manga"],
            collection=["Diff collection2"],
            groups=["Artistgroup"],
            artist=["Diff", "Diff2", "Diff3"],
            parody=["Blabla"],
            character=["Char1", "Char5", "Char3"],
            list=["to-read", "to-download"],
            tag=["Tag1", "Tag2", "Tag3"],
            ext_infos=None,
            last_change=datetime.date(2018, 4, 3),
            note=None,
            favorite=1
            )
    b2 = Book(mdb, **b2_data)

    changes, change_str = b1.diff(b2)
    changes_expected = dict(
            title_foreign="Different2",
            pages=27,
            my_rating=None,
            # added removed
            collection=({"Diff collection2"}, {"Diff collection1"}),
            artist=({"Diff", "Diff3"}, {"Diff1"}),
            character=({"Char5"}, {"Char2"}),
            last_change=datetime.date(2018, 4, 3),
            favorite=1
            )
    assert changes == changes_expected


def test_add_rem_assoc(monkeypatch, setup_mdb_dir):
    # _add/_remove assoc col
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)
    db_con = memdb

    b = mdb.get_book(5)
    tag_before = b.tag.copy()
    tag_change = ["Test1", "Test2", "Blabla"]
    # _add_associated_column_values doesnt commit
    with mdb.db_con:
        b._add_associated_column_values("tag", tag_change)
    tag = db_con.execute("""
        SELECT group_concat(Tag.name, ';')
        FROM Books, BookTag bt, Tag
        WHERE  Books.id = bt.book_id
        AND Tag.id = bt.tag_id
        AND Books.id = 5""").fetchone()
    assert tag[0].split(";")[-3:] == tag_change

    with mdb.db_con:
        b._remove_associated_column_values("tag", tag_change)
    tag = db_con.execute("""
        SELECT group_concat(Tag.name, ';')
        FROM Books, BookTag bt, Tag
        WHERE  Books.id = bt.book_id
        AND Tag.id = bt.tag_id
        AND Books.id = 5""").fetchone()
    assert tag[0].split(";") == tag_before


def test_static_db_methods(monkeypatch, setup_mdb_dir):
    # static db methods
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)
    db_con = memdb

    tag_before = "Large Breasts;Nakadashi;Blowjob;Threesome;Bikini;Group Sex;Swimsuit".split(";")
    tag_change = ["Test1", "Test2", "Blabla"]
    # before is last arg so staticmethod can set attr on book if its loaded (in id_map)
    Book.add_assoc_col_on_book_id(mdb, 13, "tag", tag_change, tag_before)
    tag = db_con.execute("""
        SELECT group_concat(Tag.name, ';')
        FROM Books, BookTag bt, Tag
        WHERE  Books.id = bt.book_id
        AND Tag.id = bt.tag_id
        AND Books.id = 13""").fetchone()
    assert tag[0].split(";")[-3:] == tag_change

    Book.remove_assoc_col_on_book_id(mdb, 13, "tag", tag_change, tag_before + tag_change)
    tag = db_con.execute("""
        SELECT group_concat(Tag.name, ';')
        FROM Books, BookTag bt, Tag
        WHERE  Books.id = bt.book_id
        AND Tag.id = bt.tag_id
        AND Books.id = 13""").fetchone()
    assert tag[0].split(";") == tag_before

    # load book so its in id_map and make sure add_remove_assoc also sets attr on book
    b = mdb.get_book(16)
    tag_before = ("Blowjob;Ahegao;Megane;Happy Sex;Threesome;Group Sex;"
                  "Layer Cake;Selfcest".split(";"))
    tag_change = ["Test3", "Test4", "Blablabla"]
    # before is last arg so staticmethod can set attr on book if its loaded (in id_map)
    Book.add_assoc_col_on_book_id(mdb, 16, "tag", tag_change, tag_before)
    tag = db_con.execute("""
        SELECT group_concat(Tag.name, ';')
        FROM Books, BookTag bt, Tag
        WHERE  Books.id = bt.book_id
        AND Tag.id = bt.tag_id
        AND Books.id = 16""").fetchone()
    assert tag[0].split(";")[-3:] == tag_change
    # also set attr on book
    assert b.tag[-3:] == tag_change

    Book.remove_assoc_col_on_book_id(mdb, 16, "tag", tag_change, tag_before + tag_change)
    tag = db_con.execute("""
        SELECT group_concat(Tag.name, ';')
        FROM Books, BookTag bt, Tag
        WHERE  Books.id = bt.book_id
        AND Tag.id = bt.tag_id
        AND Books.id = 16""").fetchone()
    assert tag[0].split(";") == tag_before
    # also set attr on book
    assert b.tag == tag_before

    Book.set_favorite_id(mdb, 2, 1)
    fav = db_con.execute("SELECT favorite FROM Books WHERE id = 2").fetchone()
    assert 1 == fav[0]

    b = mdb.get_book(7)
    Book.set_favorite_id(mdb, 7, 1)
    fav = db_con.execute("SELECT favorite FROM Books WHERE id = 7").fetchone()
    assert 1 == fav[0]
    # also set on book
    assert b.favorite == 1

    Book.rate_book_id(mdb, 3, 3.5)
    rat = db_con.execute("SELECT my_rating FROM Books WHERE id = 3").fetchone()
    assert 3.5 == rat[0]

    b = mdb.get_book(8)
    Book.rate_book_id(mdb, 8, 4.25)
    rat = db_con.execute("SELECT my_rating FROM Books WHERE id = 8").fetchone()
    assert 4.25 == rat[0]
    # also set on book
    assert b.my_rating == 4.25


def test_remove_book(monkeypatch, setup_mdb_dir):
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)
    import shutil
    # copy cover
    os.makedirs(os.path.join(tmpdir, "thumbs"))
    cover_path = os.path.join(tmpdir, "thumbs", "16")
    shutil.copy(os.path.join(tmpdir, os.pardir, "book_test_files", "16"), cover_path)
    db_con = memdb

    # book removed and all ext infos
    b = mdb.get_book(16)
    b.remove()
    assert b._in_db is False
    # deleted from id map
    with pytest.raises(KeyError):
        mdb.id_map[b.key]
    b_row = db_con.execute("SELECT id FROM Books WHERE id = 16").fetchall()
    assert not b_row
    ei_rows = db_con.execute("SELECT id FROM ExternalInfo WHERE id IN (16, 18)").fetchall()
    assert not ei_rows

    # cover deleted
    assert not os.path.exists(cover_path)


def test_remove_extinfo(monkeypatch, setup_mdb_dir, caplog):
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)

    b = mdb.get_book(16)
    caplog.clear()
    assert b.remove_ext_info(99) is None
    assert caplog.record_tuples == [
            ("manga_db.manga", logging.ERROR, "No external info with id 99 found!")
            ]
    assert b.remove_ext_info(18) == "https://www.tsumino.com/entry/43454"
    assert len(b.ext_infos) == 1
    assert b.ext_infos[0].id == 16

    assert b.remove_ext_info(16)
    assert not b.ext_infos
    caplog.clear()
    assert b.remove_ext_info(4939) is None
    assert caplog.record_tuples == [
            ("manga_db.manga", logging.WARNING, "No external infos on book with id 16 or not"
                                                " fetched from DB yet!")
            ]


def test_save_book(monkeypatch, setup_mdb_dir, caplog):
    # save: _add _update
    #     incl! _update_assoc_cols ->         "
    tmpdir = setup_mdb_dir
    os.chdir(tmpdir)
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)
    db_con = memdb

    # _add
    ei_data = dict(
                id=None,
                book_id=None,
                url="http://test1.com",
                id_onpage=1111,
                imported_from=1,
                upload_date=datetime.date(2018, 4, 13),
                uploader="Uploader",
                censor_id=1,
                rating=4.19,
                ratings=165,
                favorites=300,
                downloaded=None,
                last_update=None,
                outdated=None,
            )
    b1_data = dict(
            id=None,
            title_eng="Add1",
            title_foreign="Foreign1",
            language_id=1,
            pages=25,
            read_status=13,
            status_id=1,
            my_rating=None,
            category=["Manga"],
            collection=None,
            groups=["Artistgroup"],
            artist=["Diff1", "Diff2"],
            parody=["Blabla"],
            character=["Char1", "Char2", "Char3"],
            list=["to-read", "to-download"],
            tag=["Tag1", "Tag2", "Tag3"],
            ext_infos=None,
            last_change=datetime.date(2018, 6, 3),
            note=None,
            favorite=None
            )
    b1 = Book(mdb, **b1_data)
    ei1 = ExternalInfo(mdb, b1, **ei_data)
    ei2 = ExternalInfo(mdb, b1, **ei_data)
    # will outdate extinfo 8
    ei2.id_onpage = 43506
    b1.ext_infos = [ei1, ei2]
    assert b1._in_db is False

    bid, outdated = b1.save()
    assert bid == 18
    assert b1.id == 18
    # in_db + id_map, committed reset
    assert b1._in_db is True
    assert mdb.id_map[b1.key] is b1
    assert not b1._committed_state
    book_info_db = all_book_info(db_con, 18, include_id=True)
    assert len(book_info_db) == 2
    # fav set correctly
    assert book_info_db[0]["favorite"] == 0
    assert b1.favorite == 0

    compare_cols_row_book_data(b1, book_info_db[0], b1_data, special={"favorite": 0})

    # outdated, list of ext info ids that outdated others
    assert outdated == [20]
    # extinfo saved
    eis = db_con.execute("SELECT id, book_id, id_onpage FROM ExternalInfo "
                         "WHERE id > 18").fetchall()
    assert len(eis) == 2
    assert eis[0]["book_id"] == 18
    assert eis[1]["book_id"] == 18
    assert eis[0]["id_onpage"] == 1111
    assert eis[1]["id_onpage"] == 43506

    # add book with new lang
    b2 = Book(mdb, title_eng="Test2", favorite=1, pages=11, status_id=1)
    b2.language = "Krababbl"
    bid, _ = b2.save()
    assert bid == 19
    assert b2.id == 19
    assert b2.language_id == 2
    lang = db_con.execute("SELECT id FROM Languages WHERE name = 'Krababbl'").fetchall()
    assert lang
    assert lang[0][0] == 2
    brow = db_con.execute("SELECT title_eng, favorite FROM Books WHERE id = 19").fetchone()
    assert brow[0] == "Test2"
    assert brow["favorite"] == 1
    assert b2.favorite == 1
    assert b2._in_db is True
    assert not b2._committed_state
    assert mdb.id_map[b2.key] is b2

    # _update

    bu1 = Book(mdb, id=None, title_eng="Kangofu-san ni Kintama Sakusei Saremashita",
               title_foreign="看護婦さんにキンタマ搾精されました", in_db=False)
    bu1.in_db = True
    # test not updating when block_update kwarg is true
    caplog.clear()
    assert bu1.save(block_update=True) == (None, None)
    assert caplog.record_tuples == [
            ("manga_db.manga", logging.DEBUG,
             f"Book was found in DB(id 15) but saving was blocked due to "
             "block_update option!")
            ]

    bu2 = mdb.get_book(11)
    # dont do anything if no changes
    caplog.clear()
    assert not bu2._committed_state
    assert bu2.save() == (11, None)
    assert caplog.record_tuples == [
            ("manga_db.manga", logging.DEBUG, "No changes to save for book with id 11")
            ]
    assert not bu2._committed_state
    before = bu2.export_for_db()
    # empty assoc list to None
    before.update({col: getattr(bu2, col) if getattr(bu2, col) else None
                   for col in bu2.ASSOCIATED_COLUMNS})
    bu2.language = "adlalad"
    change = {
        "title_eng": "Altered",
        "language_id": 3,
        "my_rating": 4.75,
        "favorite": 1,
        # removed and added
        "tag": ("Large Breasts;Test33;Nakadashi;Ahegao;Gender Bender;Dark Skin;Elf;Body Swap"
                ";Bondage;Filming;Test Tag".split(";")),
        # added
        "artist": ["Taniguchi-san", "Newartist"],
        # same
        "category": ["Manga"],
        # none added
        "character": ["Char111", "Char222"]
            }
    bu2.update_from_dict(change)
    before.update(change)
    bid, _ = bu2.save()
    book_info_db = all_book_info(db_con, 11, include_id=True)
    compare_cols_row_book_data(bu2, book_info_db, before,
                               special={"last_change": datetime.date.today()})
    # committed reset
    assert not bu2._committed_state
    # last_change
    assert bu2.last_change == datetime.date.today()
    assert book_info_db["last_change"] == datetime.date.today()

    bu3 = mdb.get_book(7)
    assert not bu3._committed_state
    before = bu3.export_for_db()
    # empty assoc list to None
    before.update({col: getattr(bu3, col) if getattr(bu3, col) else None
                   for col in bu3.ASSOCIATED_COLUMNS})
    change = {
        "title_foreign": "ForeignAltered",
        "pages": 13,
        "note": "Note blabla",
        # set None
        "tag": None,
        # set None
        "artist": None,
        # changed
        "category": ["Manga"],
        # none added
        "collection": ["Col1", "Col2"],
        "groups": ["Grp1", "Grp2", "Senpenbankashiki"]
            }
    bu3.update_from_dict(change)
    before.update(change)
    bid, _ = bu3.save()
    book_info_db = all_book_info(db_con, 7, include_id=True)
    compare_cols_row_book_data(bu3, book_info_db, before,
                               special={"last_change": datetime.date.today()})
    # committed reset
    assert not bu3._committed_state
    # last_change
    assert bu3.last_change == datetime.date.today()
    assert book_info_db["last_change"] == datetime.date.today()


assoc_concat = {
        "tag": "tags", "artist": "artists", "category": "categories", "character": "characters",
        "collection": "collections", "groups": "groups", "list": "lists", "parody": "parodies"
        }
def compare_cols_row_book_data(book, row, data, special=None):
    if special is None:
        special = {}
    for col in Book.COLUMNS:
        row_val = row[col]
        data_val = data[col]
        if col in special:
            # specific values that are incorrect in data
            assert row_val == special[col]
            assert getattr(book, col) == special[col]
        elif data_val is None:
            # use is comparison for None
            assert row_val is None
            assert getattr(book, col) is None
        else:
            assert row_val == data_val
            assert getattr(book, col) == data_val
    for col in Book.ASSOCIATED_COLUMNS:
        if col == "ext_infos":
            continue
        # look up plural of col to get name of concat assoc col
        col_assoc_concat = assoc_concat[col]
        row_val = row[col_assoc_concat]
        if row_val is not None:
            # row_val is concatted values
            # need sorted to compare (or use set)
            row_val = sorted(row_val.split(";")) if ";" in row_val else [row_val]
        # need sorted to compare (or use set)
        data_val = sorted(data[col]) if data[col] else None
        book_val = getattr(book, col)
        book_val = sorted(book_val) if book_val else book_val
        if col in special:
            # specific values that are incorrect in data
            assert row_val == special[col]
            assert book_val == special[col]
        elif data_val is None:
            # assoc col doesnt return None only empty trackable
            assert row_val is None
            assert book_val == []
        else:
            assert row_val == data_val
            assert book_val == data_val
