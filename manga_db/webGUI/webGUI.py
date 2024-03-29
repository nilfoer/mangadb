"""
File: webGUI.py
Description: Creates webGUI for manga_db using flask
"""

import os.path
import json
import re
import time
import datetime

import werkzeug

from typing import Optional, Dict, Any, Sequence, cast, Union

from flask import (
    current_app, request, redirect, url_for, Blueprint,
    render_template, flash, send_from_directory,
    jsonify, send_file, session, g
)
from markupsafe import Markup

from .mdb import get_mdb
from .json_custom import to_serializable
from ..constants import STATUS_IDS
from ..manga_db import MangaDB, update_cookies_from_file
from ..manga import Book
from ..extractor.base import MangaExtractorData
from ..import extractor
from ..db.search import validate_order_by_str
from ..ext_info import ExternalInfo
from .. import extractor

BOOKS_PER_PAGE = 60

# thumb extensions
ALLOWED_THUMB_EXTENSIONS = set(('png', 'jpg', 'jpeg', 'gif'))

# no url prefix
main_bp = Blueprint("main", __name__)

URL_RE = re.compile(r"(?:https?://)?(?:\w+\.)?(\w+\.\w+)/")


# create route for thumbs/static data that isnt in static, can be used in template with
@main_bp.route('/thumbs/<path:filename>')
def thumb_static(filename):
    cover_timestamp = request.args.get("cover_timestamp", 0, type=float)
    fn = f"{filename}_{cover_timestamp:.0f}"
    return send_from_directory(current_app.config['THUMBS_FOLDER'], fn)


@main_bp.route('/refresh_cookie')
def refresh_cookies_file():
    # NOTE: assumes cookie file is at app.instance_path\cookies.txt
    success = update_cookies_from_file(os.path.join(current_app.instance_path, 'cookies.txt'),
                                       has_custom_info=True)
    if success:
        flash("Cookies updated successfully!", "title")
    else:
        flash("Failed updating from cookies file!", "title warning")
        flash("Either the cookie file was not found at 'instance/cookies.txt' or "
              "the file is not a valid Netscape HTTP Cookie File", "info")
        flash("Also make sure you used the Firefox extension NoRobot Exporter. "
              "It exports all relevant information for authenticating with DDoS "
              "protection services like Cloudflare from your browser!", "info")

    return redirect(url_for("main.show_entries"))


def handle_search_sort():
    user_sort_col, user_sort_dir = session.get(
        'user_search_pref', (None, None))
    # prioritize get args over user settings stored in session cookie
    order_by_col = request.args.get(
        'sort_col', None, type=str) or user_sort_col
    asc_desc = request.args.get('order', None, type=str) or user_sort_dir

    new_search_pref = bool(order_by_col or asc_desc)
    # in case one of them is None
    order_by_col = order_by_col or "id"
    asc_desc = asc_desc or "DESC"
    # validate our sorting prefs otherwise were vulnerable to sql injection
    if not validate_order_by_str(order_by_col):
        order_by_col = "id"
    if not validate_order_by_str(asc_desc):
        asc_desc = "DESC"

    if new_search_pref:
        session['user_search_pref'] = (order_by_col, asc_desc)

    return order_by_col, asc_desc


def get_books(query=None):
    order_by_col, asc_desc = handle_search_sort()
    order_by = f"Books.{order_by_col} {asc_desc}"
    # dont need to validate since we pass them in with SQL param substitution
    after = request.args.getlist("after", None)
    after = after if after else None
    before = request.args.getlist("before", None)
    before = before if before else None

    # branch on condition if we have a NULL for the primary sorting col
    # order_by_col isnt id but we only got one value from after/before
    if after is not None and len(after) == 1 and order_by_col != "id":
        after = (None, after[0])
    elif before is not None and len(before) == 1 and order_by_col != "id":
        before = (None, before[0])

    if query:
        # get 1 entry more than BOOKS_PER_PAGE so we know if we need btn in that direction
        books = get_mdb().search(query, order_by=order_by, limit=BOOKS_PER_PAGE+1,
                                 after=after, before=before)
    else:
        books = get_mdb().get_x_books(BOOKS_PER_PAGE+1, after=after, before=before,
                                      order_by=order_by)
    first, last, more = first_last_more(books, order_by_col, after, before)

    return books, order_by_col, asc_desc, first, last, more


