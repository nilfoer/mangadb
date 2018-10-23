"""
File: webGUI.py
Description: Creates webGUI for manga_db using flask
"""

import os.path
import json
import secrets
from flask import (
        Flask, request, redirect, url_for,
        render_template, flash, send_from_directory,
        jsonify, send_file, abort, session, Markup,
)

from .auth import auth_bp, load_admin_credentials
from .json import to_serializable
from ..constants import STATUS_IDS
from ..manga_db import MangaDB
from ..manga import Book
from ..ext_info import ExternalInfo
from .. import extractor

LOCAL_DOWNLOAD = "N:\\_archive\\test\\tsu\\to-read\\"
BOOKS_PER_PAGE = 60


# config logging b4 this line vv
app = Flask(__name__)  # create the application instance :)

# Load default config and override config from an environment variable
app.config.update(
    dict(
        # DATABASE=os.path.join(app.root_path, 'flaskr.db'),
        # unsafe key for dev purposes otherwise use tru random bytes like:
        # python -c "import os; print(os.urandom(24))"
        SECRET_KEY='mangadb dev'))

# register blueprint has to come after routes were added to it
app.register_blueprint(auth_bp)

# blueprint = Blueprint('thumbs', __name__, static_url_path='/thumbs', static_folder='/thumbs')
# app.register_blueprint(blueprint)

mdb = MangaDB(".", "manga_db.sqlite")

# path to thumbs folder
app.config['THUMBS_FOLDER'] = os.path.join(mdb.root_dir, "thumbs")
# thumb extensions
ALLOWED_THUMB_EXTENSIONS = set(('png', 'jpg', 'jpeg', 'gif'))
# limit upload size to 0,5MB
app.config['MAX_CONTENT_LENGTH'] = 0.5 * 1024 * 1024

# create route for thumbs/static data that isnt in static, can be used in template with
# /thumbs/path/filename or with url_for(thumb_static, filename='filename')
# Custom static data
@app.route('/thumbs/<path:filename>')
def thumb_static(filename):
    return send_from_directory(app.config['THUMBS_FOLDER'], filename)


@app.before_request
def validate_csrf_token():
    # decorator @app.before_request to execute this b4 every req
    # TODO add lifetime
    if request.method == "POST":
        # pop from session so its only lasts one req
        token = session.pop("_csrf_token", None)
        if not token:
            app.logger.error("Session is missing CSRF token!")
            abort(403)

        # is_xhr -> ajax request
        if request.is_xhr:
            # configured jquery ajax to send token as X-CSRFToken header
            if token != request.headers.get("X-CSRFToken", None):
                app.logger.error("AJAX request CSRF token is invalid!")
                abort(403)
        elif token != request.form.get("_csrf_token", None):
            app.logger.error("Request CSRF token is invalid!")
            abort(403)


@app.after_request
def new_csrf_token(response):
    # since we dont refresh the page when using ajax we have to send
    # js the new csfr token
    if request.is_xhr:
        response.headers["X-CSRFToken"] = generate_csrf_token()
    return response


# partly taken from http://flask.pocoo.org/snippets/3/
def generate_csrf_token():
    if '_csrf_token' not in session:
        # As of 2015, it is believed that 32 bytes (256 bits) of randomness is sufficient for the
        # typical use-case expected for the secrets module
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


def generate_csrf_token_field():
    token = generate_csrf_token()
    return Markup(f"<input type='hidden' name='_csrf_token' value='{token}' />")


# register func to gen token field so we can us it in template
app.jinja_env.globals['csrf_token_field'] = generate_csrf_token_field
app.jinja_env.globals['csrf_token'] = generate_csrf_token


# check login on all pages but those that are marked is_public (by public_route decorator)
# src: https://stackoverflow.com/a/52572337
# Kristof Gilicze
@app.before_request
def check_route_access():
    if request.endpoint is None:  # can be None so check it first
        return
    if any([
            request.endpoint.startswith('static'),
            request.endpoint.startswith("thumb_static"),
            # auth/logout endpoint is auth.logout
            request.endpoint.startswith("auth."),  # allow access to auth pages by default
            "authenticated" in session,  # user is logged in
            # allow access to is_public marked functions
            getattr(app.view_functions[request.endpoint], 'is_public', False)]):
        return  # Access granted
    else:
        return redirect(url_for('auth.login'))


