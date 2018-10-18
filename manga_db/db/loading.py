

def load_instance(manga_db, cls, row, *args, **kwargs):
    id_map = manga_db.id_map
    key = build_key_dictlike(cls, row)
    instance = id_map.get(key, None)
    # when we have lazy loading we have to populate cls instance with parts that havent been loaded
    # yet
    if instance is None:
        instance = cls(manga_db, *args, **row, **kwargs)
        instance._in_db = True
        id_map.add(instance)
    return instance


def build_key_dictlike(cls, dictlike):
    return (cls, tuple((dictlike[col] for col in cls.PRIMARY_KEY_COLUMNS)))
