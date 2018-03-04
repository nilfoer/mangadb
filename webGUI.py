import os
import sqlite3

from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, Blueprint, send_from_directory

from manga_db import load_or_create_sql_db, search_tags_string_parse, get_tags_by_book_id_onpage

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


@app.route('/book/<book_id_onpage>')
def show_book_info(book_id_onpage):
    cur = db_con.execute('select * from Tsumino WHERE id_onpage = ?', (book_id_onpage,))
    book_info = cur.fetchone()
    tags = get_tags_by_book_id_onpage(db_con, book_id_onpage)
    favorite = "li_best" in tags

    return render_template('show_book_info.html', book_info=book_info, tags=tags,
            favorite=favorite)


@app.route('/add', methods=['POST'])
def add_entry():
    #db.execute('insert into entries (title, text) values (?, ?)',
    #             [request.form['title'], request.form['text']])
    #db.commit()
    flash(f'New entry was successfully posted with: {request.form["title"]}')
    return redirect(url_for('show_entries'))

@app.route("/search", methods=["POST"])
def search_books():
    # search_tags_.. functions set row factory of db_con back to None -> pass additional param
    books = search_tags_string_parse(db_con, request.form['tagstring'], keep_row_fac=True)
    # now setting value of search field when this func was called to show previous search string in search input field -> flash msg not needed
    # flash(f'Showing results for tags: {request.form["tagstring"]}')
    return render_template("show_entries.html", entries=books, search_field=request.form['tagstring'])

if __name__ == "__main__":
    app.run()
