"""
File: webGUI.py
Description: Creates webGUI for manga_db using flask
"""

import os.path
from flask import Flask, request, redirect, url_for, render_template, flash, send_from_directory

from ..constants import STATUS_IDS
from ..manga_db import MangaDB
from ..manga import MangaDBEntry
from ..ext_info import ExternalInfo
from .. import extractor
from ..db.search import search_sytnax_parser
#from tsu_info_getter import write_inf_txt

LOCAL_DOWNLOAD = "N:\\_archive\\test\\tsu\\to-read\\"



# config logging b4 this line vv
app = Flask(__name__)  # create the application instance :)

# Load default config and override config from an environment variable
app.config.update(
    dict(
        #DATABASE=os.path.join(app.root_path, 'flaskr.db'),
        SECRET_KEY='development key',
        USERNAME='admin',
        PASSWORD='default'))

# blueprint = Blueprint('thumbs', __name__, static_url_path='/thumbs', static_folder='/thumbs')
# app.register_blueprint(blueprint)

mdb = MangaDB(".", "manga_db.sqlite")
db_con = mdb.db_con

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
def show_info(book_id, book=None):
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

    return render_template(
        'show_info.html',
        book=book,
        collections=collections)


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
        return render_template("choose_book.html", books=books)
    else:
        return show_info(book_id=None, book=books[0])


@app.route('/book/<int:book_id>/ext_info/<int:ext_info_id>/update', methods=["GET"])
def update_book_ext_info(book_id, ext_info_id):
    # all sites use some kind of id -> stop using long url for tsumino and build url with
    # id_onpage instead
    url = f"http://www.tsumino.com/Book/Info/{book_id_onpage}"
    id_internal, field_change_str = update_book(
        db_con, url, None, write_infotxt=False)
    if field_change_str:
        flash(
            "WARNING - Please re-download this Book, since the change of following fields "
            "suggest that someone has uploaded a new version:"
        )
        flash(field_change_str)
    if id_internal is None:
        flash("WARNING - Connection problem or book wasnt found on page!!!")

    return redirect(
        url_for('show_info', book_id=book_id_onpage))


INFOTXT_ORDER_HELPER = (("title", "Title"), ("uploader", "Uploader"),
                        ("upload_date", "Uploaded"), ("pages", "Pages"),
                        ("rating_full", "Rating"), ("category", "Category"),
                        ("collection", "Collection"), ("groups", "Group"),
                        ("artist", "Artist"), ("parody", "Parody"),
                        ("character", "Character"), ("tag", "Tag"),
                        ("url", "URL"))
@app.route('/WriteInfoTxt/<book_id>', methods=["GET"])
def write_info_txt_by_id(book_id):
    cur = db_con.execute('select * from Books WHERE id = ?',
                         (book_id, ))
    book_info = cur.fetchone()
    tags = get_tags_by_book_id_internal(db_con, book_id).split(",")
    tags = ", ".join(
        (tag for tag in sorted(tags) if not tag.startswith("li_")))

    info_str = []
    for key, title in INFOTXT_ORDER_HELPER:
        if key == "tag":
            info_str.append(f"Tag: {tags}")
        else:
            val = book_info[key]
            if val is None:
                continue
            elif isinstance(val, str):
                val = val.replace(',', ', ')
            info_str.append(f"{title}: {val}")

    write_inf_txt("\n".join(info_str), book_info["title"], path=LOCAL_DOWNLOAD)

    return redirect(
        url_for('show_info', book_id=book_id))


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
    books = search_sytnax_parser(
        db_con, searchstr, order_by=order_by, keep_row_fac=True)

    return render_template(
        "show_entries.html",
        entries=books,
        search_field=searchstr,
        order_col_libox=order_by_col,
        asc_desc=asc_desc)


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
    for col in MangaDBEntry.DB_COL_HELPER:
        val = request.form.get(col, None)
        if col in ("pages", "status_id", "language_id"):
            try:
                val = int(val)
            except ValueError:
                app.logger.warning("Couldnt convert value '%s' to int for column '%s'",
                                   val, col)
                flash(f"{col} needs to be a number!")
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
                flash(f"{col} needs to be a floating point number!")
                return redirect(url_for("show_edit_book", book_id=book_id))
        update_dic[col] = val
    for col in MangaDBEntry.JOINED_COLUMNS:
        val_list = request.form.getlist(col)
        update_dic[col] = val_list

    book.update_from_dict(update_dic)
    book.save()

    return redirect(url_for("show_info", book_id=book_id))


def main():
    app.run()


if __name__ == "__main__":
    main()
