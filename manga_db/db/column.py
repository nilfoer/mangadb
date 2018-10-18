from weakref import WeakKeyDictionary

from .constants import ColumnValue


# callback that sets the current state as commited state on the instance
# the first time the value is changed after a commit
def committed_state_callback(instance, col_name, value):
    if col_name not in instance._committed_state:
        before = getattr(instance, col_name)
        if before is not ColumnValue.NO_VALUE:
            instance._committed_state[col_name] = before


class Column:

    def __init__(self, value_type, default=None, **kwargs):
        self.type = value_type
        self.default = default
        self.values = WeakKeyDictionary()
        self.primary_key = kwargs.pop("primary_key", False)
        self.nullable = kwargs.pop("nullable", True)

    # new in py3.6: Called at the time the owning class owner is created. The descriptor has been
    # assigned to name
    def __set_name__(self, owner, name):
        if self.primary_key:
            # add pk col separately
            try:
                owner.PRIMARY_KEY_COLUMNS.append(name)
            except AttributeError:
                owner.PRIMARY_KEY_COLUMNS = [name]
        else:
            # add col name to COLUMNS of class
            try:
                owner.COLUMNS.append(name)
            except AttributeError:
                owner.COLUMNS = [name]
        self.name = name

    def __get__(self, instance, owner):
        # if we would just return None we wouldn't be able to know
        # if the actual value was None or if the key wasnt present yet (when in __init__)
        try:
            return self.values[instance]
        except KeyError:
            return ColumnValue.NO_VALUE

    def __set__(self, instance, value):
        if value is not None and not isinstance(value, self.type):
            raise TypeError("Value doesn't match the column's type!")
        # important to come b4 setting the value otherweise we cant get the old value
        committed_state_callback(instance, self.name, value)

        self.values[instance] = value

    def __delete__(self, instance):
        del self.values[instance]


class ColumnWithCallback(Column):

    def __init__(self, value_type, default=None, **kwargs):
        super().__init__(value_type, default=default, **kwargs)
        self.callbacks = WeakKeyDictionary()

    def __set__(self, instance, value):
        super().__set__(instance, value)
        # call registered callback and inform them of new value
        # important this happens b4 setting the value otherwise we cant retrieve old value
        for callback in self.callbacks.get(instance, []):
            callback(value)

    def add_callback(self, instance, callback):
        """Add a new function to call everytime the descriptor updates
        To be able to call add_callback you have to call it on the class level,
        since when descriptors get called they always invoke __get__ but when called
        on the class level the 1st argument to get is None"""
        if instance not in self.callbacks:
            self.callbacks[instance] = set()
        self.callbacks[instance].add(callback)