def public_route(decorated_function):
    decorated_function.is_public = True
    return decorated_function


@app.route('/', methods=["GET"])
def show_entries():
    order_by_col = request.args.get('order_by_col', "id", type=str)
    asc_desc = "ASC" if request.args.get('asc_desc', "DESC", type=str) == "ASC" else "DESC"
    order_by = f"Books.{order_by_col} {asc_desc}"
    after = request.args.get("after", None, type=int)
    before = request.args.get("before", None, type=int)
    books = mdb.get_x_books(BOOKS_PER_PAGE+1, after=after, before=before,
                            order_by=order_by)
    first_id, last_id, more = first_last_more(books, after, before)

    return render_template(
        'show_entries.html',
        books=books,
        more=more,
        first_id=first_id,
        last_id=last_id,
        order_col_libox=order_by_col,
        asc_desc=asc_desc)


@app.route('/book/<int:book_id>')
def show_info(book_id, book=None, **kwargs):
    # enable passing book obj over optional param while keeping url route option
    # with required param
    if book is None:
        book = mdb.get_book(book_id)
    if book is None:
        return render_template(
            'show_info.html',
            error_msg=f"No book with id {book_id} was found in DB!")

    collections = None
    if book.collection:
        collections = []
        for collection in book.collection:
            books_in_collection = mdb.get_collection_info(collection)
            collections.append((collection, books_in_collection))

    book_upd_changes = kwargs.pop("book_upd_changes", None)
    show_outdated = kwargs.pop("show_outdated", None)
    outdated = None
    if show_outdated:
        try:
            ei = [ei for ei in book.ext_infos if ei.id == show_outdated][0]
        except IndexError:
            app.logger.error("Cant show outdated id %d not found in books ext_infos",
                             show_outdated)
        else:
            outdated = ei.get_outdated_links_same_pageid()

    return render_template(
        'show_info.html',
        book=book,
        collections=collections,
        # rather than spend a lot of time/code to replace title_eng and _foreign with title in
        # rows make title func available to jinja by passing it in as param
        build_title=Book.build_title,
        lists=[row["name"] for row in book.get_all_options_for_assoc_column("list")],
        book_upd_changes=book_upd_changes,
        outdated=outdated)


@app.route('/import', methods=["POST"])
def import_book(url=None):
    if url is None:
        url = request.form['ext_url']
    extr_data, thumb_url = mdb.retrieve_book_data(url)
    if extr_data is None:
        flash("Failed getting book!", "warning")
        flash("Either there was something wrong with the url or the extraction failed!", "info")
        flash(f"URL was: {url}")
        flash("Check the logs for more details!", "info")
        return redirect(url_for("show_entries"))
    book = Book(mdb, **extr_data)
    # convert data to json so we can rebuilt ext_info when we add it to DB
    # as we have to take all data from edit_info page or store a json serialized ExternalInfo
    # in session; jsonify return flask.Response i just need a str
    extr_data_json = json.dumps(extr_data, default=to_serializable)

    bid = mdb.get_book_id(book.title_eng, book.title_foreign)
    if bid is not None:
        # book was alrdy in DB
        # -> add extinfo instead of importing whole book
        book.id = bid
        ext_info = ExternalInfo(mdb, book, **extr_data)
        eid, outdated = ext_info.save()
        flash(f"Added external link at '{ext_info.url}' to book!")
        return show_info(book_id=bid, show_outdated=eid if outdated else None)
    else:
        # dl cover as temp uuid name and display add book page
        import uuid
        filename = uuid.uuid4().hex
        cover_path = os.path.join(app.config["THUMBS_FOLDER"], filename)
        cover_dled = mdb.download_cover(thumb_url, cover_path)
        if not cover_dled:
            flash("Thumb couldnt be downloaded!")
        return show_add_book(book=book, cover_temp=filename if cover_dled else None,
                             extr_data=extr_data_json)


