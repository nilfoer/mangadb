"""
File: webGUI.py
Description: Creates webGUI for manga_db using flask
"""

import sqlite3

from flask import Flask, request, redirect, url_for, render_template, flash, send_from_directory

from manga_db import load_or_create_sql_db, get_tags_by_book, add_tags_to_book, \
        remove_tags_from_book_id, LISTS, get_tags_by_book_id_internal, book_id_from_url, \
        add_book, update_book, get_all_id_onpage_set, search_sytnax_parser
from tsu_info_getter import write_inf_txt

LOCAL_DOWNLOAD = "N:\\_archive\\test\\tsu\\to-read\\"

app = Flask(__name__)  # create the application instance :)

# Load default config and override config from an environment variable
app.config.update(
    dict(
        #DATABASE=os.path.join(app.root_path, 'flaskr.db'),
        SECRET_KEY='development key',
        USERNAME='admin',
        PASSWORD='default'))
# path to thumbs folder
app.config['THUMBS_FOLDER'] = "thumbs"

# blueprint = Blueprint('thumbs', __name__, static_url_path='/thumbs', static_folder='/thumbs')
# app.register_blueprint(blueprint)

db_con, _ = load_or_create_sql_db("manga_db.sqlite")
db_con.row_factory = sqlite3.Row

# set with all id_onpage to check if book is in db without having to query for every check
# -> if later more than one -> dict (key is pagename) of sets
all_book_id_onpage = get_all_id_onpage_set(db_con)


# create route for thumbs/static data that isnt in static, can be used in template with
# /thumbs/path/filename or with url_for(thumb_static, filename='filename')
# Custom static data
@app.route('/thumbs/<path:filename>')
def thumb_static(filename):
    return send_from_directory(app.config['THUMBS_FOLDER'], filename)


@app.route('/')
def show_entries():
    cur = db_con.execute('select * from Tsumino order by id desc')
    entries = cur.fetchall()
    return render_template(
        'show_entries.html',
        entries=entries,
        order_col_libox="id",
        asc_desc="DESC")


LISTS_DIC = {li: None for li in LISTS}
# int:blabla -> means var blabla has to be of type int
@app.route('/book/<string:id_type>/<int:book_id>')
def show_book_info(id_type, book_id):
    lists_all = LISTS_DIC.copy()

    if id_type == "id":
        id_col = "id"
        id_type_db = "id_internal"
    elif id_type == "ext":
        id_col = "id_onpage"
        id_type_db = "id_onpage"
    else:
        # could also use flash(f"ERROR...")
        return render_template(
            'show_book_info.html',
            error_msg=f"ERROR: Unsupported id_type supplied!")

    cur = db_con.execute(f'select * from Tsumino WHERE {id_col} = ?',
                         (book_id, ))
    book_info = cur.fetchone()

    # handle book not being in db yet
    if not book_info:
        return render_template(
            'show_book_info.html',
            error_msg=f"No book with {id_col} {book_id}"
            " was found in DB!")

    tags = get_tags_by_book(db_con, book_id, id_type_db).split(",")
    # split tags and lists
    lists_book = {tag: True for tag in tags if tag.startswith("li_")}
    # upd dic with all lists with lists that are set on this book
    lists_all.update(lists_book)
    lists_book = lists_all
    favorite = lists_book["li_best"]

    tags = [tag for tag in tags if not tag.startswith("li_")]

    return render_template(
        'show_book_info.html',
        book_info=book_info,
        tags=tags,
        favorite=favorite,
        lists_book=lists_book)


@app.route('/jump', methods=["GET", "POST"])
def jump_to_book_by_url():
    if request.method == 'POST':
        url = request.form['jump-to-url']
    else:
        url = request.args['jump-to-url']
    book_id_onpage = book_id_from_url(url)

    # check if book not in db -> add
    if book_id_onpage not in all_book_id_onpage:
        add_book(db_con, url, None, write_infotxt=False)
        # also add book_id_onpage to set of all id_onpage in DB so it represents current state of
        # DB next time we call this func
        all_book_id_onpage.add(book_id_onpage)

    return redirect(
        url_for('show_book_info', id_type="ext", book_id=book_id_onpage))


