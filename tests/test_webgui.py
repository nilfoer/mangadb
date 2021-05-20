import os
import shutil
import json
import datetime
import bs4
import sqlite3
import pytest
import re
from io import BytesIO

from PIL import Image
from flask import url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from manga_db.webGUI import create_app
from manga_db.ext_info import ExternalInfo
from manga_db.webGUI.mdb import t_local
from manga_db.webGUI.json_custom import to_serializable
from manga_db.constants import LANG_IDS
from utils import all_book_info, gen_hash_from_file, load_db_from_sql_file

TESTS_DIR = os.path.dirname(os.path.realpath(__file__))


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

    sql_file = os.path.join(TESTS_DIR, "all_test_files", "manga_db.sqlite.sql")
    mdb_file = os.path.join(tmpdir, "manga_db.sqlite")
    con = load_db_from_sql_file(sql_file, mdb_file)
    con.close()

    # setup flask app for testing
    app = create_app(
            test_config={"TESTING": True, "DEBUG": False, "SERVER_NAME": "test.test"},
            instance_path=tmpdir
            )
    client = app.test_client()

    yield tmpdir, app, client

    # clean up thread local so we avoid a re-used thread using an old mdb connection
    # from the thread local    
    t_local.mdb_init = False
    t_local.mdb = None


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

    with client.session_transaction() as sess:
        token_before = sess["_csrf_token"]
    app.config["USERNAME"] = "test"
    app.config["PASSWORD"] = generate_password_hash("testpw")
    resp = login(app, client, "test", "testpw")
    assert b'id="searchResult"' in resp.data
    # csrf token is session-based make sure it changes on login
    with client.session_transaction() as sess:
        assert sess["_csrf_token"] != token_before
        token_before = sess["_csrf_token"]

    with app.app_context():
        resp = client.get(url_for("auth.logout"), follow_redirects=True)
    assert b"Login" in resp.data
    # csrf token is session-based make sure it changes on logout
    with client.session_transaction() as sess:
        assert sess["_csrf_token"] != token_before
        assert "authenticated" not in sess

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

        # test that we re-set the csrf token -> session cookie changed
        resp = client.get("/", follow_redirects=True)

        import base64, binascii

        def decode_sess(s):
            se = s.split(".", 1)[0]
            n = 0
            while n < 4:
                try:
                    decoded = base64.urlsafe_b64decode(se)
                except binascii.Error:
                    # add padding
                    se += "="
                else:
                    return decoded
                n += 1
            return None

        # To create a cookie, the Set-Cookie header is sent from a server in
        # response to requests.
        # In the Set-Cookie header, a cookie is defined by a name associated
        # with a value. A web server can configure the domain and path
        # directives to restrain the scope of cookies. While session cookies
        # are deleted when a browser shuts down, the permanent cookies expire
        # at the time defined by Expires or Max-Age.
        # Among the directives, the Secure and HttpOnly attributes are
        # particularly relevant to the security of cookies:
        # Setting Secure directive forbids a cookie to be transmitted via simple HTTP.
        # Setting the HttpOnly directive prevents access to cookie value through javascript.
        # there can be multiple set-cookie headers
        set_cookies = resp.headers.getlist("Set-Cookie")
        # filter for set session cookie
        set_cookie_sess = [h for h in set_cookies if "session=" in h][0]
        start, end = set_cookie_sess.index("=") + 1, set_cookie_sess.index(";")
        sess_cstr = set_cookie_sess[start:end]
        sess_dict = json.loads(decode_sess(sess_cstr))
        # _csrf_token present but unchanged
        assert sess_dict["_csrf_token"] == "token123"
        # test that we're useing httponly sess cookie while were at it
        assert "; HttpOnly;" in set_cookie_sess


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
        # chapter status not displayed if not set!
        assert not soup.select_one("#ChapterStatus")
        assert soup.select_one("#ReadingStatus").text.strip() == "Not Read"
        assert soup.select_one("#Status").text.strip() == "Unknown"

        lang = soup.select("#Language > a")
        assert len(lang) == 1
        assert lang[0].text.strip() == "English"

        cat = soup.select("#Category > a")
        assert len(cat) == 1
        assert cat[0].text.strip() == "Doujinshi"

        grp = soup.select("#Group > .tags > a")
        assert len(grp) == 1
        assert grp[0].text.strip() == "SeaFox"

        artist = soup.select("#Artist > .tags > a")
        assert len(artist) == 1
        assert artist[0].text.strip() == "Kirisaki Byakko"

        chars = [a.text.strip() for a in soup.select("#Character > .tags > a")]
        assert len(chars) == 3
        assert "Mario" in chars
        assert "Princess Peach" in chars
        assert "Super Crown Bowser | Bowsette" in chars

        parody = soup.select("#Parody > .tags > a")
        assert len(parody) == 1
        assert parody[0].text.strip() == "Super Mario Bros. / スーパーマリオブラザーズ"

        tags_expected = set("Femdom;Large Breasts;Nakadashi;Collar;Dragon Girl;Fangs;"
                            "Futa on Female;Futanari;Gender Bender;Hat;Leotard;Monster Girl;"
                            "Royalty".split(";"))
        tags = [a.text.strip() for a in soup.select("#Tag > .tags > a")]
        tags_nr = len(tags)
        tags = set(tags)
        assert len(tags) == tags_nr
        assert tags.symmetric_difference(tags_expected) == set()

        assert soup.select_one("#LastChange").text.strip() == "2018-10-24"
        assert not soup.select_one("#Note")
        assert soup.select_one("#btnFav").text.strip() == "Add to Favorites"
        assert soup.select_one("#Downloaded > .fa-times")

        # extinfo
        assert "Tsumino.com" in soup.select_one(".ext-info-title > a").text
        assert soup.select_one("#Uploader").text.strip() == "Scarlet Spy"
        assert soup.select_one("#Uploaded").text.strip() == "2018-10-17"
        assert soup.select_one("#Rating").text.strip() == "4.23 (101 users / 1020 favs)"
        assert soup.select_one("#Censorship").text.strip() == "Censored"

        # check collections correct
        # set favorite and dled
        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        with db_con:
            db_con.execute("UPDATE Books SET favorite = 1, my_rating = 3.5, "
                           "chapter_status = 'Whatever' WHERE id = 3")
            db_con.execute("UPDATE ExternalInfo SET downloaded = 1 WHERE book_id = 3")

        resp = client.get(url_for("main.show_info", book_id=3), follow_redirects=True)
        assert (b"Dolls -Yoshino Izumi Hen- | Dolls -Yoshino "
                b"Izumi&#39;s Story- Ch. 2") in resp.data
        r_html = resp.data.decode("utf-8")
        soup = bs4.BeautifulSoup(r_html, "html.parser")
        assert soup.select_one("#ChapterStatus").text.strip() == "Whatever"
        assert soup.select_one("#ReadingStatus").text.strip() == "Page 23"
        assert soup.select_one("#btnFav").text.strip() == "Favorite"
        assert soup.select_one("#Downloaded > .fa-check")
        assert soup.select_one("#Collection > .tags > a ").text.strip() == "Dolls"

        assert b"COLLECTION: </span>Dolls" in resp.data

        # save since only one collection otherwise have to add more detail to selector
        coll_items = soup.select(".books-collection-grid .book-grid-item")
        # book that is displayed correctly marked
        assert "current" in coll_items[0]["class"]
        assert coll_items[0].select_one(".overlay-title").text.strip() == (
                "Dolls -Yoshino Izumi Hen- | Dolls -Yoshino Izumi's"
                " Story- Ch. 2 / ドールズ -芳乃泉編- Ch. 2")
        assert len(coll_items[0].select_one(".overlay-rate").select(".fa.fa-star")) == 4
        assert "avg external rating" not in str(coll_items[0].select_one(".overlay-rate"))
        assert coll_items[0].select_one(".overlay-pages").text.strip() == "25 pages"

        assert "current" not in coll_items[1].parent["class"]
        assert coll_items[1].select_one(".overlay-title").text.strip() == (
                "Dolls Ch. 8 / ドールズ 第8話")
        assert len(coll_items[1].select_one(".overlay-rate").select(".fa.fa-star")) == 4
        # str of dom tag obj in bs4 returns html repr
        assert "avg external rating" not in str(coll_items[1].select_one(".overlay-rate"))
        assert coll_items[1].select_one(".overlay-pages").text.strip() == "31 pages"


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
        assert resp.location == url_for("main.show_info", book_id=7)

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
        # one after default langs
        assert book_row["language_id"] == (len(LANG_IDS) / 2 + 1)
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
                "list": ["to-read", "test"],
                "nsfw": 1,
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
        for col in ("title_eng", "title_foreign", "my_rating", "status_id", "pages", "note",
                    "nsfw"):
            assert brow[col] == data[col]
        assert sorted(brow["tags"].split(";")) == sorted(data["tag"])
        assert sorted(brow["artists"].split(";")) == sorted(data["artist"])
        assert sorted(brow["categories"].split(";")) == sorted(data["category"])
        assert sorted(brow["characters"].split(";")) == sorted(data["character"])
        assert sorted(brow["collections"].split(";")) == sorted(data["collection"])
        assert sorted(brow["groups"].split(";")) == sorted(data["groups"])
        assert sorted(brow["lists"].split(";")) == sorted(data["list"])
        assert brow["parodies"] is None


