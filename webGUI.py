import os
import sqlite3

from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, Blueprint, send_from_directory

from manga_db import load_or_create_sql_db, search_tags_string_parse, get_tags_by_book_id_onpage, \
        add_tags_to_book, remove_tags_from_book_id, lists, get_tags_by_book_id_internal, \
        book_id_from_url, add_book, update_book

app = Flask(__name__) # create the application instance :)

# Load default config and override config from an environment variable
app.config.update(dict(
    #DATABASE=os.path.join(app.root_path, 'flaskr.db'),
    SECRET_KEY='development key',
    USERNAME='admin',
    PASSWORD='default'
))
# path to thumbs folder
app.config['THUMBS_FOLDER'] = "thumbs"

# blueprint = Blueprint('thumbs', __name__, static_url_path='/thumbs', static_folder='/thumbs')
# app.register_blueprint(blueprint)

db_con, _ = load_or_create_sql_db("manga_db.sqlite")
db_con.row_factory = sqlite3.Row

# create route for thumbs/static data that isnt in static, can be used in template with /thumbs/path/filename or with url_for(thumb_static, filename='filename')
# Custom static data
@app.route('/thumbs/<path:filename>')
def thumb_static(filename):
    return send_from_directory(app.config['THUMBS_FOLDER'], filename)


@app.route('/')
def show_entries():
    cur = db_con.execute('select * from Tsumino order by id desc')
    entries = cur.fetchall()
    return render_template('show_entries.html', entries=entries)


lists_dic = {li: None for li in lists}
# int:blabla -> means var blabla has to be of type int
@app.route('/book/<int:book_id_internal>')
def show_book_info(book_id_internal):
    lists_all = lists_dic.copy()

    cur = db_con.execute('select * from Tsumino WHERE id = ?', (book_id_internal,))
    book_info = cur.fetchone()
    tags = get_tags_by_book_id_internal(db_con, book_id_internal).split(",")
    # split tags and lists
    lists_book = {tag: True for tag in tags if tag.startswith("li_")}
    # upd dic with all lists with lists that are set on this book
    lists_all.update(lists_book)
    lists_book = lists_all
    favorite = lists_book["li_best"]

    tags = [tag for tag in tags if not tag.startswith("li_")]

    return render_template('show_book_info.html', book_info=book_info, tags=tags,
            favorite=favorite, lists_book=lists_book)


# access to book with id_onpage seperate so theres no conflict if we support more than 1 site
@app.route('/tsubook/<book_id_onpage>')
def show_tsubook_info(book_id_onpage):
    lists_all = lists_dic.copy()

    cur = db_con.execute('select * from Tsumino WHERE id_onpage = ?', (book_id_onpage,))
    book_info = cur.fetchone()
    tags = get_tags_by_book_id_onpage(db_con, book_id_onpage).split(",")
    # split tags and lists
    lists_book = {tag: True for tag in tags if tag.startswith("li_")}
    # upd dic with all lists with lists that are set on this book
    lists_all.update(lists_book)
    lists_book = lists_all
    favorite = lists_book["li_best"]

    tags = [tag for tag in tags if not tag.startswith("li_")]

    return render_template('show_book_info.html', book_info=book_info, tags=tags,
            favorite=favorite, lists_book=lists_book)


@app.route('/jump', methods=["GET", "POST"])
def jump_to_book_by_url():
    if request.method == 'POST':
        url = request.form['jump-to-url']
    else:
        url = request.args['jump-to-url']
    book_id_onpage = book_id_from_url(url)

    return redirect(url_for('show_tsubook_info', book_id_onpage=book_id_onpage))


@app.route('/AddBookFromPage', methods=["POST"])
def add_book_by_url():
    url = request.form["url-to-add"]
    id_internal = add_book(db_con, url, None, write_infotxt=False)
    
    return redirect(url_for('show_book_info', book_id_internal=id_internal))


# mb add /<site>/<id> later when more than 1 site supported
@app.route('/UpdateBookFromPage/<book_id_onpage>', methods=["GET"])
def update_book_by_id_onpage(book_id_onpage):
    # all sites use some kind of id -> stop using long url for tsumino and build url with id_onpage instead
    url = f"http://www.tsumino.com/Book/Info/{book_id_onpage}"
    id_internal = update_book(db_con, url, None, write_infotxt=False)
    
    return redirect(url_for('show_book_info', book_id_internal=id_internal))


@app.route("/search", methods=["GET", "POST"])
def search_books():
    if request.method == 'POST':
        tagstr = request.form['tagstring']
    else:
        tagstr = request.args['tagstring']
    # search_tags_.. functions set row factory of db_con back to None -> pass additional param
    books = search_tags_string_parse(db_con, tagstr, keep_row_fac=True)
    # now setting value of search field when this func was called to show previous search string in search input field -> flash msg not needed
    # flash(f'Showing results for tags: {request.form["tagstring"]}')
    return render_template("show_entries.html", entries=books, search_field=tagstr)


@app.route("/AddFavorite/<book_id_internal>")
def add_book_favorite(book_id_internal):
    with db_con:
        # add_tags_to_book doesnt commit changes
        add_tags_to_book(db_con, book_id_internal, ["li_best"])
    flash("Successfully added Book to Favorites!")
    
    return redirect(url_for("show_book_info", book_id_internal=book_id_internal))


@app.route("/RemoveFavorite/<book_id_internal>")
def remove_book_favorite(book_id_internal):
    with db_con:
        # add_tags_to_book doesnt commit changes
        remove_tags_from_book_id(db_con, book_id_internal, ["li_best"])
    flash("Successfully removed Book from Favorites!")
    
    return redirect(url_for("show_book_info", book_id_internal=book_id_internal))



@app.route("/RateBook/<book_id_internal>", methods=["GET"])
def rate_book_internal(book_id_internal):
    with db_con:
        db_con.execute("UPDATE Tsumino SET my_rating = ? WHERE id = ?", (request.args['rating'], book_id_internal))
    
    return redirect(url_for("show_book_info", book_id_internal=book_id_internal))


@app.route("/SetLists", methods=["POST"])
def set_lists_book():
    book_id_internal = request.form["book_id_internal"]
    
    lists_book_prev = get_tags_by_book_id_internal(db_con, book_id_internal).split(",")
    # convert to set for diff operation later
    lists_book_prev = set((tag for tag in lists_book_prev if tag.startswith("li_")))

    # requests.form -> Dict[('book_id_internal', '25'), ('li_to-read', 'on'), ('li_downloaded', 'on'), ('li_best', 'on')]
    # all checked lists (from page) are present as keys in request.form
    # if list also is in lists_book_prev -> list tag already set -> dont need to set it
    lists_checked = set((k for k in request.form.keys() if k.startswith("li_")))

    # s.difference(t) 	s - t (-> s-t only works if both sets)
    lists_to_remove = lists_book_prev - lists_checked
    lists_to_add = lists_checked - lists_book_prev

    with db_con:
        add_tags_to_book(db_con, book_id_internal, lists_to_add)
        remove_tags_from_book_id(db_con, book_id_internal, lists_to_remove)

    flash(f"Successfully added these lists: {', '.join(lists_to_add) if lists_to_add else 'None'}. The following lists were removed: {', '.join(lists_to_remove) if lists_to_remove else 'None'}.")

    return redirect(url_for("show_book_info", book_id_internal=book_id_internal))


if __name__ == "__main__":
    app.run()
