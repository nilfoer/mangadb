import os
import shutil
import json
import sqlite3
import pytest

from flask import url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from manga_db.webGUI import create_app
from manga_db.webGUI.mdb import get_mdb

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
    app = create_app(
            test_config={"TESTING": True, "DEBUG": False, "SERVER_NAME": "test.test"},
            instance_path=tmpdir
            )
    client = app.test_client()

    return tmpdir, app, client


def test_login_required(app_setup):
    tmpdir, app, client = app_setup
    response = client.get("/", follow_redirects=False)
    # check for redirect to login page when not authenticated
    assert response.status_code == 302
    with app.app_context():
        assert response.location == url_for('auth.login', _external=True)


def login(app, client, username, password):
    # since were working outside of request context we need to use:
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token123"
    with app.app_context():
        return client.post(url_for("auth.login"), data=dict(
            username=username,
            password=password,
            _csrf_token="token123"
        ), follow_redirects=True)


def test_login(app_setup):
    tmpdir, app, client = app_setup
    assert "USERNAME" not in app.config
    assert "PASSWORD" not in app.config
    resp = login(app, client, "adjakl", "aksak")
    assert b'No registered user!' in resp.data

    app.config["USERNAME"] = "test"
    app.config["PASSWORD"] = generate_password_hash("testpw")
    resp = login(app, client, "test", "testpw")
    assert b'id="foundBooks"' in resp.data

    with app.app_context():
        resp = client.get(url_for("auth.logout"), follow_redirects=True)
    assert b"Login" in resp.data

    resp = login(app, client, "test", "afdaklla")
    assert b'Incorrect username or password' in resp.data
    resp = login(app, client, "adjlkaa", "testpw")
    assert b'Incorrect username or password' in resp.data


def register(app, client, username, password):
    # since were working outside of request context we need to use:
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token123"
    with app.app_context():
        return client.post(url_for("auth.register"), data=dict(
            username=username,
            password=password,
            _csrf_token="token123"
        ), follow_redirects=True)


def test_register(app_setup):
    tmpdir, app, client = app_setup
    assert "USERNAME" not in app.config
    assert "PASSWORD" not in app.config
    resp = register(app, client, "test", "")
    assert b"Password is required" in resp.data
    resp = register(app, client, "", "testpw")
    assert b"Username is required" in resp.data

    pw = "testpwpwp"
    resp = register(app, client, "testu", pw)
    assert b"Login" in resp.data
    assert app.config["USERNAME"] == "testu"
    # cant check hash directly since it changes every time even for the same pw
    # due to salting
    assert check_password_hash(app.config["PASSWORD"], pw)
    with open(os.path.join(tmpdir, "admin.txt"), "r", encoding="UTF-8") as f:
        lines = f.read().splitlines()
    assert len(lines) == 2
    assert lines[0] == "testu"
    assert app.config["PASSWORD"] == lines[1]

    resp = register(app, client, "aadkal", "adljaask")
    assert b"Only one user allowed" in resp.data


def test_csrf_token(app_setup):
    tmpdir, app, client = app_setup
    # since were working outside of request context we need to use:
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token123"
    with app.app_context():
        resp = client.post(url_for("auth.login"), data=dict(
                    username="test",
                    password="testpw",
                    _csrf_token="token123"
                ), follow_redirects=True)
        assert resp.status_code == 200

        # need to manually set csrf token since were not using generate_csrf_token functions
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"

        resp = client.post(url_for("auth.login"), data=dict(
                    username="test",
                    password="testpw",
                    _csrf_token="tokeninvalid"
                ), follow_redirects=True)
        assert resp.status_code == 403

        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        # ajax
        resp = client.post(
                url_for("auth.login"),
                data=dict(
                    username="test",
                    password="testpw",
                ),
                headers={
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': 'invalidtoken'
                }, follow_redirects=True)
        assert resp.status_code == 403

        with client.session_transaction() as sess:
            # asser new token was generated
            # since it does this automatically for ajax requests
            assert sess["_csrf_token"] != "token123"
            new_token = sess["_csrf_token"]

        resp = client.post(
                url_for("auth.login"),
                data=dict(
                    username="test",
                    password="testpw",
                ),
                headers={
                    # ajax woudl normally use: 'Content-Type': 'application/json',
                    # but login doesnt support that
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': new_token
                }, follow_redirects=True)
        assert resp.status_code == 200

        with client.session_transaction() as sess:
            assert resp.headers["X-CSRFToken"] == sess["_csrf_token"]


def list_action_ajax(app, client, action, book_id, name, before):
    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        url = url_for("main.list_action_ajax", book_id=book_id, action=action)
        resp = client.post(
                    url,
                    data={
                        "name": name,
                        "before[]": before
                        },
                    headers={
                        # 'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': "token123"
                        })
        return resp


def setup_authenticated_sess(app, client):
    with client.session_transaction() as sess:
        sess["authenticated"] = True


def test_list_action_ajax(app_setup):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)
    resp = list_action_ajax(app, client, "add", 9, None, [])
    with app.app_context():
        # print(resp.content_type, resp.content_length, resp.data, resp.headers, resp.is_json,
        #       resp.response, resp.status)
        assert resp.is_json
        # weird behaviour in flask where <jsonfiy Response>.json uses single quotes for json
        # strings whereas JSON specifies double quotes for strings
        # jsonify returns response -> access json directly on it with attr json
        assert resp.json == jsonify({'error': 'Missing list name from data!'}).json

        # not testing that list also gets set on Book instance if its in id_map
        # that behaviour is tested in test_book and we cant properly test it here
        # since the mdb instance will be on another thread
        resp = list_action_ajax(app, client, "add", 9, "test-list", ["to-read"])
        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        # order by doesnt work with group_concat
        # so use a subselect with the order by clause in, and then group concat the values
        list_s = db_con.execute("""SELECT id, group_concat(name, ';')
                                   FROM (
                                           SELECT b.id, l.name
                                           FROM Books b, List l, BookList bl
                                           WHERE bl.book_id = b.id
                                           AND bl.list_id = l.id
                                           AND b.id = 9
                                           ORDER BY l.name
                                        )
                                   GROUP BY id
                                   """).fetchone()
        assert list_s[1] == "test-list;to-read"

        resp = list_action_ajax(app, client, "remove", 9, "to-read", ["to-read", "test-list"])
        # order by doesnt work with group_concat
        # so use a subselect with the order by clause in, and then group concat the values
        list_s = db_con.execute("""SELECT id, group_concat(name, ';')
                                   FROM (
                                           SELECT b.id, l.name
                                           FROM Books b, List l, BookList bl
                                           WHERE bl.book_id = b.id
                                           AND bl.list_id = l.id
                                           AND b.id = 9
                                           ORDER BY l.name
                                        )
                                   GROUP BY id
                                   """).fetchone()
        assert list_s[1] == "test-list"

        resp = list_action_ajax(app, client, "invalid_action", 9, "to-read", [])
        assert resp.is_json
        assert resp.json == jsonify({"error": ("Supplied action 'invalid_action' is not a "
                                               "valid list action!")}).json