@app.route('/jump', methods=["POST"])
def jump_to_book_by_url():
    url = request.form['ext_url']

    extr_cls = extractor.find(url)
    id_onpage = extr_cls.book_id_from_url(url)
    imported_from = extr_cls.site_id
    # ids can get re-used by external sites so theyre not guaranteed to be unique
    # or even link to the correct extinfo/book
    books = list(mdb.get_books({"id_onpage": id_onpage, "imported_from": imported_from}))

    if not books:
        # passing var to func works directly when using optional param
        # while stilling being able to use the rout argument
        # route("/import"...) def import_book(url=None):...
        return import_book(url)
    elif len(books) > 1:
        flash("Please choose the book belonging to the supplied URL!", "title")
        flash("Due to external sites re-using their book IDs it can happen that "
              "a book ID on that page that lead too Book A now leads to Book B.")
        flash("There are multiple books in this DB which have the same external "
              "ID! Please choose the one that has the same title (and pages) as "
              "the one at the URL you supplied!", "info")
        flash("Click button add anyway if none of the shown books match the book "
              "you wanted to add!", "info")

        # if we want get params to have hyphens in them like ext-url and still wanna
        # be able to buil url with url_for we can pass in the params by unpacking
        # a dict: url_for('import_book', **{"ext-url": url}),
        return render_template(
            'show_entries.html',
            books=books,
            add_anyway=url_for('import_book', ext_url=url),
            order_col_libox="id",
            asc_desc="DESC")
    else:
        return show_info(book_id=None, book=books[0])


@app.route('/book/<int:book_id>/ext_info/<int:ext_info_id>/update')
def update_book_ext_info(book_id, ext_info_id):
    old_book = mdb.get_book(book_id)
    # could also pass in url using post or get
    ext_info = [ei for ei in old_book.ext_infos if ei.id == ext_info_id][0]
    status, new_book = ext_info.update_from_url()
    if status == "no_data":
        flash("Updating failed!", "warning")
        flash("Either there was something wrong with the url or the extraction failed!", "info")
        flash(f"URL was: {ext_info.url}")
        flash("Check the logs for more details!", "info")
        return show_info(book_id=book_id, book=old_book)
    elif status == "title_mismatch":
        flash("Update failed!", "warning")
        flash(f"Title of book at URL didn't match title '{old_book.title}'", "info")
        return show_info(book_id=book_id, book=old_book)

    changes, _ = old_book.diff(new_book)
    # filter changes and convert to jinja friendlier format
    changes = {key: changes[key] for key in changes if key not in {"id", "last_change",
                                                                   "note", "title"}}
    converted = {"normal": {col: changes[col] for col in changes
                            if col in Book.COLUMNS},
                 "added_removed": {col: changes[col] for col in changes
                                   if col in Book.ASSOCIATED_COLUMNS}
                 }
    # convert to status/lang name instead of id
    try:
        status_id = converted["normal"]["status_id"]
        converted["normal"]["status"] = STATUS_IDS[status_id]
        del converted["normal"]["status_id"]
    except KeyError:
        pass
    try:
        language_id = converted["normal"]["language_id"]
        converted["normal"]["language"] = mdb.language_map[language_id]
        del converted["normal"]["language"]
    except KeyError:
        pass

    flash("Book was updated!", "title")

    _, ext_info_chstr = ext_info.save()
    if ext_info_chstr:
        flash("WARNING", "warning")
        flash(f"Changes on external link {ext_info.site}:", "info")
        for change in ext_info_chstr.splitlines():
            flash(change, "info")

    # dont pass book so we get new book with updated ext_info from db
    return show_info(book_id, book_upd_changes=converted)


