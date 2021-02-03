import os
import shutil
import datetime
import logging
import pytest

from utils import setup_mdb_dir, setup_tmpdir_param, load_db_from_sql_file
from manga_db.db.loading import load_instance
from manga_db.manga_db import MangaDB
from manga_db.ext_info import ExternalInfo


TESTS_DIR = os.path.dirname(os.path.realpath(__file__))

class DummyBook:
    def __init__(self, id_, title):
        self.id = id_
        self.title = title


def get_ei_row(mdb, id_):
    return mdb.db_con.execute("SELECT * FROM ExternalInfo WHERE id = ?", (id_,)).fetchone()


def get_extinfo(mdb, id_):
    ei_row = get_ei_row(mdb, id_)
    ext_info = load_instance(mdb, ExternalInfo, ei_row, None)  # last arg is book
    return ext_info


def test_ext_info(setup_tmpdir_param, monkeypatch, caplog):
    tmpdir = setup_tmpdir_param
    tests_files_dir = os.path.join(TESTS_DIR, "ext_info_test_files")
    sql_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db_to_import.sqlite.sql")
    mdb_file = ":memory:"
    memdb = load_db_from_sql_file(sql_file, mdb_file, True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)

    os.chdir(tmpdir)
    fn = "tsumino_43492_mirai-tantei-nankin-jiken"
    with open(os.path.join(tests_files_dir, fn + ".html"), "r", encoding="UTF-8") as f:
        html = f.read()
    # have to change get_html to retrieve file from disk instead
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: html)

    # update_from_url
    ext_info = get_extinfo(mdb, 22)
    assert ext_info.update_from_url() == ("id_or_book_missing", None)
    ext_info.id = None
    assert ext_info.update_from_url() == ("id_or_book_missing", None)
    ext_info.book = DummyBook(21, "Mirai Tantei Nankin Jiken / 未来探偵軟禁事件")
    assert ext_info.update_from_url() == ("id_or_book_missing", None)
    ext_info.id = 22
    # Scarlet Spy2, date 13->15, 180 users / 1705 favs, prepended tag Added Tag +2 + Uncensored
    assert ext_info.update_from_url() == ("title_missmatch", None)
    status, book = ext_info.update_from_url(force=True)
    assert status == "updated"
    assert ext_info.uploader == "Scarlet Spy2"
    assert ext_info.ratings == 324
    assert ext_info.favorites == 3430
    assert ext_info.censorship == "Uncensored"
    assert ext_info.upload_date == datetime.date(2018, 10, 15)
    assert ext_info.last_update == datetime.date.today()
    assert book.tag[:2] == ["Added Tag", "Added Tag2"]

    # patch retrieve_book_data to return None and "no_data" returened by update..
    monkeypatch.setattr("manga_db.manga_db.MangaDB.retrieve_book_data", lambda x, y: (None, None, None))
    assert ext_info.update_from_url() == ("no_data", None)

    # remove
    ei_del = get_extinfo(mdb, 8)
    ei_del.remove()
    assert ei_del._in_db is False
    # deleted from id map
    with pytest.raises(KeyError):
        mdb.id_map[ei_del.key]
    ei8 = mdb.db_con.execute("SELECT id FROM ExternalInfo WHERE id = 8").fetchone()
    assert not ei8

    # save _add
    # last_update only updates when we update_from_url
    b13 = DummyBook(13, "Venus Nights")
    data = dict(
            book_id=None,  # url="http://tsumino.com/Book/Info/112233/test-url",
            id_onpage='112233', imported_from=1, upload_date=datetime.date(2018, 1, 5),
            uploader="Testuploader", censor_id=1, rating=3.85, ratings=105,
            favorites=200, downloaded=None, last_update=datetime.date(2018, 5, 9), outdated=None
            )
    new_ei = ExternalInfo(mdb, b13, **data)
    ei_id, outdated = new_ei.save()
    assert new_ei._in_db is True
    # added to id_map
    assert mdb.id_map[new_ei.key] is new_ei
    ei_row = get_ei_row(mdb, ei_id)
    for k in data:
        if k == "book_id":
            assert ei_row[k] == 13
        # downloaded and outdated got set properly
        elif k == "downloaded":
            assert ei_row[k] == 0
        elif k == "outdated":
            assert ei_row[k] == 0
        else:
            assert ei_row[k] == data[k]

    # checkt that downloaded and outdated dont get overwritten and are correctly set if None
    b15 = DummyBook(15, "Kangofu-san ni Kintama Sakusei Saremashita / "
                        "看護婦さんにキンタマ搾精されました")
    data = dict(
            book_id=15,   # url="http://tsumino.com/Book/Info/112233/test-url",
            id_onpage='112233', imported_from=1, upload_date=datetime.date(2018, 1, 5),
            uploader="Testuploader", censor_id=1, rating=3.85, ratings=105,
            favorites=200, downloaded=1, last_update=datetime.date(2018, 5, 9), outdated=1
            )
    new_ei = ExternalInfo(mdb, b15, **data)
    # ids dont match
    new_ei.book_id = 99
    with pytest.raises(ValueError):
        new_ei.save()

    # reset id and make more changes
    new_ei.book_id = 15
    new_ei.rating = 4.05
    ei_id, outdated = new_ei.save()
    assert not new_ei._committed_state
    assert new_ei._in_db is True
    # added to id_map
    assert mdb.id_map[new_ei.key] is new_ei
    ei_row = get_ei_row(mdb, ei_id)
    for k in data:
        if k == "rating":
            assert ei_row[k] == 4.05
        # downloaded and outdated got set properly
        else:
            assert ei_row[k] == data[k]

    b13 = DummyBook(None, "Venus Nights")
    data = dict(
            book_id=13,   # url="http://tsumino.com/Book/Info/112233/test-url",
            id_onpage='43460', imported_from=1, upload_date=datetime.date(2018, 1, 5),
            uploader="Testuploader", censor_id=1, rating=3.85, ratings=105,
            favorites=200, downloaded=1, last_update=datetime.date(2018, 5, 9), outdated=1
            )
    new_ei = ExternalInfo(mdb, None, **data)
    # cant save without book or book wihout id
    with pytest.raises(ValueError):
        new_ei.save()
    new_ei.book = b13
    with pytest.raises(ValueError):
        new_ei.save()
    new_ei.book.id = 13
    ei_id, outdated = new_ei.save()
    assert not new_ei._committed_state
    assert new_ei._in_db is True
    # added to id_map
    assert mdb.id_map[new_ei.key] is new_ei
    # test outdated
    assert len(outdated) == 1
    # ei.id, ei.url
    # 11 http://www.tsumino.com/Book/Info/43460/sono-shiroki-utsuwa-ni-odei-o-sosogu
    assert outdated[0][0] == 11
    assert outdated[0][1] == '43460'
    # assert outdated[0][1] == ("http://www.tsumino.com/Book/Info/43460/sono-shiroki-"
    #                           "utsuwa-ni-odei-o-sosogu")
    ei_row = get_ei_row(mdb, ei_id)
    for k in data:
        assert ei_row[k] == data[k]

    # _update
    # add fresh extinfo to update
    b20 = DummyBook(20, "The Super Horny Workplace / "
                        "エロすぎる会社日常にセックスが溶け込んだ世界")
    data = dict(
            book_id=20,   # url="http://tsumino.com/Book/Info/9999/test-url",
            id_onpage='9999', imported_from=1, upload_date=datetime.date(2018, 1, 5),
            uploader="Testuploader", censor_id=1, rating=3.85, ratings=105,
            favorites=175, downloaded=1, last_update=datetime.date(2018, 5, 9), outdated=0
            )
    new_ei = ExternalInfo(mdb, b20, **data)
    ei_id, outdated = new_ei.save()
    assert not new_ei._committed_state
    assert new_ei._in_db is True
    # added to id_map
    assert mdb.id_map[new_ei.key] is new_ei
    ei_row = get_ei_row(mdb, ei_id)
    for k in data:
        assert ei_row[k] == data[k]
    # no changes
    caplog.clear()
    new_ei.save()
    assert not new_ei._committed_state
    assert caplog.record_tuples == [("manga_db.ext_info", logging.DEBUG,
                                     "There were no changes when updating external info "
                                     f"with id {ei_id}")]
    # make changes and save them
    new_ei.rating = 4.55
    new_ei.ratings = 150
    new_ei.downloaded = None
    # downloaded_null -> will get val from db
    # save changes
    new_ei.save()
    assert not new_ei._committed_state
    ei_row = get_ei_row(mdb, ei_id)
    for k in data:
        if k == "rating":
            assert ei_row[k] == 4.55
        elif k == "ratings":
            assert ei_row[k] == 150
        else:
            assert ei_row[k] == data[k]
    # check warn on cens, uploader, upl date, pages + downloaded set to 0

    warn_col_val = {"censor_id": 2, "uploader": "New Uploader",
                    "upload_date": datetime.date.today()}
    for warn_col in ("censor_id", "uploader", "upload_date"):
        caplog.clear()
        setattr(new_ei, warn_col, warn_col_val[warn_col])
        warning_str = (f"Please re-download \"{new_ei.url}\", since the "
                       "change of the following fields suggest that someone has "
                       f"uploaded a new version:\n{new_ei.changed_str()}")
        ei_id, _ = new_ei.save()
        assert not new_ei._committed_state
        ei_row = get_ei_row(mdb, ei_id)
        assert ei_row[warn_col] == warn_col_val[warn_col]
        # check that downloaded was reset since version on page changed
        assert new_ei.downloaded == 0
        assert ei_row["downloaded"] == 0
        assert caplog.record_tuples == [
                ("manga_db.ext_info", logging.WARNING, warning_str),
                ('manga_db.ext_info', logging.INFO, f'Updated ext_info with url "{new_ei.url}" '
                                                    'in database!')
                ]

    # reset to data
    new_ei.update_from_dict(data)
    # save since were changing warn cols (dl will be set to 0)
    new_ei.save()
    new_ei.set_updated()
    new_ei.favorites = 777
    # new_ei.url = "http://changed.com/url"
    new_ei.downloaded = 1
    ei_id, _ = new_ei.save()
    assert not new_ei._committed_state
    ei_row = get_ei_row(mdb, ei_id)
    for k in data:
        if k == "last_update":
            assert ei_row[k] == datetime.date.today()
        elif k == "favorites":
            assert ei_row[k] == 777
        # elif k == "url":
        #     assert new_ei.url == "http://changed.com/url"
        #     assert ei_row[k] == "http://changed.com/url"
        elif k == "downloaded":
            assert ei_row[k] == 1
        else:
            assert ei_row[k] == data[k]


# set_dl_id
def test_set_dl_id(monkeypatch, setup_mdb_dir):
    tmpdir = setup_mdb_dir
    sql_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db_to_import.sqlite.sql")
    mdb_file = ":memory:"
    memdb = load_db_from_sql_file(sql_file, mdb_file, True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)
    ExternalInfo.set_downloaded_id(mdb, 12, 1)
    dled = mdb.db_con.execute("SELECT downloaded FROM ExternalInfo WHERE id = 12").fetchone()
    assert dled[0] == 1
