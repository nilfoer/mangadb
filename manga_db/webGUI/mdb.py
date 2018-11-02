import threading

from flask import current_app

from ..manga_db import MangaDB


# Thread-local data is data whose values are thread specific. To manage thread-local data, just #
# create an instance of local (or a subclass) and store attributes on it
# t_local = threading.local()
# we get AttributeError: '_thread._local' object has no attribute 'mdb' if we didnt assign attr yet
# and it needs to be assigned for every thread separately -> better to subclass threading.local
class app_thread_data(threading.local):
    def __init__(self):
        super().__init__()
        self.mdb_init = False


t_local = app_thread_data()


def get_mdb():
    if not t_local.mdb_init:
        # cant store in app.config since thread specific and app config isnt
        t_local.mdb = MangaDB(current_app.instance_path, current_app.config["DATABASE_PATH"])
        t_local.mdb_init = True
    return t_local.mdb