@app.route('/book/<int:book_id>/apply_update', methods=["POST"])
def apply_upd_changes(book_id):
    book = mdb.get_book(book_id)
    update_dic = {}
    for col, val in request.form.items():
        if col == "_csrf_token":
            continue
        elif col == "status":
            update_dic["status_id"] = STATUS_IDS[val]
        elif col == "language":
            update_dic["language_id"] = mdb.get_language(val)
        elif col in Book.COLUMNS:
            update_dic[col] = val
        else:
            add, remove = val.split(";;;")
            add = add.split(";") if add else []
            remove = remove.split(";") if remove else []
            # + add could produce duplicates but we know that none of the items in add
            # are in the col
            update_dic[col] = [v for v in getattr(book, col) + add if v not in remove]

    book.update_from_dict(update_dic)
    book.save()

    return show_info(book_id=book_id, book=book)


@app.route('/book/<int:book_id>/get_info_txt')
def get_info_txt(book_id):
    book = mdb.get_book(book_id)
    exp_str = book.to_export_string()
    import io
    # or use tempfile.SpooledTemporaryFile
    mem = io.BytesIO()
    # got error: applications must write bytes -> encode txt to byte
    mem.write(exp_str.encode("UTF-8"))
    # Make sure that the file pointer is positioned at the start of data to
    # send before calling send_file()
    mem.seek(0)
    # havent found a way to close file with just flask tools
    # even a helper class using weakref didnt work still got I/O on closed file error
    # -> Garbage collector will close file when it destroys file object
    # but you cant be certain when that happens.. see: https://stackoverflow.com/questions/1834556/does-a-file-object-automatically-close-when-its-reference-count-hits-zero

    # returning when using context mangaer with for handling the closing of file f
    # it didnt work since as soon as it returned the file was closed
    # after_this_request also doesnt work!
    return send_file(
            mem, mimetype="Content-Type: text/plain; charset=utf-8",
            # as attachment otherwise it just opens in the browser or you have to use save as
            as_attachment=True,
            # apparently also needs to be b/encoded otherwise we get an UnicodeEncodeError
            # if it contains non-ascii chars
            attachment_filename=f"{book.title.replace('/', '')}_info.txt".encode('utf-8')
            )


def first_last_more(books, after=None, before=None):
    if not books:
        return None, None, None

    more = {"next": None, "prev": None}

    # we alway get one row more to know if there are more results after our current last_id
    # in the direction we moved in
    if len(books) == BOOKS_PER_PAGE+1:
        onemore = True
    else:
        onemore = False

    if after is None and before is None:
        # firstpage
        if onemore:
            more["next"] = True
            del books[-1]
        else:
            more["next"] = False
    elif after is not None:
        # if we get args before/after there are more results for the opposite
        # e.g. if we get a before=61 we had to have had an after=60 that led us to that page
        more["prev"] = True
        if onemore:
            more["next"] = True
            # remove additional book
            del books[-1]
        else:
            more["next"] = False
    elif before is not None:
        more["next"] = True
        if onemore:
            more["prev"] = True
            del books[0]
        else:
            more["prev"] = False

    first_id = books[0].id
    last_id = books[-1].id
    return first_id, last_id, more


@app.route("/search", methods=["GET"])
def search_books():
    searchstr = request.args['searchstring']
    # prepare defaults so we dont always have to send them when using get
    order_by_col = request.args.get('order_by_col', "id", type=int)
    asc_desc = "ASC" if request.args.get('asc_desc', "DESC", type=str) == "ASC" else "DESC"
    after = request.args.get("after", None, type=int)
    before = request.args.get("before", None, type=int)

    order_by = f"Books.{order_by_col} {asc_desc}"
    # get 1 entry more than BOOKS_PER_PAGE so we know if we need btn in that direction
    books = mdb.search(searchstr, order_by=order_by, limit=BOOKS_PER_PAGE+1,
                       after=after, before=before)
    first_id, last_id, more = first_last_more(books, after, before)

    return render_template(
        'show_entries.html',
        books=books,
        more=more,
        first_id=first_id,
        last_id=last_id,
        search_field=searchstr,
        order_col_libox=order_by_col,
        asc_desc=asc_desc)


