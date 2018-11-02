import os
import secrets

from flask import (
        Flask, session, request, Markup,
        abort
        )

from .webGUI import main_bp
from .auth import auth_bp, init_app as auth_init_app


def init_csrf_token_checking(app):
    @app.before_request
    def validate_csrf_token():
        # decorator @main_bp.before_request to execute this b4 every req
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
            # As of 2015, it is believed that 32 bytes (256 bits) of randomness is sufficient for
            # the typical use-case expected for the secrets module
            session['_csrf_token'] = secrets.token_urlsafe(32)
        return session['_csrf_token']

    def generate_csrf_token_field():
        token = generate_csrf_token()
        return Markup(f"<input type='hidden' name='_csrf_token' value='{token}' />")

    # register func to gen token field so we can us it in template
    app.jinja_env.globals['csrf_token_field'] = generate_csrf_token_field
    app.jinja_env.globals['csrf_token'] = generate_csrf_token


def create_app(test_config=None, **kwargs):
    # create and configure the app
    # configuration files are relative to the instance folder. The instance folder is located
    # outside the flaskr package and can hold local data that shouldn’t be committed to version
    # control, such as configuration secrets and the database file
    # default is app.root_path
    # we can define instance_path here as kwarg, default is instance (must be abspath)
    # -> so project_root/instance will be the instance folder depending on un/installed
    # module/package
    app = Flask(__name__, instance_relative_config=True, **kwargs)
    # here root_path == N:\coding\tsu-info\manga_db\webGUI
    # instance_path == N:\coding\tsu-info\instance
    app.config.from_mapping(
        # unsafe key for dev purposes otherwise use true random bytes like:
        # python -c "import os; print(os.urandom(24))"
        SECRET_KEY='mangadb dev',
        DATABASE_PATH=os.path.join(app.instance_path, 'manga_db.sqlite'),
        # path to thumbs folder
        THUMBS_FOLDER=os.path.join(app.instance_path, "thumbs"),
        # limit upload size to 0,5MB
        MAX_CONTENT_LENGTH=0.5 * 1024 * 1024
    )

    if test_config is None:
        # load the instance config (from instance folder since instance_relative.. is True),
        # if it exists, when not testing
        # The configuration file uses INI file syntax – name/value pairs in a plain text file,
        # separated by an equal sign =
        # TESTING=False
        # DEBUG=True
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
    init_csrf_token_checking(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    auth_init_app(app)

    return app