def upload_file(app, client, bid, tfile):
    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        # content_type='multipart/form-data' to the post method it -> expects all values
        # in data to either be files or strings
        resp = client.post(
                    url_for("main.upload_cover", book_id=bid),
                    data={"file": tfile},
                    headers={
                        'Content-Type': 'multipart/form-data',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': "token123"
                        },
                    content_type='multipart/form-data')
        return resp


def test_upload_cover(app_setup):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)

    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.upload_cover", book_id=10),
                    data={},
                    headers={
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': "token123"
                        })
        assert resp.json == jsonify({"error": "No file data received!"}).json

        # cant simulate user not selecting file as in file being of size 0 or filename
        # being false -> without filename file ends up in form data and not in req.files
        # tfile = (BytesIO(b't'), "")
        # resp = upload_file(app, client, tfile)
        # assert resp.json == jsonify({"error": "No file selected!"}).json

        # needs to be working img since we do processing with pil
        # create image with pil (over max thumb size in color red)
        img = Image.new('RGB', (500, 930), color='red')
        # save pil image in BytesIO obj
        img_bio = BytesIO()
        img.save(img_bio, format='PNG')
        # reset pointer
        img_bio.seek(0)
        tfile = (img_bio, "test.png")
        resp = upload_file(app, client, 10, tfile)
        # _0 is automatically appended
        assert resp.json == jsonify({"cover_path": "/thumbs/temp_cover"}).json
        cover_img = Image.open(os.path.join(tmpdir, "thumbs", "temp_cover_0"))
        assert cover_img.size <= (400, 600)
        cover_img.close()

        # upload for book without id
        img = Image.new('RGB', (300, 530), color='red')
        # save pil image in BytesIO obj
        img_bio = BytesIO()
        img.save(img_bio, format='PNG')
        # reset pointer
        img_bio.seek(0)
        tfile = (img_bio, "test.png")
        resp = upload_file(app, client, 0, tfile)
        r_dic = resp.get_json()
        cover_img = Image.open(os.path.join(tmpdir, "thumbs",
                                            r_dic["cover_path"].rsplit("/", 1)[-1] + "_0"))
        assert cover_img.size <= (400, 600)
        cover_img.close()

        # using same temp name -> del old one first
        os.remove(os.path.join(tmpdir, "thumbs", "temp_cover_0"))

        img = Image.new('RGB', (300, 530), color='red')
        # save pil image in BytesIO obj
        img_bio = BytesIO()
        img.save(img_bio, format='PNG')
        # reset pointer
        img_bio.seek(0)
        tfile = (img_bio, "test.png")
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.upload_cover", book_id=0),
                    data={"file": tfile},
                    headers={
                        'Content-Type': 'multipart/form-data',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': "token123"
                        },
                    content_type='multipart/form-data')
        r_dic2 = resp.get_json()
        assert os.path.isfile(os.path.join(tmpdir, "thumbs",
                                           r_dic2["cover_path"].rsplit("/", 1)[-1] + "_0"))
        # since we overwrite anyway we don't need to check for deletion