@main_bp.route('/', methods=["GET"])
def show_entries():
    books, order_by_col, asc_desc, first, last, more = get_books()
    return render_template(
        'show_entries.html',
        books=books,
        more=more,
        first=first,
        last=last,
        order_col=order_by_col,
        asc_desc=asc_desc)


@main_bp.route('/book/<int:book_id>')
def show_info(book_id, book=None, book_upd_changes=None, show_outdated=None,
              add_ei_or_new_book_prompt=None):
    mdb = get_mdb()
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
            books_in_collection = mdb.get_books_in_collection(collection)
            collections.append((collection, books_in_collection))

    outdated = None
    if show_outdated:
        try:
            ei = [ei for ei in book.ext_infos if ei.id == show_outdated][0]
        except IndexError:
            current_app.logger.error("Cant show outdated id %d not found in books ext_infos",
                                     show_outdated)
        else:
            outdated = ei.get_outdated_extinfo_same_pageid()

    return render_template(
        'show_info.html',
        book=book,
        collections=collections,
        # rather than spend a lot of time/code to replace title_eng and _foreign with title in
        # rows make title func available to jinja by passing it in as param
        build_title=Book.build_title,
        lists=[row["name"]
               for row in book.get_all_options_for_assoc_column("list")],
        book_upd_changes=book_upd_changes,
        outdated=outdated,
        add_ei_or_new_book_prompt=add_ei_or_new_book_prompt)


def flash_cookie_update_msg():
    flash("Failed getting book: Service unavailable!", "title warning")
    flash("If you can visit the site normally using your browser you probably "
          "have to create/update the cookies.txt inside you 'instance' folder!", "info")
    flash("You can do that using the 'NoRobot Exporter' Firefox extension", "info")
    flash("After updating the file: Hit the 'Refresh cookies' button inside the "
          "toolbox and then try again!", "info")


@main_bp.route('/import', methods=["POST"])
def import_book(url: Optional[str] = None, force_new: bool = False):
    if url is None:
        url = request.form['ext_url']

    mdb = get_mdb()
    extr_data: Optional[Dict[str, Any]]
    thumb_url: Optional[str]
    extr_data, thumb_url = None, None
    book: Book

    # whether the import should be added as external link to an existing book instead
    add_ext_info = False
    if "extr_data_json" in request.form:
        # coming from add as external or new book prompt!!
        extr_data = json.loads(request.form['extr_data_json'])
        thumb_url = request.form['thumb_url']
        # during json conversion datetime was converted to a str (in isoformat)
        extr_data["upload_date"] = datetime.date.fromisoformat(
            extr_data['upload_date'])
        if request.form['action'] == "add_new":
            force_new = True
        else:
            add_ext_info = True
        # @CleanUp indirection needed here?
        book = mdb.book_from_data(MangaExtractorData(**extr_data))
    else:
        extr_data, thumb_url, err_code = mdb.retrieve_book_data(url)
        if extr_data is None:
            if err_code == 503:
                flash_cookie_update_msg()
            else:
                flash("Failed getting book!", "title warning")
                flash("Either there was something wrong with the url or the extraction failed!",
                      "info")
                flash(f"URL was: {url}")
                flash("Check the logs for more details!", "info")
            return redirect(url_for("main.show_entries"))
        book = mdb.book_from_data(extr_data)

    bid = mdb.get_book_id(
        book.title_eng, book.title_foreign) if not force_new else None
    if add_ext_info:
        # -> add extinfo instead of importing whole book => NO since if its in id_map
        # book.ext_infos wont match state in DB
        book_in_db = mdb.get_book(bid)
        ext_info = ExternalInfo(mdb, book_in_db, **extr_data)
        eid, outdated = ext_info.save()
        # @Temporary add ei to book.ext_infos
        book_in_db.ext_infos.append(ext_info)

        flash(f"Added external link at '{ext_info.url}' to book!")
        return show_info(bid, show_outdated=eid if outdated else None)

    # convert data to json so we can rebuilt ext_info when we add it to DB
    # as we have to take all data from edit_info page or store a json serialized ExternalInfo
    # in session; jsonify return flask.Response i just need a str
    extr_data_json = json.dumps(extr_data, default=to_serializable)
    if bid is not None:
        # book was alrdy in DB
        # show prompt to add extinfo or add as a new book
        return show_info(bid, add_ei_or_new_book_prompt=(url, extr_data_json, thumb_url))
    else:
        # dl cover as temp and display add book page
        # only allow one temp cover
        # change this to temp_cover_{username} if we add multiple user support
        cover_dled = mdb.download_cover(
            thumb_url, current_app.config["THUMBS_FOLDER"], bid,
            overwrite=True, forced_filename="temp_cover_0")
        if not cover_dled:
            current_app.logger.error(
                "Could not download cover for book at %s with thumb url %s",
                url, thumb_url)
            flash("Thumb couldnt be downloaded!")

        return show_add_book(book=book, cover_uploaded=time.time() if cover_dled else 0,
                             extr_data=extr_data_json)


