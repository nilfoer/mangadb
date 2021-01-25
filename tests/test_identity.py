import os.path
import pytest

from utils import setup_mdb_dir, load_db_from_sql_file, TESTS_DIR
from manga_db.db.id_map import IndentityMap
from manga_db.db.loading import load_instance
from manga_db.manga_db import MangaDB
from manga_db.manga import Book


class Obj:
    def __init__(self, id_):
        self.id = id_
        self.key = (Obj, (id_,))
        # needed to be added to id_map
        self._in_db = True


def test_id_map():
    id_map = IndentityMap()

    o1 = Obj(1)

    assert not id_map.get(o1.key)
    id_map.add(o1)
    assert id_map.get(o1.key) is o1

    o2 = Obj(2)
    o2._in_db = False

    assert not id_map.get(o2.key)
    id_map.add(o2)
    assert id_map.get(o2.key) is None
    o2._in_db = True
    assert not id_map.get(o2.key)
    id_map.add(o2)
    assert id_map.get(o2.key) is o2

    objs = [Obj(i) for i in range(3, 11)]
    for o in objs:
        assert not id_map.get(o.key)
        id_map.add(o)
        assert id_map.get(o.key) is o

    assert len(id_map) == 10
    assert o1.key in id_map
    assert id_map[o1.key] is o1

    id_map.remove(o1.key)
    assert not id_map.get(o1.key)

    with pytest.raises(KeyError):
        id_map.remove(o1.key)
    id_map.discard(o1.key)

    id_map.discard(o2.key)
    assert not id_map.get(o2.key)


def get_book_row(mdb, _id):
    c = mdb.db_con.execute("SELECT * FROM Books WHERE id = ?", (_id,))
    row = c.fetchone()
    return row if row else None


def test_load_instance(monkeypatch, setup_mdb_dir):
    tmpdir = setup_mdb_dir
    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    memdb = load_db_from_sql_file(mdb_file, ":memory:", True)
    monkeypatch.setattr("manga_db.manga_db.MangaDB._load_or_create_sql_db",
                        lambda x, y, z: (memdb, None))
    mdb = MangaDB(tmpdir, mdb_file)

    b_man = Book(mdb, title_eng="Testbook", language_id=1, pages=11, status_id=1,
                 favorite=0, list=["to-read"], nsfw=0)
    bid, _ = b_man.save()
    b_man_loaded = get_book_row(mdb, bid)
    b_man_loaded = load_instance(mdb, Book, b_man_loaded)
    assert b_man is b_man_loaded
    assert b_man._in_db

    b_1 = get_book_row(mdb, 1)
    b_1 = load_instance(mdb, Book, b_1)
    assert b_1._in_db
    assert mdb.id_map.get(b_1.key) is b_1
    b_2 = get_book_row(mdb, 2)
    b_2 = load_instance(mdb, Book, b_2)
    assert b_2._in_db
    assert mdb.id_map.get(b_2.key) is b_2
