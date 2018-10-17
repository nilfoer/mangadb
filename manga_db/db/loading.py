

def load_instance(manga_db, cls, row):
    id_map = manga_db.id_map
    key = build_key_dictlike(cls, row)
    instance = id_map.get(key, None)
    if instance is not None:
        return instance
    else:
        instance = cls(manga_db, row)



def build_key(obj):
    return (obj.__class__, tuple((getattr(obj, col) for col in obj.PRIMARY_KEY_COL)))


def build_key_dictlike(cls, dictlike):
    return (cls.__class__, tuple((dictlike[col] for col in cls.PRIMARY_KEY_COL)))