tsu_extr_data = {
        'title_eng': 'Sono Shiroki Utsuwa ni Odei o Sosogu', 'title_foreign': 'その白き器に汚泥を注ぐ',
        'uploader': 'MrOverlord12', 'upload_date': datetime.date(2018, 10, 13), 'pages': 20,
        'rating': 4.13, 'ratings': 39, 'favorites': 420, 'category': ['Manga'],
        'collection': None, 'groups': None, 'artist': ['Taniguchi-san'], 'parody': None,
        'character': None,
        'tag': ['Ahegao', 'Body Swap', 'Bondage', 'Dark Skin', 'Defloration', 'Elf', 'Filming',
                'Futa on Female', 'Futanari', 'Gender Bender', 'Large Breasts', 'Nakadashi'],
        'censor_id': 2,
        'url': 'https://www.tsumino.com/entry/43460',
        'id_onpage': '43460', 'language': 'English', 'status_id': 1, 'imported_from': 1,
        'nsfw': 1, 'note': None,
        }


def test_import_book(app_setup, monkeypatch):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)
    tests_files_dir = os.path.join(TESTS_DIR, "webgui_test_files")

    url = "https://www.tsumino.com/entry/43492"
    fn = "tsumino_43492_mirai-tantei-nankin-jiken"
    with open(os.path.join(tests_files_dir, fn + ".html"), "r", encoding="UTF-8") as f:
        html = f.read()
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: None)
    cover_url = os.path.join(tests_files_dir, fn).replace("\\", r"/")
    cover_url = f"file:///{cover_url}"
    # patch get_cover to point to thumb on disk
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover", lambda x: cover_url)

    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.import_book"),
                    data={"ext_url": url, "_csrf_token": "token123"},
                    follow_redirects=True)
        assert b"Failed getting book" in resp.data

    # have to change get_html to retrieve file from disk instead
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: html)
    kwargs_show_add = {}
    # import book shows show_add_book with a temp fn for dled cover and extr data json embedded
    # patch show add book to give us the argmuents

    def store_kwargs(**kwargs):
        kwargs_show_add.update(kwargs)
        return ""
    monkeypatch.setattr("manga_db.webGUI.webGUI.show_add_book", store_kwargs)
    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.import_book"),
                    data={"ext_url": url, "_csrf_token": "token123"},
                    follow_redirects=True)

        # cover temp written correctly
        assert (gen_hash_from_file(os.path.join(tmpdir, "thumbs", "temp_cover_0"),
                                   "sha512") ==
                "6c77019c5a84f00486b35a496b4221eb30dfb8a5d37d006c298d01562291ca0138e2ef72e"
                "27f076be80593fb1ff27f09a5a557c55c8a98e80f88d91ceff8b533")

        row_expected = (
            'Future Detective: The House Confinement Incident | Mirai Tantei Nankin Jiken',
            '未来探偵軟禁事件', 1, 31, 1, None, None,
            datetime.date.today(), 0, ('Femdom;Handjob;Large Breasts;Nakadashi;Straight Shota;'
            'Blowjob;Big Ass;Happy Sex;Impregnation;Incest;Stockings;Huge Breasts;'
            'Tall Girl;BBW;Hotpants;Inseki;Onahole;Plump;Smug;Comedy;Imouto;Sex Toys'),
            'Kakuzatou', 'Doujinshi',
            None, None, 'Kakuzato-ichi', None, None, '43492', 1, datetime.date(2018, 10, 13),
            'Scarlet Spy', 2, 4.49, 324, 3430, 0, datetime.date.today(), 0
            )
        # compare book
        b = kwargs_show_add["book"]
        assert b.title_eng == row_expected[0]
        assert b.title_foreign == row_expected[1]
        assert b.language_id == LANG_IDS['English']
        assert b.pages == row_expected[3]
        assert b.status_id == row_expected[4]
        assert b.my_rating == row_expected[5]
        assert b.note == row_expected[6]
        assert b.last_change == row_expected[7]
        assert b.favorite is None
        assert sorted(b.tag) == sorted(row_expected[9].split(";"))
        assert b.artist == [row_expected[10]]
        assert b.category == [row_expected[11]]
        assert b.character == []
        assert b.collection == []
        assert b.groups == [row_expected[14]]
        assert b.list == []
        assert b.parody == ['Original']

        # check ext info from json since its rebuilt from that
        ei = json.loads(kwargs_show_add["extr_data"])
        print(kwargs_show_add["extr_data"])
        print(ei, type(ei))
        # assert ei["url"] == row_expected[17]
        assert ei["id_onpage"] == row_expected[17]
        assert ei["imported_from"] == row_expected[18]
        assert ei["upload_date"] == str(row_expected[19])
        assert ei["uploader"] == row_expected[20]
        assert ei["censor_id"] == row_expected[21]
        assert ei["rating"] == row_expected[22]
        assert ei["ratings"] == row_expected[23]
        assert ei["favorites"] == row_expected[24]

        # book alrdy in DB -> add extinfo
        url = "https://www.tsumino.com/entry/43460"
        fn = "tsumino_43460_sono-shiroki-utsuwa.html"
        with open(os.path.join(tests_files_dir, fn), "r", encoding="UTF-8") as f:
            html = f.read()
        monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: html)
        monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover", lambda x: cover_url)
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        # import same book again
        resp = client.post(
                    url_for("main.import_book"),
                    data={"ext_url": url, "_csrf_token": "token123"},
                    follow_redirects=True)
        r_html = resp.data.decode("utf-8")
        # check for add external or new book prompt
        assert "Title of book to import matches with the title of this book!" in r_html

        # make the acutal call to import as external info
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.import_book"),
                    data={"ext_url": url, "_csrf_token": "token123",
                          "extr_data_json": json.dumps(tsu_extr_data, default=to_serializable),
                          "thumb_url": cover_url, "action": "add_ext"},
                    follow_redirects=True)
        r_html = resp.data.decode("utf-8")
        assert f"Added external link at &#39;{url}" in r_html
        # show outdated msg
        assert "External links from same site and with matching IDs found" in r_html
        assert f"( {url} )" in r_html

        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)

        # @Hack url select replaced with 0
        ei_rows = db_con.execute("SELECT book_id, 0, id_onpage, imported_from, upload_date, "
                                 "uploader, censor_id, rating, ratings, favorites, downloaded, "
                                 "last_update, outdated "
                                 "FROM ExternalInfo WHERE book_id = 11").fetchall()
        assert len(ei_rows) == 2
        assert ei_rows[0][:-2] == ei_rows[1][:-2]
        assert ei_rows[1][11] == datetime.date.today()
        # old ei outdated
        assert ei_rows[0][12] == 1
        # no cover written
        assert not os.path.isfile(os.path.join(tmpdir, "thumbs", "11"))