# function that accepts ajax request so we can add lists on show_info
# without reloading the page or going to edit
# WARNING vulnerable to cross-site requests
# TODO add token
@app.route("/book/<int:book_id>/list/<action>", methods=["POST"])
def list_action_ajax(book_id, action):
    list_name = request.form.get("name", None, type=str)
    # jquery will add brackets to key of ajax data of type array
    before = request.form.getlist("before[]", type=str)
    if list_name is None:
        return jsonify({"error": "Missing list name from data!"})

    if action == "add":
        # was getting Bad Request 400 due to testing print line below:
        # ...the issue is that Flask raises an HTTP error when it fails to find
        # a key in the args and form dictionaries. What Flask assumes by
        # default is that if you are asking for a particular key and it's not
        # there then something got left out of the request and the entire
        # request is invalid.
        # print("test",request.form["adjak"],"test")
        Book.add_assoc_col_on_book_id(mdb, book_id, "list", [list_name], before)
        # pass url back to script since we cant use url_for
        return jsonify({"added": list_name,
                        "search_tag_url": url_for('search_books',
                                                  searchstring=f'tag:"{list_name}"')})
    elif action == "remove":
        Book.remove_assoc_col_on_book_id(mdb, book_id, "list", [list_name], before)
        # pass url back to script since we cant use url_for
        return jsonify({"removed": list_name})
    else:
        flash(f"Supplied action '{action}' is not a valid list action!", "warning")
        return redirect(url_for("show_info", book_id=book_id))


@app.route("/book/<int:book_id>/set/fav/<int:fav_intbool>")
def set_favorite(book_id, fav_intbool):
    Book.set_favorite_id(mdb, book_id, fav_intbool)
    return redirect(
        url_for("show_info", book_id=book_id))


@app.route("/book/<book_id>/rate/<float:rating>")
def rate_book(book_id, rating):
    Book.rate_book_id(mdb, book_id, rating)
    return redirect(
        url_for("show_info", book_id=book_id))


@app.route("/book/<book_id>/ext_info/<int:ext_info_id>/set/downloaded/<int:intbool>")
def set_downloaded(book_id, ext_info_id, intbool):
    ExternalInfo.set_downloaded_id(mdb, ext_info_id, intbool)
    return redirect(
        url_for("show_info", book_id=book_id))


@app.route("/outdated", methods=["GET"])
def show_outdated_links():
    id_onpage = request.args.get("id_onpage", None, type=int)
    imported_from = request.args.get("imported_from", None, type=int)
    if id_onpage and imported_from:
        books = mdb.get_outdated(id_onpage, imported_from)
    else:
        books = mdb.get_outdated()

    flash("Showing books with outdated links!", "title")
    flash("Newest first!", "info")

    return render_template(
        'show_entries.html',
        books=books,
        order_col_libox="id",
        asc_desc="DESC")


@app.route("/book/<int:book_id>/add_ext_info", methods=["POST"])
def add_ext_info(book_id):
    url = request.form.get("url", None, type=str)
    # need title to ensure that external link matches book
    book_title = request.form.get("book_title", None, type=str)
    if not url or not book_title:
        flash(f"URL empty!")
        return redirect(url_for("show_info", book_id=book_id))
    book, ext_info, _ = MangaDB.retrieve_book_data(url)
    if book is None:
        flash("Adding external link failed!", "warning")
        flash("Either there was something wrong with the url or the extraction failed!", "info")
        flash(f"URL was: {url}")
        flash("Check the logs for more details!", "info")
        return show_info(book_id=book_id)
    if book.title != book_title:
        # just warn if titles dont match, its ultimately the users decision
        flash("Title of external link and book's title don't match!", "warning")
        flash(f"URL: {url}", "info")

    # @Hack @Cleanup assigning book id to book we dont want to save in order
    # to be able to save ext_info
    book.id = book_id
    ei_id, outdated = ext_info.save()

    flash(f"External link was added as id {ei_id}")
    return show_info(book_id=book_id, show_outdated=ext_info.id if outdated else None)