@app.route("/SetDL/<book_id_internal>", methods=["GET"])
def set_dl(book_id_internal):
    with db_con:
        # add_tags_to_book doesnt commit changes
        add_tags_to_book(db_con, book_id_internal, ["li_downloaded"])
    return redirect(
        url_for("show_book_info", id_type="id", book_id=book_id_internal))


# mb add /<site>/<id> later when more than 1 site supported
@app.route('/UpdateBookFromPage/<book_id_onpage>', methods=["GET"])
def update_book_by_id_onpage(book_id_onpage):
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
        url_for('show_book_info', id_type="ext", book_id=book_id_onpage))


INFOTXT_ORDER_HELPER = (("title", "Title"), ("uploader", "Uploader"),
                        ("upload_date", "Uploaded"), ("pages", "Pages"),
                        ("rating_full", "Rating"), ("category", "Category"),
                        ("collection", "Collection"), ("groups", "Group"),
                        ("artist", "Artist"), ("parody", "Parody"),
                        ("character", "Character"), ("tag", "Tag"),
                        ("url", "URL"))
@app.route('/WriteInfoTxt/<book_id_internal>', methods=["GET"])
def write_info_txt_by_id(book_id_internal):
    cur = db_con.execute('select * from Tsumino WHERE id = ?',
                         (book_id_internal, ))
    book_info = cur.fetchone()
    tags = get_tags_by_book_id_internal(db_con, book_id_internal).split(",")
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
        url_for('show_book_info', id_type="id", book_id=book_id_internal))


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

    order_by = f"Tsumino.{order_by_col} {asc_desc}"
    books = search_sytnax_parser(
        db_con, searchstr, order_by=order_by, keep_row_fac=True)

    return render_template(
        "show_entries.html",
        entries=books,
        search_field=searchstr,
        order_col_libox=order_by_col,
        asc_desc=asc_desc)


@app.route("/AddFavorite/<book_id_internal>")
def add_book_favorite(book_id_internal):
    with db_con:
        # add_tags_to_book doesnt commit changes
        add_tags_to_book(db_con, book_id_internal, ["li_best"])
    flash("Successfully added Book to Favorites!")

    return redirect(
        url_for("show_book_info", id_type="id", book_id=book_id_internal))


@app.route("/RemoveFavorite/<book_id_internal>")
def remove_book_favorite(book_id_internal):
    with db_con:
        # add_tags_to_book doesnt commit changes
        remove_tags_from_book_id(db_con, book_id_internal, ["li_best"])
    flash("Successfully removed Book from Favorites!")

    return redirect(
        url_for("show_book_info", id_type="id", book_id=book_id_internal))


@app.route("/RateBook/<book_id_internal>", methods=["GET"])
def rate_book_internal(book_id_internal):
    with db_con:
        db_con.execute("UPDATE Tsumino SET my_rating = ? WHERE id = ?",
                       (request.args['rating'], book_id_internal))

    return redirect(
        url_for("show_book_info", id_type="id", book_id=book_id_internal))


@app.route("/SetLists", methods=["POST"])
def set_lists_book():
    book_id_internal = request.form["book_id_internal"]

    lists_book_prev = get_tags_by_book_id_internal(db_con,
                                                   book_id_internal).split(",")
    # convert to set for diff operation later
    lists_book_prev = set(
        (tag for tag in lists_book_prev if tag.startswith("li_")))

    # requests.form -> Dict[('book_id_internal', '25'), ('li_to-read', 'on'),
    # ('li_downloaded', 'on'), ('li_best', 'on')]
    # all checked lists (from page) are present as keys in request.form
    # if list also is in lists_book_prev -> list tag already set -> dont need to set it
    lists_checked = set(
        (k for k in request.form.keys() if k.startswith("li_")))

    # s.difference(t) 	s - t (-> s-t only works if both sets)
    lists_to_remove = lists_book_prev - lists_checked
    lists_to_add = lists_checked - lists_book_prev

    with db_con:
        add_tags_to_book(db_con, book_id_internal, lists_to_add)
        remove_tags_from_book_id(db_con, book_id_internal, lists_to_remove)

    flash(
        f"Successfully added these lists: {', '.join(lists_to_add) if lists_to_add else 'None'}. "
        "The following lists were removed: "
        f"{', '.join(lists_to_remove) if lists_to_remove else 'None'}."
    )

    return redirect(
        url_for("show_book_info", id_type="id", book_id=book_id_internal))


if __name__ == "__main__":
    app.run()
