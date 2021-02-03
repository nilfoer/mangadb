import sys
import os
import time

from flask import Flask

from ..manga_db import update_cookies_from_file

from .webGUI import main_bp
from .csrf import init_app as csrf_init_app
from .auth import auth_bp, init_app as auth_init_app


def create_app(instance_path=None, test_config=None, **kwargs):
    # create and configure the app
    # configuration files are relative to the instance folder. The instance folder is located
    # outside the flaskr package and can hold local data that shouldn’t be committed to version
    # control, such as configuration secrets and the database file
    # default is app.root_path
    # we can define instance_path here as kwarg, default is instance (must be abspath)
    # -> so project_root/instance will be the instance folder depending on un/installed
    # module/package

    # instance_path='/../' Please keep in mind that this path must be absolute when provided.
    # If the instance_path parameter is not provided the following default locations are used:
    # Uninstalled module:
    # /myapp.py
    # /instance
    # Uninstalled package:
    # /myapp
    #     /__init__.py
    # /instance
    # Installed module or package:
    # $PREFIX/lib/python2.X/site-packages/myapp
    # $PREFIX/var/myapp-instance
    # $PREFIX is the prefix of your Python installation. This can be /usr or
    # the path to your virtualenv. You can print the value of sys.prefix to see
    # what the prefix is set to.
    # here using pyinstaller: sinlge_folder_dist\var\manga_db.webGUI-instance
    # NOTE: ^ would not work with single_exe since it is unpacked into a temp dir
    # that gets deleted after the program exits
    # sys._MEIPASS is the abspath to the single folder the generated exe is in
    # or it points to the temp folder where the embedded contents of the
    # exe were unpacked to (will be deleted when process is killed)
    # => better to use sys.argv[0] or sys.executable
    # When a normal Python script runs, sys.executable is the path to the
    # program that was executed, namely, the Python interpreter.
    # in frozen app:
    # sys.executable = (abs?)path to bootloader in either the one-file app or
    #                  the executable in the one-folder app.
    # sys.argv[0] = name or relative path that was used in the user’s command
    # sys.argv[0]: manga_db\MangaDB.exe
    # sys.executable: D:\SYNC\coding\tsu-info\dist\manga_db\MangaDB.exe
    # If the user launches the app by way of a symbolic link, sys.argv[0] uses
    # that symbolic name, while sys.executable is the actual path to the
    # executable. Sometimes the same app is linked under different names and is
    # expected to behave differently depending on the name that is used to
    # launch it. For this case, you would test os.path.basename(sys.argv[0])
    #
    # On the other hand, sometimes the user is told to store the executable in
    # the same folder as the files it will operate on, for example a music
    # player that should be stored in the same folder as the audio files it
    # will play. For this case, you would use os.path.dirname(sys.executable).
    if instance_path is not None:
        app = Flask(__name__, instance_path=instance_path,
                    instance_relative_config=True, **kwargs)
    elif getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        exe_dir = os.path.abspath(os.path.dirname(sys.executable))
        app = Flask(__name__,
                    instance_path=os.path.join(exe_dir, "instance"),
                    instance_relative_config=True, **kwargs)
    else:
        app = Flask(__name__, instance_relative_config=True, **kwargs)

    # here root_path == N:\coding\tsu-info\manga_db\webGUI
    # instance_path == N:\coding\tsu-info\instance (auto-generated for non-installed module)
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

    if test_config is None:
        # load the instance config (from instance folder since instance_relative.. is True),
        # if it exists, when not testing
        # The configuration file uses INI file syntax – name/value pairs in a plain text file,
        # separated by an equal sign =
        # TESTING=False
        # DEBUG=True
        try:
            # turn on silent (no exc when file isn't found) to activate dev key
            app.config.from_pyfile('config.py', silent=False)
        except FileNotFoundError:
            # generate safe key for users
            safe_key = os.urandom(24)
            with open(os.path.join(app.instance_path, 'config.py'), 'w', encoding='utf-8') as f:
                f.write(f"SECRET_KEY = {repr(safe_key)}")
            app.config['SECRET_KEY'] = safe_key
    else:
        # load the test config if passed in
        # test_config can also be passed to the factory, and will be used instead of the instance
        # configuration. This is so the tests you’ll write later in the tutorial can be configured
        # independently of any development values you have configured
        app.config.from_mapping(test_config)

    # add utility for jinja templates to get a timestamp
    def time_str():
        return str(time.time())
    app.jinja_env.globals['time_str'] = time_str

    csrf_init_app(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    auth_init_app(app)

    # reload cookies.txt on startup
    update_cookies_from_file(os.path.join(app.instance_path, 'cookies.txt'))

    return app
