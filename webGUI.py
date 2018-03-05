import os
import sqlite3

from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, Blueprint, send_from_directory

from manga_db import load_or_create_sql_db, search_tags_string_parse, get_tags_by_book_id_onpage, \
        add_tags_to_book, remove_tags_from_book_id

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


@app.route('/book/<book_id_internal>')
def show_book_info(book_id_internal):
    cur = db_con.execute('select * from Tsumino WHERE id = ?', (book_id_internal,))
    book_info = cur.fetchone()
    tags = get_tags_by_book_id_onpage(db_con, book_info['id_onpage'])
    favorite = "li_best" in tags

    return render_template('show_book_info.html', book_info=book_info, tags=tags,
            favorite=favorite)


# access to book with id_onpage seperate so theres no conflict if we support more than 1 site
@app.route('/tsubook/<book_id_onpage>')
def show_tsubook_info(book_id_onpage):
    cur = db_con.execute('select * from Tsumino WHERE id_onpage = ?', (book_id_onpage,))
    book_info = cur.fetchone()
    tags = get_tags_by_book_id_onpage(db_con, book_id_onpage)
    favorite = "li_best" in tags

    return render_template('show_tsubook_info.html', book_info=book_info, tags=tags,
            favorite=favorite)


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


if __name__ == "__main__":
    app.run()
