"""
File: webGUI.py
Description: Creates webGUI for manga_db using flask
"""

import os.path
from flask import (
        Flask, request, redirect, url_for,
        render_template, flash, send_from_directory,
        jsonify, send_file
)

from ..constants import STATUS_IDS
from ..manga_db import MangaDB
from ..manga import MangaDBEntry
from ..ext_info import ExternalInfo
from .. import extractor

LOCAL_DOWNLOAD = "N:\\_archive\\test\\tsu\\to-read\\"


# config logging b4 this line vv
app = Flask(__name__)  # create the application instance :)

# Load default config and override config from an environment variable
app.config.update(
    dict(
        # DATABASE=os.path.join(app.root_path, 'flaskr.db'),
        SECRET_KEY='development key',
        USERNAME='admin',
        PASSWORD='default'))

# blueprint = Blueprint('thumbs', __name__, static_url_path='/thumbs', static_folder='/thumbs')
# app.register_blueprint(blueprint)

mdb = MangaDB(".", "manga_db.sqlite")

# path to thumbs folder
app.config['THUMBS_FOLDER'] = os.path.join(mdb.root_dir, "thumbs")

# create route for thumbs/static data that isnt in static, can be used in template with
# /thumbs/path/filename or with url_for(thumb_static, filename='filename')
# Custom static data
@app.route('/thumbs/<path:filename>')
def thumb_static(filename):
    return send_from_directory(app.config['THUMBS_FOLDER'], filename)


@app.route('/')
def show_entries():
    books = mdb.get_x_books(150)
    return render_template(
        'show_entries.html',
        books=books,
        order_col_libox="id",
        asc_desc="DESC")


def create_list_dict(manga_db, book):
    list_dict = {row[0]: False for row in manga_db.fetch_list_names()}
    list_dict.update({name: True for name in book.list})
    return list_dict


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

    book_upd_changes = kwargs.get("book_upd_changes", None)

    return render_template(
        'show_info.html',
        book=book,
        collections=collections,
        lists=[row["name"] for row in book.get_all_options_for_assoc_column("list")],
        book_upd_changes=book_upd_changes)


@app.route('/import', methods=["GET", "POST"])
def import_book(url=None):
    if url is None:
        if request.method == 'POST':
            url = request.form['ext-url']
        else:
            url = request.args['ext-url']
    bid, book = mdb.import_book(url, lists=[])
    return show_info(book_id=None, book=book)


@app.route('/jump', methods=["GET", "POST"])
def jump_to_book_by_url():
    if request.method == 'POST':
        url = request.form['ext-url']
    else:
        url = request.args['ext-url']

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

        return render_template(
            'show_entries.html',
            books=books,
            order_col_libox="id",
            asc_desc="DESC")
    else:
        return show_info(book_id=None, book=books[0])


