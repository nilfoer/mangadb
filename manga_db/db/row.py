class DBRow:

    # tuple of all column names
    DB_COL_HELPER = ()

    # attributes in class of rows that can be associated to this type of row using bridge tables
    JOINED_COLUMNS = ()

    def __init__(self, manga_db, data, **kwargs):
        self.manga_db = manga_db
        # !!! assign None to all your columns as instance attributes !!!
        # !!! before calling super().__init__ when inheriting from this class !!!
        if isinstance(data, dict):
            self._from_dict(data)
        else:
            self._from_row(data)
        # so we can pass e.g. tag-list that isnt included in slite3.Row as kwarg
        for k, v in kwargs.items():
            setattr(self, k, v)

    def _from_dict(self, dic):
        # only update fields that are in cls.get_column_names()
        self.__dict__.update(self.filter_dict(dic))

    def _from_row(self, row):
        for key in self.DB_COL_HELPER:
            setattr(self, key, row[key])

    @classmethod
    def get_column_names(cls):
        """
        Returns tuple of strings containing all column names, including the ones
        that can be attributed to the type of row using e.g. bridge tables
        """
        return cls.DB_COL_HELPER + cls.JOINED_COLUMNS

    @classmethod
    def filter_dict(cls, data):
        """
        Filters out all data fields that are not in cls.get_column_names()
        """
        dic = {}
        for col in cls.get_column_names():
            try:
                dic[col] = data[col]
            except KeyError:
                pass
        return dic

    def export_for_db(self):
        raise NotImplementedError

    def save(self):
        """
        Save changes to DB
        """
        raise NotImplementedError

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"{self.__class__.__name__}({selfdict_str})"