@main_bp.route('/jump', methods=["GET"])
def jump_to_book_by_url():
    url = request.args['ext_url']

    extr_cls = extractor.find(url)
    id_onpage = extr_cls.book_id_from_url(url)
    imported_from = extr_cls.site_id
    # ids can get re-used by external sites so theyre not guaranteed to be unique
    # or even link to the correct extinfo/book
    books = list(get_mdb().get_books(
        {"id_onpage": id_onpage, "imported_from": imported_from}))

    if not books:
        # passing var to func works directly when using optional param
        # while stilling being able to use the rout argument
        # route("/import"...) def import_book(url=None):...
        return render_template(
            'book.html',
            error_msg=f"Book wasn't found in the Database! Should it be imported?",
            import_url=url)
    elif len(books) > 1:
        flash("Please choose the book belonging to the supplied URL!", "title")
        flash("Due to external sites re-using their book IDs it can happen that "
              "a book ID on that page that lead to Book A now leads to Book B.")
        flash("There are multiple books in this DB which have the same external "
              "ID! Please choose the one that has the same title (and pages) as "
              "the one at the URL you supplied!", "info")
        flash("Click button add anyway if none of the shown books match the book "
              "you wanted to add!", "info")

        # if we want get params to have hyphens in them like ext-url and still wanna
        # be able to buil url with url_for we can pass in the params by unpacking
        # a dict: url_for('main.import_book', **{"ext-url": url}),
        return render_template(
            'show_entries.html',
            books=books,
            add_anyway=url,
            order_col_libox="id",
            asc_desc="DESC")
    else:
        return redirect(url_for("main.show_info", book_id=books[0].id))


@main_bp.route('/book/<int:book_id>/ext_info/<int:ext_info_id>/update', methods=("POST",))
def update_book_ext_info(book_id, ext_info_id):
    mdb = get_mdb()
    old_book = mdb.get_book(book_id)
    # could also pass in url using post or get
    ext_info = [ei for ei in old_book.ext_infos if ei.id == ext_info_id][0]
    status, new_book = ext_info.update_from_url()
    if status == "no_data":
        flash("Updating failed!", "title warning")
        flash("Either there was something wrong with the url or the extraction failed!", "info")
        flash(f"URL was: {ext_info.url}")
        flash("Check the logs for more details!", "info")
        return redirect(url_for("main.show_info", book_id=book_id))
    elif status == "title_missmatch":
        flash("Update failed!", "title warning")
        flash(
            f"Title of book at URL didn't match title '{old_book.title}'", "info")
        return redirect(url_for("main.show_info", book_id=book_id))

    changes, _ = old_book.diff(new_book)
    # filter changes and convert to jinja friendlier format
    changes = {key: changes[key] for key in changes if key not in {"id", "last_change",
                                                                   "note", "title",
                                                                   "favorite", "list"}}
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
        # TODO leave normal lang col without id since this adds a lang if its not present
        language_id = converted["normal"]["language_id"]
        converted["normal"]["language"] = mdb.language_map[language_id]
        del converted["normal"]["language"]
    except KeyError:
        pass

    flash("External link was updated!", "title")

    _, ext_info_chstr = ext_info.save()
    if ext_info_chstr:
        # :re_dl_warning
        if ext_info_chstr.startswith("Please re-download"):
            flash("WARNING", "warning")
        flash(f"Changes on external link on {ext_info.site}:", "info")
        for change in ext_info_chstr.splitlines():
            if change.startswith("last_update"):
                continue
            flash(change, "info")

    # putting the converted changes on g doesnt work since we redirect
    # and thats a new request and g only stays valid for the current one
    return show_info(book_id, book_upd_changes=converted if changes else None)


