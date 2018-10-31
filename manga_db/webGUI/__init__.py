import os
import logging

from flask import Flask, g, current_app
from ..manga_db import MangaDB

from .auth import auth_bp, load_admin_credentials


def get_mdb():
    if 'mdb' not in g:
        current_app.logger.info("Opening DB")
        g.mdb = MangaDB(current_app.instance_path, current_app.config["DATABASE_PATH"])

    current_app.logger.info("Getting DB %d", id(g.mdb))
    return g.mdb


def close_mdb(e=None):
    mdb = g.pop('mdb', None)

    if mdb is not None:
        mdb.close()


def create_app(test_config=None):
    # When you want to configure logging for your project, you should do it as soon as
    # possible when the program starts. If app.logger is accessed before logging is configured,
    # it will add a default handler. If possible, configure logging before creating the
    # application object.
    logging.config.dictConfig({
        'version': 1,
        'formatters': {'default': {
            'format': '[%(asctime)s] %(levelname)s on (%(threadName)-10s) in %(module)s: %(message)s',
        }},
        'handlers': {'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
        }},
        'root': {
            'level': 'INFO',
            'handlers': ['wsgi']
        }
    })
    # create and configure the app
    # configuration files are relative to the instance folder. The instance folder is located
    # outside the flaskr package and can hold local data that shouldn’t be committed to version
    # control, such as configuration secrets and the database file
    # default is app.root_path
    # we can define instance_path here as kwarg, default is instance
    # -> so project_root/instance will be the instance folder depending on un/installed
    # module/package
    app = Flask(__name__, instance_relative_config=True)
    # here root_path == N:\coding\tsu-info\manga_db\webGUI
    # instance_path == N:\coding\tsu-info\instance
    app.config.from_mapping(
        # unsafe key for dev purposes otherwise use tru random bytes like:
        # python -c "import os; print(os.urandom(24))"
        SECRET_KEY='mangadb dev',
        DATABASE_PATH=os.path.join(app.instance_path, 'manga_db.sqlite'),
        # path to thumbs folder
        THUMBS_FOLDER=os.path.join(app.instance_path, "thumbs"),
        # limit upload size to 0,5MB
        MAX_CONTENT_LENGTH=0.5 * 1024 * 1024
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        # test_config can also be passed to the factory, and will be used instead of the instance
        # configuration. This is so the tests you’ll write later in the tutorial can be configured
        # independently of any development values you have configured
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    # ensure the instance thumbs folder exists
    try:
        os.makedirs(app.config["THUMBS_FOLDER"])
    except OSError:
        pass


    app.logger.info("Creating app")
    app.register_blueprint(auth_bp)
    load_admin_credentials(app)

    @app.route("/")
    def index():
        mdb = get_mdb()
        b = mdb.get_book(5)
        return b.title

    return app
