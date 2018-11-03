import os
import shutil
import json
import bs4
import sqlite3
import pytest

from flask import url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from manga_db.webGUI import create_app
from manga_db.webGUI.mdb import get_mdb
from utils import all_book_info

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


def test_show_info(app_setup):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)

    with app.app_context():
        resp = client.get(url_for("main.show_info", book_id=5), follow_redirects=True)
        assert b"Top Princess Bottom Princess" in resp.data
        assert "攻め姫受け姫".encode("utf-8") in resp.data
        r_html = resp.data.decode("utf-8")
        soup = bs4.BeautifulSoup(r_html, "html.parser")
        assert soup.select_one("#Pages").text.strip() == "19"
        assert soup.select_one("#Status").text.strip() == "Unknown"

        lang = soup.select("#Language > a")
        assert len(lang) == 1
        assert lang[0].text.strip() == "English"

        cat = soup.select("#Category > a")
        assert len(cat) == 1
        assert cat[0].text.strip() == "Doujinshi"

        grp = soup.select("#Group > a")
        assert len(grp) == 1
        assert grp[0].text.strip() == "SeaFox"

        artist = soup.select("#Artist > a")
        assert len(artist) == 1
        assert artist[0].text.strip() == "Kirisaki Byakko"

        chars = [a.text.strip() for a in soup.select("#Character > a")]
        assert len(chars) == 3
        assert "Mario" in chars
        assert "Princess Peach" in chars
        assert "Super Crown Bowser | Bowsette" in chars

        parody = soup.select("#Parody > a")
        assert len(parody) == 1
        assert parody[0].text.strip() == "Super Mario Bros. / スーパーマリオブラザーズ"

        tags_expected = set("Femdom;Large Breasts;Nakadashi;Collar;Dragon Girl;Fangs;"
                            "Futa on Female;Futanari;Gender Bender;Hat;Leotard;Monster Girl;"
                            "Royalty".split(";"))
        tags = [a.text.strip() for a in soup.select("#Tag > a")]
        tags_nr = len(tags)
        tags = set(tags)
        assert len(tags) == tags_nr
        assert tags.symmetric_difference(tags_expected) == set()

        assert soup.select_one("#LastChange").text.strip() == "2018-10-24"
        assert not soup.select_one("#Note")
        assert soup.select_one("#btnFavoriteHandler").text.strip() == "Add to Favorites"
        assert soup.select_one("#btnDownloadEntry").text.strip() == "Download"

        # extinfo
        assert "Tsumino.com" in soup.select_one(".ext-info-title > a").text
        assert soup.select_one("#Uploader > a ").text.strip() == "Scarlet Spy"
        assert soup.select_one("#Uploaded").text.strip() == "2018-10-17"
        assert soup.select_one("#Rating").text.strip() == "4.23 (101 users / 1020 favs)"
        assert soup.select_one("#Censorship").text.strip() == "Censored"

        # check collections correct
        # set favorite and dled
        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        with db_con:
            db_con.execute("UPDATE Books SET favorite = 1, my_rating = 3.5 WHERE id = 3")
            db_con.execute("UPDATE ExternalInfo SET downloaded = 1 WHERE book_id = 3")

        resp = client.get(url_for("main.show_info", book_id=3), follow_redirects=True)
        assert (b"Dolls -Yoshino Izumi Hen- | Dolls -Yoshino "
                b"Izumi&#39;s Story- Ch. 2") in resp.data
        r_html = resp.data.decode("utf-8")
        soup = bs4.BeautifulSoup(r_html, "html.parser")
        assert soup.select_one("#btnFavoriteHandler").text.strip() == "Favorited"
        assert soup.select_one("#btnDownloadEntry").text.strip() == "Downloaded"
        assert soup.select_one("#Collection > a ").text.strip() == "Dolls"
        assert b"Collection: Dolls" in resp.data

        col_rows = soup.select("a.trow")
        cells = col_rows[0].select(".tcell")
        # book that is displayed correctly marked
        assert "book-collection-is-me" in col_rows[0]["class"]
        assert cells[0].text.strip() == ("Dolls -Yoshino Izumi Hen- | Dolls -Yoshino Izumi's"
                                         " Story- Ch. 2 / ドールズ -芳乃泉編- Ch. 2")
        assert cells[1].text.strip() == "3.5"
        assert cells[2].text.strip() == "25"

        cells = col_rows[1].select(".tcell")
        assert "book-collection-is-me" not in col_rows[1]["class"]
        assert cells[0].text.strip() == "Dolls Ch. 8 / ドールズ 第8話"
        assert cells[1].text.strip() == "Not rated"
        assert cells[2].text.strip() == "31"