def test_add_book(app_setup):
    extr_json = """{"title_eng": "Mirai Tantei Nankin Jiken", "title_foreign":
    "\\u672a\\u6765\\u63a2\\u5075\\u8edf\\u7981\\u4e8b\\u4ef6", "uploader": "Scarlet Spy",
    "upload_date": "2018-10-13", "pages": 31, "rating": 4.46, "ratings": 175, "favorites": 1703,
    "my_rating": null, "category": ["Doujinshi"], "collection": ["Testcol"],
    "groups": ["Kakuzato-ichi"], "artist": ["Kakuzatou"], "parody": ["Testpar1", "Testpar2"],
    "character": ["Char1", "Char 2"], "tag": ["BBW", "Big Ass", "Blowjob", "Elder Sister",
    "Femdom", "Handjob", "Happy Sex", "Hotpants", "Huge Breasts", "Impregnation", "Incest",
    "Inseki", "Large Breasts", "Nakadashi", "Onahole", "Plump", "Smug", "Stockings",
    "Straight Shota", "Tall Girl"], "censor_id": 2, "url":
    "http://www.tsumino.com/Book/Info/43492/mirai-tantei-nankin-jiken", "id_onpage": "43492",
    "language": "English", "status_id": 1, "imported_from": 1, "nsfw": 0}"""
    extr_data = json.loads(extr_json)
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)

    tmpcov_path = os.path.join(tmpdir, "thumbs", "temp_cover_0")
    data = {k: v for k, v in extr_data.items() if k not in ExternalInfo.COLUMNS and
            v is not None}
    data.update({
        "extr_data_json": extr_json,
        "cover_uploaded": True,
        "_csrf_token": "token123",
        "read_status": "",
        "language_id": 1,
        "my_rating": 3.4,
        "note": "test",
        "list": ["to-read", "test"],
        })
    with open(tmpcov_path, "w") as f:
        f.write("Testcover temp file")
    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.add_book"),
                    data=data,
                    follow_redirects=True)
        assert b"Mirai Tantei Nankin Jiken" in resp.data
        assert not os.path.isfile(tmpcov_path)
        assert os.path.isfile(os.path.join(tmpdir, "thumbs", "18_0"))

        row_expected = ('Mirai Tantei Nankin Jiken', '未来探偵軟禁事件', 1, 31, 1, 3.4,
                        #                                      chapter, read_status, nsfw
                        "test", datetime.date.today(), 0, 0.0, None, None, 0, 'Kakuzatou',
                        'Doujinshi', "Char1;Char 2", "Testcol", 'Kakuzato-ichi', "to-read;test",
                        "Testpar1;Testpar2",
                        # 'http://www.tsumino.com/Book/Info/43492/mirai-tantei-nankin-jiken',
                        '43492', 1, datetime.date(2018, 10, 13), 'Scarlet Spy', 2, 4.46, 175,
                        1703, 0, datetime.date.today(), 0)

        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        row = all_book_info(db_con, 18, include_id=False)
        # assoc col values arent ordered, if one of the above fails and its assoc col
        # also compare them sorted
        assert tuple((c for c in row if not (type(c) == str and "Femdom" in c))) == row_expected
        tags_expected = sorted('Femdom;Handjob;Large Breasts;Nakadashi;Straight Shota;Blowjob;Big Ass;Happy Sex;Impregnation;Incest;Stockings;Huge Breasts;Elder Sister;Tall Girl;BBW;Hotpants;Inseki;Onahole;Plump;Smug'.split(";"))
        assert sorted(row['tags'].split(";")) == tags_expected

    # cancel add book
    tmpcov_path = os.path.join(tmpdir, "thumbs", "temp_cover_0")
    with open(tmpcov_path, "w") as f:
        f.write("Testcover temp file to delete")
    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        client.post(
                url_for("main.cancel_add_book"),
                data="1",
                headers={
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': "token123"
                    },
                follow_redirects=True)
    assert not os.path.isfile(tmpcov_path)