@main_bp.route('/book/<int:book_id>/apply_update', methods=["POST"])
def apply_upd_changes(book_id):
    mdb = get_mdb()
    book = mdb.get_book(book_id)
    update_dic = {}
    for col, val in request.form.items():
        if col == "_csrf_token":
            continue
        elif col == "pages":
            update_dic[col] = int(val)
        elif col == "status":
            update_dic["status_id"] = STATUS_IDS[val]
        elif col == "language":
            update_dic["language_id"] = mdb.get_language(
                val, create_unpresent=True)
        elif col in Book.COLUMNS:
            update_dic[col] = val
        else:
            add, remove = val.split(";;;")
            add = add.split(";") if add else []
            remove = remove.split(";") if remove else []
            # + add could produce duplicates but we know that none of the items in add
            # are in the col
            update_dic[col] = [v for v in getattr(
                book, col) + add if v not in remove]

    book.update_from_dict(update_dic)
    book.save()

    return redirect(url_for("main.show_info", book_id=book_id))


@main_bp.route('/book/<int:book_id>/get_info_txt')
def get_info_txt(book_id):
    book = get_mdb().get_book(book_id)
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
        attachment_filename=f"{book.title.replace('/', '')}_info.txt"
    )


def first_last_more(books, order_by_col="id", after=None, before=None):
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
    if "id" != order_by_col.lower():
        # if we are sorting by something else than id
        # we also need to pass the values of that col
        primary_first = getattr(books[0], order_by_col)
        primary_last = getattr(books[-1], order_by_col)
        return (primary_first, first_id), (primary_last, last_id), more
    else:
        return first_id, last_id, more


@main_bp.route("/search", methods=["GET"])
def search_books():
    searchstr = request.args['q']
    if URL_RE.match(searchstr):
        return redirect(url_for("main.jump_to_book_by_url", ext_url=searchstr))

    books, order_by_col, asc_desc, first, last, more = get_books(searchstr)

    return render_template(
        'show_entries.html',
        books=books,
        more=more,
        first=first,
        last=last,
        search_field=searchstr,
        order_col=order_by_col,
        asc_desc=asc_desc)


# function that accepts ajax request so we can add lists on show_info
# without reloading the page or going to edit
@main_bp.route("/book/<int:book_id>/list/<action>", methods=["POST"])
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
        Book.add_assoc_col_on_book_id(
            get_mdb(), book_id, "list", [list_name], before)
        # pass url back to script since we cant use url_for
        return jsonify({"added": list_name,
                        "search_tag_url": url_for('main.search_books',
                                                  q=f'tag:"{list_name}"')})
    elif action == "remove":
        Book.remove_assoc_col_on_book_id(
            get_mdb(), book_id, "list", [list_name], before)
        return jsonify({"removed": list_name})
    else:
        return jsonify({
            "error": f"Supplied action '{action}' is not a valid list action!"
        })


@main_bp.route("/book/<int:book_id>/set/fav/<int:fav_intbool>")
def set_favorite(book_id, fav_intbool):
    Book.set_favorite_id(get_mdb(), book_id, fav_intbool)
    return redirect(
        url_for("main.show_info", book_id=book_id))


@main_bp.route("/book/<int:book_id>/rate/<float:rating>")
def rate_book(book_id, rating):
    Book.rate_book_id(get_mdb(), book_id, rating)
    return redirect(
        url_for("main.show_info", book_id=book_id))


# TODO these set.. routes should use POST
@main_bp.route("/book/<int:book_id>/ext_info/<int:ext_info_id>/set/downloaded/<int:intbool>")
def set_downloaded(book_id, ext_info_id, intbool):
    ExternalInfo.set_downloaded_id(get_mdb(), ext_info_id, intbool)
    return redirect(
        url_for("main.show_info", book_id=book_id))


@main_bp.route("/outdated", methods=["GET"])
def show_outdated_links():
    id_onpage = request.args.get("id_onpage", None, type=str)
    imported_from = request.args.get("imported_from", None, type=int)
    if id_onpage and imported_from:
        books = get_mdb().get_outdated(id_onpage, imported_from)
    else:
        books = get_mdb().get_outdated()

    flash("Showing books with outdated links!", "title")
    flash("Newest first!", "info")

    return render_template(
        'show_entries.html',
        books=books,
        order_col_libox="id",
        asc_desc="DESC")


