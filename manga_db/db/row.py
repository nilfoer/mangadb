from typing import List, Dict, Any, Tuple, Mapping


class DBRow:

    TABLENAME = ""

    PRIMARY_KEY_COLUMNS: List[str]
    # cant assign [] here otherwise col names of all subclasses will be appended to same list
    COLUMNS: List[str]
    ASSOCIATED_COLUMNS: List[str]

    def __init__(self, manga_db, in_db, **kwargs):
        self.manga_db = manga_db
        # commited values get added when col gets modified
        self._committed_state = {}
        # defaul false, true when loaded from db through load_instance
        # get_book_id can return an id but still doesnt mean that the book is in db
        # it might just have the same title as the book whose id was returned
        self._in_db = in_db

    @property
    def key(self):
        return self.__class__, tuple((getattr(self, col) for col in self.PRIMARY_KEY_COLUMNS))

    @classmethod
    def get_all_column_names(cls) -> List[str]:
        """
        Returns list of strings containing all column names
        """
        return cls.COLUMNS + cls.ASSOCIATED_COLUMNS

    @classmethod
    def filter_dict(cls, data: Dict) -> Dict:
        """
        Filters out all data fields that are not in our columns
        """
        dic = {}
        for col in cls.get_all_column_names():
            try:
                dic[col] = data[col]
            except KeyError:
                pass
        return dic

    def export_for_db(self) -> Dict[str, Any]:
        """
        Returns a dict with all the attributes of self that are stored in the row directly
        """
        result: Dict[str, Any] = {}
        for attr in self.COLUMNS + self.PRIMARY_KEY_COLUMNS:
            val = getattr(self, attr)
            result[attr] = val
        return result

    def save(self):
        """
        Save changes to DB
        """
        raise NotImplementedError

    def diff_normal_cols(self, row: Mapping[str, Any]) -> Tuple[str, List[str]]:
        changed_str = []
        changed_cols = []
        for col in self.COLUMNS:
            self_attr = getattr(self, col)
            if row[col] != self_attr:
                changed_str.append(f"Column '{col}' changed from '{row[col]}' to '{self_attr}'")
                changed_cols.append(col)
        return "\n".join(changed_str), changed_cols

    def changed_str(self) -> str:
        return "\n".join([f"{col}: '{val}' changed to '{getattr(self, col)}'" for col, val in
                          self._committed_state.items()])

    def __repr__(self) -> str:
        selfdict_str = ", ".join((f"{attr}: '{val}'" for attr, val in self.__dict__.items()))
        return f"{self.__class__.__name__}({selfdict_str})"