def test_add_ext_info(app_setup, monkeypatch):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)
    tests_files_dir = os.path.join(TESTS_DIR, "webgui_test_files")
    url = "https://www.tsumino.com/entry/43516"
    fn = "tsumino_43516_martina-onee-chan-no-seikatsu.html"
    with open(os.path.join(tests_files_dir, fn), "r", encoding="UTF-8") as f:
        html = f.read()
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: None)
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover", lambda x: "x")
    # for title missmatch test: book we're comparing against does not have an id yet!
    monkeypatch.setattr("manga_db.manga.Book.title", property(lambda x: "Title Missmatch" if x.id else ""))

    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.add_ext_info", book_id=6),
                    data={"_csrf_token": "token123"},
                    follow_redirects=True)
        # switch to add ext_info page
        assert b"Adding external info to:" in resp.data

        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.add_ext_info", book_id=6),
                    data={"url": url, "_csrf_token": "token123"},
                    follow_redirects=True)
        assert b"Adding external link failed!" in resp.data
        assert f"URL was: {url}".encode("utf-8") in resp.data

        # have to change get_html to retrieve file from disk instead
        monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html",
                            lambda x: html)
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.add_ext_info", book_id=6),
                    data={"url": url, "_csrf_token": "token123"},
                    follow_redirects=True)
        # title missmatch warning
        assert b"Title of external link and book&#39;s title doesn&#39;t match!" in resp.data
        # outdated warning
        assert b"External links from same site and with matching IDs found!" in resp.data
        assert f"( {url} )".encode("utf-8") in resp.data
        assert b"External link was added as id 19" in resp.data
        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        # @Hack url select replaced with 0
        ei_rows = db_con.execute("""SELECT 0, id_onpage, imported_from, upload_date,
                                           uploader, censor_id, rating, ratings, favorites,
                                           downloaded, last_update, outdated
                                    FROM ExternalInfo WHERE book_id = 6""").fetchall()
        assert len(ei_rows) == 2
        assert ei_rows[0][:-3] == ei_rows[1][:-3]
        assert ei_rows[1][9] == 0
        assert ei_rows[1][-2] == datetime.date.today()
        # old ei outdated
        assert ei_rows[0][-1] == 1


