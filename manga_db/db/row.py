from .constants import ColumnValue


class DBRow:

    TABLENAME = ""

    def __init__(self, manga_db, **kwargs):
        self.manga_db = manga_db
        # commited values get added when col gets modified
        self._committed_state = {}
        # gets set to true when loaded from db through load_instance
        self._in_db = False

    @staticmethod
    def committed_state_callback(instance, col_name, value):
        if col_name not in instance._committed_state:
            before = getattr(instance, col_name)
            if before is not ColumnValue.NO_VALUE:
                instance._committed_state[col_name] = before

    @classmethod
    def from_dict(cls, manga_db, dic):
        # only update fields that are in cls.get_column_names()
        row = cls(manga_db)
        row.__dict__.update(cls.filter_dict(dic))

    @classmethod
    def get_column_names(cls):
        """
        Returns tuple of strings containing all column names, including the ones
        that can be attributed to the type of row using e.g. bridge tables
        primary key columns are not included
        """
        # TODO loop through self vars and add Column/Assoc.. sublcasses
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
        """
        Returns a dict with all the attributes of self that are stored in the row directly
        """
        result = {}
        for attr in self.DB_COL_HELPER:
            val = getattr(self, attr)
            if (attr in self.NOT_NULL_COLS) and val is None:
                raise ValueError(f"'self.{attr}' can't be NULL when exporting for DB!")
            result[attr] = val
        return result

    def save(self):
        """
        Save changes to DB
        """
        raise NotImplementedError

    def diff_normal_cols(self, row):
        changed_str = []
        changed_cols = []
        for col in self.DB_COL_HELPER:
            self_attr = getattr(self, col)
            if row[col] != self_attr:
                changed_str.append(f"Column '{col}' changed from '{row[col]}' to '{self_attr}'")
                changed_cols.append(col)
        return "\n".join(changed_str), changed_cols

    def __repr__(self):
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"{self.__class__.__name__}({selfdict_str})"
