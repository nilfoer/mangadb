import pytest
import os
import shutil
import json
import pickle


TESTS_DIR = os.path.dirname(os.path.realpath(__file__))


def read_file(fn):
    with open(fn, "r", encoding="UTF-8") as f:
        return f.read()


def write_file_str(fn, s):
    with open(fn, "w", encoding="UTF-8") as w:
        w.write(s)


def import_json(fn):
    json_str = read_file(fn)
    return json.loads(json_str)


def export_json(fn, obj):
    json_str = json.dumps(obj, indent=4, sort_keys=True)
    write_file_str(fn, json_str)


def import_pickle(filename):
    with open(filename, 'rb') as f:
        # The protocol version used is detected automatically, so we do not
        # have to specify it.
        obj = pickle.load(f)
    return obj


def export_pickle(obj, filename):
    with open(filename, 'wb') as f:
        # Pickle the 'data' dictionary using the highest protocol available.
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)


@pytest.fixture
def setup_tmpdir():
    tmpdir = os.path.join(TESTS_DIR, "tmp")
    # we wont return after yielding if the test raises an exception
    # -> better way to delete at start of next test so we also
    # have the possiblity to check the content of tmpdir manually
    # -> but then we also have to except FileNotFoundError since tmpdir
    # might not exist yet
    try:
        shutil.rmtree(tmpdir)
    except FileNotFoundError:
        pass
    os.makedirs(tmpdir)

    return tmpdir
    # yield tmpdir
    # # del dir and contents after test is done


@pytest.fixture
def setup_mdb_dir():
    # we wont return after yielding if the test raises an exception
    # -> better way to delete at start of next test so we also
    # have the possiblity to check the content of tmpdir manually
    # -> but then we also have to except FileNotFoundError since tmpdir
    # might not exist yet
    tmpdir_list = [dirpath for dirpath in os.listdir(TESTS_DIR) if dirpath.startswith(
                   "tmp_") and os.path.isdir(os.path.join(TESTS_DIR, dirpath))]
    for old_tmpdir in tmpdir_list:
        try:
            shutil.rmtree(os.path.join(TESTS_DIR, old_tmpdir))
        except FileNotFoundError:
            pass
        except PermissionError:
            pass

    i = 0
    while True:
        tmpdir = os.path.join(TESTS_DIR, f"tmp_{i}")
        if os.path.isdir(tmpdir):
            i += 1
            continue
        os.makedirs(tmpdir)
        break

    mdb_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite")
    shutil.copy(mdb_file, tmpdir)

    return tmpdir, os.path.join(tmpdir, "manga_db.sqlite")


@pytest.fixture
def setup_tmpdir_param():
    """
    For parametrized pytest fixtures and functions since pytest still accesses
    the tmp directory while switching between params which means we cant delete
    tmpdir -> we try to delete all dirs starting with tmp_ and then we
    create a new tmpdir with name tmp_i where i is the lowest number for which
    tmp_i doesnt exist
    """
    # maybe use @pytest.fixture(autouse=True) -> gets called before and after(with yield)
    # every test

    # we wont return after yielding if the test raises an exception
    # -> better way to delete at start of next test so we also
    # have the possiblity to check the content of tmpdir manually
    # -> but then we also have to except FileNotFoundError since tmpdir
    # might not exist yet
    tmpdir_list = [dirpath for dirpath in os.listdir(TESTS_DIR) if dirpath.startswith(
                   "tmp_") and os.path.isdir(os.path.join(TESTS_DIR, dirpath))]
    for old_tmpdir in tmpdir_list:
        try:
            shutil.rmtree(os.path.join(TESTS_DIR, old_tmpdir))
        except FileNotFoundError:
            pass
        except PermissionError:
            pass

    i = 0
    while True:
        tmpdir = os.path.join(TESTS_DIR, f"tmp_{i}")
        if os.path.isdir(tmpdir):
            i += 1
            continue
        os.makedirs(tmpdir)
        break

    return tmpdir


# The @pytest.fixture(scope="session", autouse=True) bit adds a pytest fixture which will run once
# every test session (which gets run every time you use pytest). The autouse=True tells pytest to
# run this fixture automatically (without being called anywhere else).

# Within the cleanup function, we define the remove_test_dir and use the
# request.addfinalizer(remove_test_dir) line to tell pytest to run the remove_test_dir function once
# it is done (because we set the scope to "session", this will run once the entire testing session
# is done).
@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    """Cleanup tmp directories once we are finished."""
    # DOESNT WORKRKRRKRKRRK
    write_file_str("scopesess.txt", "written")

    def remove_tmp_dirs():
        write_file_str("funct.txt", "written")
        for f in os.listdir(TESTS_DIR):
            print("test")
            if f.startswith("tmp"):
                p = os.path.join(TESTS_DIR, f)
                if os.path.isdir(p):
                    shutil.rmtree(p)
    request.addfinalizer(remove_tmp_dirs)


def all_book_info(db_con, book_id=None, include_id=True):
    # dont get id since ids wont match since order changes every time
    # same for dates
    # order by sth predictable like title_eng
    c = db_con.execute(f"""
            SELECT Books.title_eng, Books.title_foreign, Books.language_id, Books.pages,
                   Books.status_id, Books.my_rating, Books.note, Books.favorite,
                   {'Books.id,' if include_id else ''}
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
            {'ei.id, ei.book_id,' if include_id else ''}
            ei.url, ei.id_onpage, ei.imported_from, ei.upload_date, ei.uploader, ei.censor_id,
            ei.rating, ei.ratings, ei.favorites, ei.downloaded, ei.outdated
            FROM Books
            -- returns one row for each external info, due to outer joins also returns
            -- a row for books without external info
            -- no good way as far as i know to have it as one row (unless i know how many
            -- external infos there are per book and its the same for every book
            -- -> then i could use group_concat or subqueries with limit)
            LEFT JOIN ExternalInfo ei ON Books.id = ei.book_id
            {'WHERE Books.id = ?' if book_id else ''}
            GROUP BY Books.id, ei.id
            ORDER BY Books.title_eng
        """, (book_id,) if book_id else ())
    rows = c.fetchall()
    if rows:
        return rows if len(rows) > 1 else rows[0]
    else:
        return None