@main_bp.route("/book/<int:book_id>/add_ext_info", methods=["POST"])
def add_ext_info(book_id):
    url = request.form.get("url", None, type=str)
    if not url:
        return redirect(url_for("main.show_edit_ext_info", book_id=book_id))

    try:
        extr_cls = extractor.find(url)
    except extractor.NoExtractorFound:
        flash("The domain of the external link is not yet supported but you can add "
              "an external link here manually!", "info")
        # unsupported url -> manual add
        return redirect(url_for("main.show_edit_ext_info", book_id=book_id, url=url))

    extr_data, _, err_code = MangaDB.retrieve_book_data(url)
    if extr_data is None:
        if err_code == 503:
            flash_cookie_update_msg()
        else:
            flash("Adding external link failed!", "title warning")
            flash(
                "Either there was something wrong with the url or the extraction failed!", "info")
            flash(f"URL was: {url}")
            flash("Check the logs for more details!", "info")
        return redirect(url_for("main.show_info", book_id=book_id))

    mdb: MangaDB = get_mdb()

    # need title to ensure that external link matches book
    book = mdb.get_book(book_id)
    ei_book, ext_info = mdb.book_and_ei_from_data(extr_data)
    if ei_book.title != book.title:
        # just warn if titles dont match, its ultimately the users decision
        flash("Title of external link and book's title doesn't match!", "title warning")
        flash(f"URL: {url}", "info")

    # @Temporary getting book to be able to save ext_info and adding ext_info manually to ext_infos
    b = mdb.get_book(book_id)
    ext_info.book = b
    b.ext_infos.append(ext_info)
    ei_id, outdated = ext_info.save()

    flash(f"External link was added as id {ei_id}")
    return show_info(book_id, show_outdated=ext_info.id if outdated else None)


@main_bp.route("/book/add")
def show_add_book(book=None, cover_uploaded=None, extr_data=None):
    mdb = get_mdb()
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

    # @Hack HUGE need to throw away ids otherwise sorting doesnt work with book.tag
    # also change this in add_book
    available_options["tag"] = [name for (_, name) in available_options["tag"]]
    return render_template(
        'edit_info.html',
        book=book,
        available_options=available_options,
        cover_uploaded=cover_uploaded,
        extr_data=extr_data)


@main_bp.route("/book/add/submit", methods=["POST"])
def add_book():
    mdb = get_mdb()
    data = book_form_to_dic(request.form)
    book = Book(mdb, **data)
    extr_data = request.form.get("extr_data_json", None)
    if extr_data:
        extr_data = json.loads(extr_data)
        # convert date string back to dateteime date
        extr_data["upload_date"] = datetime.date.fromisoformat(
            extr_data["upload_date"])
        ext_info = ExternalInfo(mdb, book, **extr_data)
        book.ext_infos = [ext_info]

    # we also use add_book to import books -> we need outdated_on_ei_id
    bid, outdated_on_ei_id = book.save(block_update=True, force=True)
    outdated_on_ei_id = outdated_on_ei_id[0] if outdated_on_ei_id else None

    # rename book cover if one was uploaded
    if request.form.get("cover_uploaded", None):
        # first cover will always have timestamp 0
        os.replace(os.path.join(current_app.config["THUMBS_FOLDER"], "temp_cover_0"),
                   os.path.join(current_app.config["THUMBS_FOLDER"], f"{bid}_0"))

    return show_info(bid, book=book, show_outdated=outdated_on_ei_id)


@main_bp.route("/book/add/cancel", methods=["POST"])
def cancel_add_book():
    # instead of using js to read out cover_uploaded and using ajax to send POST request
    # to this funcs url i could insert a form with only one field a hidden input with
    # cover_uploaded as value and bind the cancel button to submit the form
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
    cover_uploaded = request.data
    if cover_uploaded:
        os.remove(os.path.join(
            current_app.config["THUMBS_FOLDER"], "temp_cover_0"))
    # js takes care of the redirection
    return url_for("main.show_entries")


@main_bp.route("/book/edit/<int:book_id>")
def show_edit_book(book_id, book=None):
    mdb = get_mdb()
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
    # @Hack HUGE need to throw away ids otherwise sorting doesnt work with book.tag
    # also change this in add_book
    available_options["tag"] = [name for (_, name) in available_options["tag"]]

    return render_template(
        'edit_info.html',
        book=book,
        available_options=available_options)


