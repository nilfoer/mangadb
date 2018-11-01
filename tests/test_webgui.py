import os
import shutil
import pytest

from flask import url_for, session, request

from manga_db.webGUI.webGUI import app, mdb

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))


# cant use recommended way of testing since our code fails when it uses
# muliple threads and we dont need the threads since the webgui is only
# supposed to be used by one person
@pytest.fixture
def app_setup():
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

    # setup flask app for testing
    app.config['TESTING'] = True
    app.config['SERVER_NAME'] = "test.test"
    # change mdb connection since we set it up to just use manga_db.sqlite in cwd
    mdb.db_con, _ = mdb._load_or_create_sql_db(os.path.join(tmpdir, "manga_db.sqlite"))
    client = app.test_client()

    return tmpdir, app, client


def test_login_required(app_setup):
    tmpdir, app, client = app_setup
    response = client.get("/", follow_redirects=False)
    # check for redirect to login page when not authenticated
    assert response.status_code == 302
    with app.app_context():
        assert response.location == url_for('auth.login', _external=True)
