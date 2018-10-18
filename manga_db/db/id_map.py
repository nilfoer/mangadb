import weakref


class IndentityMap:

    def __init__(self):
        # d[key] directly returns acutal object (not weakref)
        # if value gets gc'd key/entry gets autmatically removed from WeakValueDictionary
        # if we retrieved and assigned the obj to a var then it wont be collected by gc anymore
        self._dict = weakref.WeakValueDictionary()

    def add(self, obj):
        if not obj._in_db:
            return False
        else:
            key = obj.key
            if key in self._dict:
                # TODO custom exception
                raise Exception(f"Can't add {key} to IndentityMap, since there is already "
                                "an instance present for this key!")
            else:
                self._dict[key] = obj
                return True

    def remove(self, key):
        del self._dict[key]

    def discard(self, key):
        try:
            self.remove(key)
            return True
        except KeyError:
            return False

    def __getitem__(self, key):
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def get(self, key, default=None):
        try:
            obj = self._dict[key]
            return obj
        except KeyError:
            return default

    def items(self):
        return self._dict.items()

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)