def test_apply_upd_changes(app_setup):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)

    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                url_for("main.apply_upd_changes", book_id=7),
                data={
                    "_csrf_token": "token123",
                    "status": "Completed",
                    "language": "Klingon",
                    "pages": 27,
                    "tag": "Test;Test Tag;;;Masturbation;Fingering",
                    "list": "Added List;ListAdded;;;"
                    },
                follow_redirects=False)
        assert resp.status_code == 200

        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        db_con.row_factory = sqlite3.Row
        tags = db_con.execute("""SELECT id, group_concat(name, ';')
                             FROM (
                                     SELECT b.id, l.name
                                     FROM Books b, Tag l, BookTag bl
                                     WHERE bl.book_id = b.id
                                     AND bl.tag_id = l.id
                                     AND b.id = 7
                                     ORDER BY l.name
                                  )
                             GROUP BY id
                             """).fetchone()
        assert tags[1] == "Gender Bender;Possession;Solo Action;Test;Test Tag"

        lists = db_con.execute("""SELECT id, group_concat(name, ';')
                             FROM (
                                     SELECT b.id, l.name
                                     FROM Books b, List l, BookList bl
                                     WHERE bl.book_id = b.id
                                     AND bl.list_id = l.id
                                     AND b.id = 7
                                     ORDER BY l.name
                                  )
                             GROUP BY id
                             """).fetchone()
        assert lists[1] == "Added List;ListAdded"
        book_row = db_con.execute("SELECT * FROM Books WHERE id = 7").fetchone()
        assert book_row["status_id"] == 3
        assert book_row["language_id"] == 2
        assert book_row["pages"] == 27


def test_edit_book(app_setup):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)

    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        data = {
                "_csrf_token": "token123",
                "title_eng": "Test Title !$I=§",
                "title_foreign": "とれて♥甘痴",
                "language_id": 1,
                "my_rating": 4.5,
                "status_id": 2,
                "pages": 27,
                "category": ["Doujinshi", "Manga", "Newcat"],
                "collection": ["Testcol"],
                "groups": ["Testgrp1", "Testgrp2"],
                "artist": ["Tanabe Kyou"],
                "parody": [],
                "character": ["Testchar1", "Test char2"],
                "note": "Testnote 123\n235423",
                "tag": ["Anal", "Nakadashi", "Blowjob", "X-ray", "Ahegao", "Huge Penis",
                        "Incest", "Loli", "Maledom", "Niece", "Slut", "Stockings"],
                "list": ["to-read", "test"]
                }
        resp = client.post(
                url_for("main.edit_book", book_id=9),
                data=data,
                follow_redirects=False)
        assert resp.status_code == 302
        assert resp.location == url_for("main.show_info", book_id=9)

        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        db_con.row_factory = sqlite3.Row
        brow = all_book_info(db_con, book_id=9)
        for col in ("title_eng", "title_foreign", "my_rating", "status_id", "pages", "note"):
            assert brow[col] == data[col]
        assert sorted(brow["tags"].split(";")) == sorted(data["tag"])
        assert sorted(brow["artists"].split(";")) == sorted(data["artist"])
        assert sorted(brow["categories"].split(";")) == sorted(data["category"])
        assert sorted(brow["characters"].split(";")) == sorted(data["character"])
        assert sorted(brow["collections"].split(";")) == sorted(data["collection"])
        assert sorted(brow["groups"].split(";")) == sorted(data["groups"])
        assert sorted(brow["lists"].split(";")) == sorted(data["list"])
        assert brow["parodies"] is None