def book_form_to_dic(form):
    result = {}
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
        val = form.get(col, None)
        if val is None:
            continue
        elif col in ("pages", "status_id", "language_id"):
            val = int(val.strip())
        elif col == "read_status":
            val = int(val.strip()) if val != "" else val
        elif col == "my_rating":
            val = float(val.strip()) if val != "" else val
        elif col == "nsfw":
            val = int(val)

        if not isinstance(val, str):
            result[col] = val
        else:
            val = val.strip()
            # add None instead of empty strings!
            result[col] = val if val else None
    for col in Book.ASSOCIATED_COLUMNS:
        if col == "ext_infos":
            continue
        val_list = form.getlist(col)
        result[col] = val_list
    return result


@main_bp.route("/book/edit/<int:book_id>/submit", methods=["POST"])
def edit_book(book_id):
    book = get_mdb().get_book(book_id)

    update_dic = book_form_to_dic(request.form)
    update_dic['nsfw'] = int(update_dic['nsfw'])

    book.update_from_dict(update_dic)

    # change cover if one was uploaded
    cover_timestamp = request.form.get("cover_uploaded", None, type=float)
    if cover_timestamp:
        thumb_dir = current_app.config['THUMBS_FOLDER']

        # delete old cover if present
        try:
            os.remove(os.path.join(
                thumb_dir, f"{book_id}_{book.cover_timestamp:.0f}"))
        except FileNotFoundError:
            pass

        # replace with new one and update timestamp
        # rename instead of os.replace so it crashes on existing file
        os.rename(os.path.join(thumb_dir, "temp_cover_0"),
                  os.path.join(thumb_dir, f"{book_id}_{cover_timestamp:.0f}"))
        book.cover_timestamp = cover_timestamp

    book.save()

    return redirect(url_for("main.show_info", book_id=book_id))


@main_bp.route("/book/edit/<int:book_id>/ext_info", defaults={'ext_info_id': None})
@main_bp.route("/book/edit/<int:book_id>/ext_info/<int:ext_info_id>")
def show_edit_ext_info(book_id, ext_info_id, book=None):
    mdb = get_mdb()
    if book is None:
        book = mdb.get_book(book_id)
    if book is None:
        return render_template(
            'show_info.html',
            error_msg=f"No book with id {book_id} was found in DB!")

    if ext_info_id is None:
        ext_info = ExternalInfo(mdb, book, imported_from=extractor.MANUAL_ADD)
    else:
        book.update_ext_infos()
        try:
            ext_info = next(e for e in book._ext_infos if e.id == ext_info_id)
        except StopIteration:
            flash(
                f"No external info with that id found on book with id {book.id}", "title warning")
            return redirect(url_for('main.show_entries'))

    url = request.args.get("url", None)

    return render_template(
        'edit_ext_info.html',
        book=book,
        ext_info=ext_info,
        url=url)


@main_bp.route("/book/edit/<int:book_id>/ext_info/submit", defaults={'ext_info_id': None}, methods=['POST'])
@main_bp.route("/book/edit/<int:book_id>/ext_info/<int:ext_info_id>/submit", methods=['POST'])
def edit_ext_info(book_id: int, ext_info_id: int,
                  book: Optional[Book] = None) -> Union[str, werkzeug.Response]:
    mdb = get_mdb()
    if book is None:
        book = mdb.get_book(book_id)
    if book is None:
        return render_template(
            'show_info.html',
            error_msg=f"No book with id {book_id} was found in DB!")

    if ext_info_id is None:
        ext_info = ExternalInfo(mdb, book, imported_from=extractor.MANUAL_ADD)
    else:
        book.update_ext_infos()
        try:
            ext_info = next(e for e in book._ext_infos if e.id == ext_info_id)
        except StopIteration:
            flash(
                f"No external info with that id found on book with id {book.id}", "title warning")
            return redirect(url_for('main.show_entries'))

    if ext_info_id is None:
        # add to book
        book.ext_infos.append(ext_info)

        ext_info.id_onpage = request.form['id_onpage']

    try:
        ext_info.upload_date = datetime.date.fromisoformat(
            request.form['upload_date'])
    except ValueError:
        flash("Could not set date on external info since the date had the wrong format!", "warning")
        return redirect(url_for(
            "main.show_edit_ext_info", book_id=book_id, ext_info_id=ext_info_id,
            url=request.form['id_onpage']))

    uploader = request.form['uploader']
    ext_info.uploader = uploader if uploader else None
    censorship_status = request.form['censorship_status']
    ext_info.censorship = censorship_status
    rating = request.form['rating']
    ext_info.rating = float(rating) if rating else None
    ratings = request.form['ratings']
    ext_info.ratings = int(ratings) if ratings else None
    favorites = request.form['favorites']
    ext_info.favorites = int(favorites) if favorites else None
    ext_info.downloaded = int(request.form['downloaded'])

    ext_info.save(manual=True)

    return redirect(url_for("main.show_info", book_id=book_id))


