from weakref import WeakKeyDicitonary

from .row import DBRow


class AssociatedColumn:

    def __init__(self, table_name, assoc_table=None, **kwargs):
        self.table_name = table_name
        self.assoc_table = assoc_table
        self.values = WeakKeyDicitonary()
        self.callbacks = WeakKeyDicitonary()
        # callback that sets the current state as commited state on the instance
        # the first time the value is changed after a commit
        self.committed_state_callback = DBRow.committed_state_callback

    # new in py3.6: Called at the time the owning class owner is created. The descriptor has been
    # assigned to name
    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        v = self.values.get(instance, None)
        # return frozenset so users cant modify it directly
        return frozenset(v) if v else None

    def __set__(self, instance, value):
        value = set(value)
        self.committed_state_callback(instance, self.name, value)
        # call registered callback and inform them of new value
        # important this happens b4 setting the value otherwise we cant retrieve old value
        for callback in self.callbacks.get(instance, []):
            callback(instance, self.name, value)

        self.values[instance] = value

    def __delete__(self, instance):
        del self.values[instance]

    def add(self, instance, value):
        self.committed_state_callback(instance, self.name, value)
        try:
            self.values[instance].add(value)
        except KeyError:
            self.values[instance] = {value}

    def discard(self, instance, value):
        self.committed_state_callback(instance, self.name, value)
        try:
            self.values[instance].discard(value)
            return True
        except KeyError:
            return

    def add_callback(self, instance, callback):
        """Add a new function to call everytime the descriptor updates
        To be able to call add_callback you have to call it on the class level,
        since when descriptors get called they always invoke __get__ but when called
        on the class level the 1st argument to get is None"""
        if instance not in self.callbacks:
            self.callbacks[instance] = set()
        self.callbacks[instance].add(callback)