@app.route('/book/<int:book_id>/ext_info/<int:ext_info_id>/update', methods=["GET"])
def update_book_ext_info(book_id, ext_info_id):
    old_book = mdb.get_book(book_id)
    # could also pass in url using post or get
    old_ext_info = [ei for ei in old_book.ext_infos if ei.id == ext_info_id][0]
    new_book, _ = mdb.retrieve_book_data(old_ext_info.url, [])
    changes, _ = old_book.diff(new_book)
    # filter changes and convert to jinja friendlier format
    changes = {key: changes[key] for key in changes if key not in {"id", "last_change",
                                                                   "note", "title"}}
    converted = {"normal": {col: changes[col] for col in changes
                            if col in MangaDBEntry.DB_COL_HELPER},
                 "added_removed": {col: changes[col] for col in changes
                                   if col in MangaDBEntry.JOINED_COLUMNS}
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

    ext_info = new_book.ext_infos[0]
    ext_info.id = ext_info_id
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
    assoc_changes = {}
    for col, val in request.form.items():
        if col == "status":
            update_dic["status_id"] = STATUS_IDS[val]
        elif col == "language":
            update_dic["language_id"] = mdb.get_language(val)
        elif col in MangaDBEntry.DB_COL_HELPER:
            update_dic[col] = val
        else:
            add, remove = val.split(";;;")
            # if we dont check for empty string we get set {''}
            # and it will get added as tag
            add = add.split(";") if add else []
            remove = remove.split(";") if remove else []
            assoc_changes[col] = (set(add), set(remove))

    book.update_from_dict(update_dic)
    book.update_changes_dict(assoc_changes)
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


@app.route("/search", methods=["GET", "POST"])
def search_books():
    if request.method == 'POST':
        searchstr = request.form['searchstring']
        order_by_col = request.form['order-by-col']
        asc_desc = "ASC" if request.form['asc-desc'] == "ASC" else "DESC"
    else:
        searchstr = request.args['searchstring']
        # prepare defaults so we dont always have to send them when using get
        order_by_col = request.args.get('order-by-col', "id")
        asc_desc = request.args.get('asc-desc', "DESC")

    order_by = f"Books.{order_by_col} {asc_desc}"
    books = mdb.search(searchstr, order_by=order_by)

    return render_template(
        "show_entries.html",
        books=books,
        search_field=searchstr,
        order_col_libox=order_by_col,
        asc_desc=asc_desc)


# function that accepts ajax request so we can add lists on show_info
# without reloading the page or going to edit
# WARNING vulnerable to cross-site requests
# TODO add token
@app.route("/book/<int:book_id>/list/<action>", methods=["POST"])
def list_action_ajax(book_id, action):
    list_name = request.form.get("name", None)
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
        MangaDBEntry.add_assoc_col_on_book_id(mdb.db_con, book_id, "list", [list_name])
        # pass url back to script since we cant use url_for
        return jsonify({"added": list_name,
                        "search_tag_url": url_for('search_books',
                                                  searchstring=f'tags:"{list_name}"')})
    elif action == "remove":
        MangaDBEntry.remove_assoc_col_on_book_id(mdb.db_con, book_id, "list", [list_name])
        # pass url back to script since we cant use url_for
        return jsonify({"removed": list_name})
    else:
        flash(f"Supplied action '{action}' is not a valid list action!", "warning")
        return redirect(url_for("show_info", book_id=book_id))


@app.route("/book/<int:book_id>/set/fav/<int:fav_intbool>")
def set_favorite(book_id, fav_intbool):
    MangaDBEntry.set_favorite_id(mdb.db_con, book_id, fav_intbool)
    return redirect(
        url_for("show_info", book_id=book_id))


@app.route("/book/<book_id>/rate/<float:rating>")
def rate_book(book_id, rating):
    MangaDBEntry.rate_book_id(mdb.db_con, book_id, rating)
    return redirect(
        url_for("show_info", book_id=book_id))


@app.route("/book/<book_id>/ext_info/<int:ext_info_id>/set/downloaded/<int:intbool>",
           methods=["GET"])
def set_downloaded(book_id, ext_info_id, intbool):
    ExternalInfo.set_downloaded_id(mdb.db_con, ext_info_id, intbool)
    return redirect(
        url_for("show_info", book_id=book_id))


@app.route("/book/edit/<int:book_id>")
def show_edit_book(book_id, book=None):
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
    # fine here since i just get the col names in DB_COL_HELPER and JOINED_COLUMNS
    # but have to be careful not to just e.g. iterate over the request.form dict or
    # whatever and execute sql queries with col names substituted in f-string and not
    # through db api params (? and :kwarg), someone could change the name field on
    # an input tag to DELETE FROM Books and all entries could get deleted
    # example: col, tag: ('SELECT * FROM Books', 'French Kissing') -> would in my case
    # even if it got inserted still just produce an error
    # esp combination with executescript is dangerous since you can use ; to start
    # another statement ...;DROP Table
    for col in MangaDBEntry.DB_COL_HELPER:
        val = request.form.get(col, None)
        if col in ("pages", "status_id", "language_id"):
            try:
                val = int(val)
            except ValueError:
                app.logger.warning("Couldnt convert value '%s' to int for column '%s'",
                                   val, col)
                flash(f"{col} needs to be a number!", "info")
                return redirect(url_for("show_edit_book", book_id=book_id))
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
    for col in MangaDBEntry.JOINED_COLUMNS:
        val_list = request.form.getlist(col)
        update_dic[col] = val_list

    book.update_from_dict(update_dic)
    book.save()

    # @Speed could also pass book to show_info directly, but by getting book from db
    # again we can see if changes applied correctly?
    return redirect(url_for("show_info", book_id=book_id))


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
    flash(f"External link with url '{url}' was removed from Book!")
    return show_info(book_id=book_id, book=book)


def main():
    app.run()


if __name__ == "__main__":
    main()