# TODO change this to use collection_id
@main_bp.route("/collection/edit/<string:collection_name>")
def show_edit_collection(collection_name: str,
                         books_in_collection: Optional[Sequence[Book]] = None) -> str:
    mdb = get_mdb()
    if books_in_collection is None:
        collection_id = cast(
            int, mdb.get_collection_id_from_name(collection_name))
        if collection_id is None:
            return render_template(
                'edit_collection.html',
                collection_name=collection_name,
                books_in_collection=[],
                error_msg=f"No collection with name {collection_name} was found!")
        books_in_collection = mdb.get_books_in_collection(collection_name)

    if books_in_collection is None:
        return render_template(
            'edit_collection.html',
            collection_name=collection_name,
            books_in_collection=[])

    return render_template(
        'edit_collection.html',
        collection_name=collection_name,
        books_in_collection=books_in_collection)


@main_bp.route("/collection/edit/<string:collection_name>/submit", methods=['POST'])
def edit_collection(collection_name: str) -> werkzeug.wrappers.Response:
    new_collection_name = request.form['new_collection_name'].strip()
    mdb = get_mdb()

    # NOTE: !IMPORTANT! do this BEFORE we change title
    # should never land here from a manual url -> just assume we get a collection_id back
    collection_id = cast(int, mdb.get_collection_id_from_name(collection_name))

    if new_collection_name != collection_name:
        success = mdb.update_tag_name(
            'collection', collection_id, new_collection_name)
        if not success:
            flash(
                "Saving changes failed due to the new name not being unique!", "title warning")
            # NOTE: if we want html inside a flash message we need to wrap it in flask.Markup
            # Marks a string as being safe for inclusion in HTML/XML output without needing to be escaped
            # so be careful ! no user input
            flash(Markup(
                "Edit the collection that is blocking the renaming: <a href=\""
                f"{url_for('main.show_edit_collection', collection_name=new_collection_name)}\""
                f">{new_collection_name}</a>"), "info")
            return redirect(url_for('main.show_edit_collection', collection_name=collection_name))

    bid_new_cidx = [(int(bid[5:]), int(cidx)) for (bid, cidx) in request.form.items()
                    if bid.startswith("cidx_")]
    if bid_new_cidx:
        mdb.update_in_collection_order(collection_id, bid_new_cidx)

    return redirect(url_for('main.show_edit_collection', collection_name=new_collection_name))


@main_bp.route("/delete-collection/<string:collection_name>", methods=['POST'])
def delete_collection(collection_name: str) -> werkzeug.wrappers.Response:
    mdb = get_mdb()

    collection_id = cast(int, mdb.get_collection_id_from_name(collection_name))
    mdb.delete_tag('collection', collection_id)

    return redirect(url_for('main.show_entries'))