@app.route("/book/add")
def show_add_book(book=None, cover_temp=None, extr_data=None):
    if book is None:
        # @Hack
        data = {"list": [], "tag": [], "category": [], "parody": [],
                "groups": [], "character": [], "collection": [], "artist": []}
        book = Book(mdb, **data)
    available_options = book.get_all_options_for_assoc_columns()
    available_options["language"] = [(_id, name) for _id, name in mdb.language_map.items()
                                     if type(_id) == int]
    available_options["status"] = [(_id, name) for _id, name in STATUS_IDS.items()
                                   if type(_id) == int]

    return render_template(
        'edit_info.html',
        book=book,
        available_options=available_options,
        cover_temp_name=cover_temp,
        extr_data=extr_data)


@app.route("/book/add/submit", methods=["POST"])
def add_book():
    data = {}
    for col in Book.COLUMNS:
        val = request.form.get(col, None)
        if col in ("pages", "status_id", "language_id"):
            val = int(val)
        elif col == "my_rating":
            # dont add if empty string or 0..
            if not val:
                continue
            val = float(val)
        data[col] = val
    for col in Book.ASSOCIATED_COLUMNS:
        val_list = request.form.getlist(col)
        data[col] = val_list
    book = Book(mdb, **data)
    extr_data = request.form.get("extr_data_json", None)
    if extr_data:
        extr_data = json.loads(extr_data)
        # convert date string back to dateteime date
        import datetime
        extr_data["upload_date"] = datetime.datetime.strptime(
                extr_data["upload_date"], "%Y-%m-%d").date()
        ext_info = ExternalInfo(mdb, book, **extr_data)
        book.ext_infos = [ext_info]

    # we also use add_book to import books -> we need outdated_on_ei_id
    bid, outdated_on_ei_id = book.save(block_update=True)
    outdated_on_ei_id = outdated_on_ei_id[0] if outdated_on_ei_id else None

    # rename book cover if one was uploaded with temp name
    temp_name = request.form.get("cover_temp_name", None)
    if temp_name is not None:
        os.rename(os.path.join(app.config["THUMBS_FOLDER"], temp_name),
                  os.path.join(app.config["THUMBS_FOLDER"], str(bid)))
    return show_info(book_id=bid, book=book, show_outdated=outdated_on_ei_id)


@app.route("/book/add/cancel", methods=["POST"])
def cancel_add_book():
    # instead of using js to read out cover_temp_name and using ajax to send POST request
    # to this funcs url i could insert a form with only one field a hidden input with
    # cover_temp_name as value and bind the cancel button to submit the form
    # (cant do it in the noraml form since i have required fields)

    # Use request.get_data() to get the raw data, regardless of content type.
    # The data is cached and you can subsequently access request.data, request.json,
    # request.form at will.
    # If you access request.data first, it will call get_data with an argument to parse form data
    # first. If the request has a form content type (multipart/form-data,
    # application/x-www-form-urlencoded, or application/x-url-encoded) then the raw data will be
    # consumed. request.data and request.json will appear empty in this case.
    # print(request.get_data())
    # specified contentType text/plain here so .data works
    # del temp book cover file if we dont add book
    temp_name = request.data
    if temp_name:
        os.remove(os.path.join(app.config["THUMBS_FOLDER"], temp_name.decode("UTF-8")))
    # js takes care of the redirection
    return url_for("show_entries")


@app.route("/book/edit/<int:book_id>")
def show_edit_book(book_id, book=None):
    if book is None:
        book = mdb.get_book(book_id)
    if book is None:
        return render_template(
            'show_info.html',
            error_msg=f"No book with id {book_id} was found in DB!")

    available_options = book.get_all_options_for_assoc_columns()
    available_options["language"] = [(_id, name) for _id, name in mdb.language_map.items()
                                     if type(_id) == int]
    available_options["status"] = [(_id, name) for _id, name in STATUS_IDS.items()
                                   if type(_id) == int]

    return render_template(
        'edit_info.html',
        book=book,
        available_options=available_options)


