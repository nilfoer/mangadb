import os
import pytest
import sqlite3
import hashlib

from utils import setup_mdb_dir, import_json
from manga_db.threads import import_multiple

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))


def gen_hash_from_file(fname, hash_algo_str, _hex=True):
    # construct a hash object by calling the appropriate constructor function
    hash_obj = hashlib.new(hash_algo_str)
    # open file in read-only byte-mode
    with open(fname, "rb") as f:
        # only read in chunks of size 4096 bytes
        for chunk in iter(lambda: f.read(4096), b""):
            # update it with the data by calling update() on the object
            # as many times as you need to iteratively update the hash
            hash_obj.update(chunk)
    # get digest out of the object by calling digest() (or hexdigest() for hex-encoded string)
    if _hex:
        return hash_obj.hexdigest()
    else:
        return hash_obj.digest()


url_furl_map = import_json(os.path.join(TESTS_DIR, "threads_test_files",
                                        "url_fileurl_map.json"))
def new_get_html(url):
    # url_furl_map maps url to rel path from tests_dir to html file
    fpath = os.path.join(TESTS_DIR, os.path.normpath(url_furl_map[url]))
    with open(fpath, "r", encoding="UTF-8") as f:
        html = f.read()
    return html


def new_get_cover(self):
    # thumbs have same name as html files (minus extension)
    fpath = os.path.join(TESTS_DIR, "threads_test_files", "thumbs",
                         os.path.normpath(url_furl_map[self.url][19:-5]))
    return "file:///" + fpath


# run python -m pytest -m "not slow" to deselect slow tests
@pytest.mark.slow
def test_import_multiple(setup_mdb_dir, monkeypatch):
    tmpdir, mdb_file = setup_mdb_dir
    os.makedirs(os.path.join(tmpdir, "thumbs"))

    os.chdir(tmpdir)
    # have to change get_html to retrieve file from disk instead
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", new_get_html)
    # patch get_cover to point to thumb on disk
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover", new_get_cover)
    url_links = import_json(os.path.join(TESTS_DIR, "threads_test_files",
                                         "to_import_link_collect_resume.json"))
    import_multiple(url_links)
    con_res = sqlite3.connect(mdb_file, detect_types=sqlite3.PARSE_DECLTYPES)
    con_expected = sqlite3.connect(os.path.join(TESTS_DIR, "threads_test_files",
                                                "manga_db_to_import.sqlite"),
                                   detect_types=sqlite3.PARSE_DECLTYPES)
    # order isnt predictable since order depends on how fast html is retrieved
    assert all_table_cells(con_res) == all_table_cells(con_expected)

    con_res.row_factory = sqlite3.Row
    # select new books and check that the cover that was saved under that id
    # matches the acutal cover that belongs to the book
    c = con_res.execute("""SELECT b.id, ei.id_onpage, ei.url
                           FROM Books b, ExternalInfo ei
                           WHERE b.id = ei.book_id
                           AND b.id > 17""")
    rows = c.fetchall()
    # maps id_onpage (str due to json keys) to sha512 checksums
    id_onpagestr_checksum = import_json(os.path.join(TESTS_DIR, "threads_test_files",
                                                     "chksms.json"))
    for row in rows:
        expected = id_onpagestr_checksum[str(row["id_onpage"])]
        actual = gen_hash_from_file(os.path.join(tmpdir, "thumbs", str(row["id"])), "sha512")
        assert actual == expected


def all_table_cells(db_con):
    # dont get id since ids wont match since order changes every time
    # same for dates
    # order by sth predictable like title_eng
    c = db_con.execute("""
            SELECT Books.title_eng, Books.title_foreign, Books.language_id, Books.pages,
                   Books.status_id, Books.my_rating, Books.note, Books.favorite,
                (
                    SELECT group_concat(Tag.name, ';')
                    FROM BookTag bt, Tag
                    WHERE  Books.id = bt.book_id
                    AND Tag.id = bt.tag_id
                ) AS tags,
                (
                    SELECT group_concat(Artist.name, ';')
                    FROM BookArtist bt, Artist
                    WHERE  Books.id = bt.book_id
                    AND Artist.id = bt.artist_id
                ) AS artists,
                (
                    SELECT group_concat(Category.name, ';')
                    FROM BookCategory bt, Category
                    WHERE  Books.id = bt.book_id
                    AND Category.id = bt.category_id
                ) AS categories,
                (
                    SELECT group_concat(Character.name, ';')
                    FROM BookCharacter bt, Character
                    WHERE  Books.id = bt.book_id
                    AND Character.id = bt.Character_id
                ) AS characters,
                (
                    SELECT group_concat(Collection.name, ';')
                    FROM BookCollection bt, Collection
                    WHERE  Books.id = bt.book_id
                    AND Collection.id = bt.Collection_id
                ) AS collections,
                (
                    SELECT group_concat(Groups.name, ';')
                    FROM BookGroups bt, Groups
                    WHERE  Books.id = bt.book_id
                    AND Groups.id = bt.Group_id
                ) AS groups,
                (
                    SELECT group_concat(List.name, ';')
                    FROM BookList bt, List
                    WHERE  Books.id = bt.book_id
                    AND List.id = bt.List_id
                ) AS lists,
                (
                    SELECT group_concat(Parody.name, ';')
                    FROM BookParody bt, Parody
                    WHERE  Books.id = bt.book_id
                    AND Parody.id = bt.Parody_id
                ) AS parodies,
            ei.url, ei.id_onpage, ei.imported_from, ei.upload_date, ei.uploader, ei.censor_id,
            ei.rating, ei.ratings, ei.favorites, ei.downloaded, ei.outdated
            FROM Books
            -- returns one row for each external info, due to outer joins also returns
            -- a row for books without external info
            -- no good way as far as i know to have it as one row (unless i know how many
            -- external infos there are per book and its the same for every book
            -- -> then i could use group_concat or subqueries with limit)
            LEFT JOIN ExternalInfo ei ON Books.id = ei.book_id
            GROUP BY Books.id, ei.id
            ORDER BY Books.title_eng
        """)
    rows = c.fetchall()
    return rows