# code for file uploading taken from:
# http://flask.pocoo.org/docs/1.0/patterns/fileuploads/ and
# https://stackoverflow.com/questions/50069199/send-file-with-flask-and-return-a-data-without-refreshing-the-html-page
# https://stackoverflow.com/questions/32724971/jquery-file-upload-without-redirect
def allowed_thumb_ext(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_THUMB_EXTENSIONS


@main_bp.route('/book/<int:book_id>/upload_cover', methods=['POST'])
def upload_cover(book_id):
    # check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file data received!"})
    file_data = request.files['file']
    # if user does not select file, browser also
    # submit an empty part without filename
    if file_data.filename == '':
        return jsonify({"error": "No file selected!"})
    if file_data and allowed_thumb_ext(file_data.filename):
        from PIL import Image
        # file_data is only the wrapper (werkzeug.FileStorag) open actual file with .stream
        # (SpooledTemporaryFile)
        img = Image.open(file_data.stream)
        # convert to thumbnail (in-place) tuple is max size, keeps apsect ratio
        img.thumbnail((400, 600))
        # when saving without extension we need to pass format kwarg
        img.save(os.path.join(current_app.config['THUMBS_FOLDER'], "temp_cover_0"),
                 format=img.format)
        img.close()
        file_data.close()
        # this needs to be temp_cover without _0 since we don't use a cover_timestamp
        # for the temp_cover and thumb_static will automatically append _0 if none is supplied
        return jsonify({'cover_path': url_for('main.thumb_static', filename="temp_cover")})
    else:
        return jsonify({"error": "Wrong extension for thumb!"})


@main_bp.route('/book/<int:book_id>/remove', methods=("POST",))
def remove_book(book_id):
    book = get_mdb().get_book(book_id)
    book.remove()
    flash(f"Book '{book.title}' was removed from MangaDB!")
    return redirect(url_for('main.show_entries'))


@main_bp.route('/book/<int:book_id>/ext_info/<int:ext_info_id>/remove', methods=("POST",))
def remove_ext_info(book_id, ext_info_id):
    book = get_mdb().get_book(book_id)
    url = book.remove_ext_info(ext_info_id)
    if url is None:
        flash(f"External link with id {ext_info_id} wasnt found on book!")
    else:
        flash(f"External link with url '{url}' was removed from Book!")
    return redirect(url_for("main.show_info", book_id=book_id))


tag_abbrev_to_table_name = {
    't': 'Tag',
    'l': 'List',
    'co': 'Collection',
    'ca': 'Category',
    'g': 'Groups',
    'a': 'Artist',
    'p': 'Parody',
    'ch': 'Character',
}


@main_bp.route('/manage-tags', methods=['GET', 'POST'])
def manage_tags():
    try:
        tags_type_abbrev = request.args['tag-type']
        search_str = request.args['tag-search']
    except KeyError:
        # no search yet
        return render_template('manage_tags.html')

    try:
        tag_tbl_name = tag_abbrev_to_table_name[tags_type_abbrev]
    except KeyError:
        flash("Got invalid value for tag type abbreviation", "title warning")
        return render_template('manage_tags.html')

    mdb = get_mdb()
    c = mdb.db_con.execute(
        f"SELECT id, name FROM {tag_tbl_name} WHERE name LIKE '%{search_str}%'")
    tags = c.fetchall()

    return render_template(
        'manage_tags.html',
        tags=tags,
        tt_abbr=tags_type_abbrev,
        tags_search_field=search_str,
        tags_type=tag_tbl_name.rstrip('s'))


@main_bp.route("/manage-tags/delete", methods=["POST"])
def delete_tag():
    tag_id = request.form.get("id", None, type=int)
    tag_type = request.form.get("type", None, type=str)
    if tag_id is None:
        return jsonify({"error": "Missing tag id from data!"})
    if tag_type is None:
        return jsonify({"error": "Missing tag type from data!"})

    col_name = tag_abbrev_to_table_name[tag_type].lower()
    mdb = get_mdb()
    mdb.delete_tag(col_name, tag_id)

    return jsonify({"success": True})


@main_bp.route("/manage-tags/edit", methods=["POST"])
def edit_tag():
    tag_id = request.form.get("id", None, type=int)
    tag_type = request.form.get("type", None, type=str)
    new_tag_name = request.form.get("new_tag_name", None, type=str)
    if tag_id is None:
        return jsonify({"error": "Missing tag id from data!"})
    if tag_type is None:
        return jsonify({"error": "Missing tag type from data!"})
    if new_tag_name is None:
        return jsonify({"error": "Missing new_tag_name from data!"})

    col_name = tag_abbrev_to_table_name[tag_type].lower()
    mdb = get_mdb()
    if mdb.update_tag_name(col_name, tag_id, new_tag_name.strip()):
        return jsonify({"success": True, "new_tag_name": new_tag_name})
    else:
        return jsonify({"error": f"Name {new_tag_name} already exists!", "dupe": True})


# dummy to pass when our original object would be None
# but the jinja2 template accesses it using the dot operator
class DummyObj:
    def __getattr__(self, key):
        return None