def test_update_book_ext_info(app_setup, monkeypatch):
    tmpdir, app, client = app_setup
    setup_authenticated_sess(app, client)
    tests_files_dir = os.path.join(TESTS_DIR, "webgui_test_files")
    fn = "tsumino_43516_martina-onee-chan-no-seikatsu_updated.html"
    with open(os.path.join(tests_files_dir, fn), "r", encoding="UTF-8") as f:
        html = f.read()
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: None)
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover", lambda x: "x")

    with app.app_context():
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.update_book_ext_info", book_id=6, ext_info_id=6),
                    data={"_csrf_token": "token123"},
                    follow_redirects=True)
        assert b"Updating failed!" in resp.data
        assert (b"Either there was something wrong with the url or the extraction failed"
                in resp.data)

        # have to change get_html to retrieve file from disk instead
        monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html",
                            lambda x: html)
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.update_book_ext_info", book_id=6, ext_info_id=6),
                    data={"_csrf_token": "token123"},
                    follow_redirects=True)
        # canceled updated due to wrong title
        assert b"Update failed!" in resp.data
        assert b"Title of book at URL didn&#39;t match title" in resp.data

        db_con = sqlite3.connect(os.path.join(tmpdir, "manga_db.sqlite"),
                                 detect_types=sqlite3.PARSE_DECLTYPES)
        # set to downloaded so it gets reset when we get re-dl warning
        with db_con:
            db_con.execute("UPDATE ExternalInfo SET downloaded = 1 WHERE id = 6")
        # @Hack url select replaced with 0
        ei_row_before = db_con.execute("""SELECT 0, id_onpage, imported_from,
                                          outdated, downloaded
                                        FROM ExternalInfo WHERE book_id = 6""").fetchone()
        assert ei_row_before[4] == 1
        # change wrong title back
        html = html.replace("TITLE MISSMATCH ", "")
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "token123"
        resp = client.post(
                    url_for("main.update_book_ext_info", book_id=6, ext_info_id=6),
                    data={"_csrf_token": "token123"},
                    follow_redirects=True)
        assert b"External link was updated!" in resp.data

        # test that update changes are shown correctly
        assert b"Differences from Book at external link" in resp.data
        r_html = resp.data.decode("utf-8")

        expected = (
                # "uploader": "censor_id": "upload_date": "rating": "ratings": "favorites":
                "Scarlet Spy2", 3, datetime.date(2018, 10, 20), 4.4, 100, 1150,
                # last_update
                datetime.date.today()
                )
        # book_changed = {
        #         "pages": 29,
        #         "artist": ["Added Artist", "Korotsuke"],
        #         # tag removed: Exhibitionism, Ponytail
        #         # tag added also Decensored which will be filtered and
        #         # updates ext info censorhsip
        #         "tag": ["Ahegao", "Happy Sex", "Impregnation", "Large Breasts", "Decensored",
        #                 "Nakadashi", "School Uniform", "Sweating", "Added Tag"],
        #         "collection": ["Big Sis Martina's"]
        #         }
        assert re.search(r'input name="pages" .*\r?\n?.* value="29"', r_html)
        added_removed = (
                ({"Decensored", "Added Tag"}, {"Exhibitionism", "Ponytail"}),
                "Added Artist;;;",
                "Big Sis Martina&#39;s;;;"
                )
        soup = bs4.BeautifulSoup(r_html, "html.parser")
        for ar in added_removed:
            # if there are multiple values they can change order
            if type(ar) == tuple:
                input_tag = soup.select_one("input[name=\"tag\"]").attrs["value"]
                added, removed = input_tag.split(";;;")
                added = set(added.split(";"))
                removed = set(removed.split(";"))
                assert ar[0] == added and ar[1] == removed
            else:
                assert ar in r_html
        # re-dl warning displayed
        assert "WARNING" in r_html
        assert "Please re-download" in r_html
        # @Hack url select replaced with 0
        ei_rows = db_con.execute("""SELECT 0, id_onpage, imported_from, outdated,
                                           downloaded, uploader, censor_id, upload_date,
                                           rating, ratings, favorites, last_update
                                    FROM ExternalInfo WHERE book_id = 6""").fetchall()
        r = ei_rows[0]
        assert len(ei_rows) == 1
        assert ei_row_before[:-1] == r[:4]
        # downloaded reset
        assert r[4] == 0
        assert r[5:] == expected