@app.route("/book/edit/<int:book_id>/submit", methods=["POST"])
def edit_book(book_id):
    book = mdb.get_book(book_id)

    update_dic = {}
    # fine here since i just get the col names in COLUMNS and ASSOCIATED_COLUMNS
    # but have to be careful not to just e.g. iterate over the request.form dict or
    # whatever and execute sql queries with col names substituted in f-string and not
    # through db api params (? and :kwarg), someone could change the name field on
    # an input tag to DELETE FROM Books and all entries could get deleted
    # example: col, tag: ('SELECT * FROM Books', 'French Kissing') -> would in my case
    # even if it got inserted still just produce an error
    # esp combination with executescript is dangerous since you can use ; to start
    # another statement ...;DROP Table
    for col in Book.COLUMNS:
        val = request.form.get(col, None)
        if col in ("pages", "status_id", "language_id"):
            val = int(val)
        elif col == "my_rating":
            # dont add if empty string or 0..
            if not val:
                continue
            try:
                val = float(val)
            except ValueError:
                app.logger.warning("Couldnt convert value '%s' to float for column '%s'",
                                   val, col)
                flash(f"{col} needs to be a floating point number!", "info")
                return redirect(url_for("show_edit_book", book_id=book_id))
        update_dic[col] = val
    for col in Book.ASSOCIATED_COLUMNS:
        if col == "ext_infos":
            continue
        val_list = request.form.getlist(col)
        update_dic[col] = val_list

    book.update_from_dict(update_dic)
    book.save()

    # @Speed could also pass book to show_info directly, but by getting book from db
    # again we can see if changes applied correctly?
    return redirect(url_for("show_info", book_id=book_id))


# code for file uploading taken from:
# http://flask.pocoo.org/docs/1.0/patterns/fileuploads/ and
# https://stackoverflow.com/questions/50069199/send-file-with-flask-and-return-a-data-without-refreshing-the-html-page
# https://stackoverflow.com/questions/32724971/jquery-file-upload-without-redirect
def allowed_thumb_ext(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_THUMB_EXTENSIONS


@app.route('/book/<int:book_id>/upload_cover', methods=['POST'])
def upload_cover(book_id):
    # check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file data recieved!"})
    file_data = request.files['file']
    # if user does not select file, browser also
    # submit an empty part without filename
    if file_data.filename == '':
        return jsonify({"error": "No file selected!"})
    if file_data and allowed_thumb_ext(file_data.filename):
        if book_id == 0:
            # generate unique filename for book that has no book id yet
            # insert as hidden field into add_book and rename to book id then
            # Version 4: These are generated from random (or pseudo-random) numbers. If you just
            # need to generate a UUID, this is probably what you want.
            import uuid
            filename = uuid.uuid4().hex

            # del old cover if there is one
            old_temp = request.form.get("old_cover_temp_name", None)
            if old_temp:
                os.remove(os.path.join(app.config['THUMBS_FOLDER'], old_temp))
        else:
            filename = str(book_id)
        from PIL import Image
        # file_data is only the wrapper (werkzeug.FileStorag) open actual file with .stream
        # (SpooledTemporaryFile)
        img = Image.open(file_data.stream)
        # convert to thumbnail (in-place) tuple is max size, keeps apsect ratio
        img.thumbnail((400, 600))
        # when saving without extension we need to pass format kwarg
        img.save(os.path.join(app.config['THUMBS_FOLDER'], filename), format=img.format)
        img.close()
        file_data.close()
        return jsonify({'cover_path': url_for('thumb_static', filename=filename)})
    else:
        return jsonify({"error": "Wrong extension for thumb!"})


@app.route('/book/<int:book_id>/remove')
def remove_book(book_id):
    book = mdb.get_book(book_id)
    book.remove()
    flash(f"Book '{book.title}' was removed from MangaDB!")
    return redirect(url_for('show_entries'))


@app.route('/book/<int:book_id>/ext_info/<int:ext_info_id>/remove')
def remove_ext_info(book_id, ext_info_id):
    book = mdb.get_book(book_id)
    url = book.remove_ext_info(ext_info_id)
    if url is None:
        flash(f"External link with id {ext_info_id} wasnt found on book!")
    else:
        flash(f"External link with url '{url}' was removed from Book!")
    return show_info(book_id=book_id, book=book)


def main(debug=False):
    load_admin_credentials(app)
    # debug=True, port=5000
    app.run(debug=debug)


if __name__ == "__main__":
    main()
