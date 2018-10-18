from weakref import WeakKeyDictionary

from .column import committed_state_callback
from .constants import ColumnValue


# adapted from https://stackoverflow.com/a/8859168 Andrew Clark
def trackable_type(instance, name, base, on_change_callback, *init_args, **init_kwargs):
    def func_add_callback(func):
        def wrapped(self, *args, **kwargs):
            before = base(self)
            result = func(self, *args, **kwargs)
            after = base(self)
            if before != after:
                # on_change_callback(instance, name, before, after)
                on_change_callback(instance, name, before)
            return result
        return wrapped

    # (<class 'method_descriptor'>, <class 'wrapper_descriptor'>)
    methods = (type(list.append), type(list.__setitem__))
    skip = set(['__iter__', '__len__', '__getattribute__'])

    # ceate Metaclass for trackable class
    class TrackableMeta(type):
        def __new__(cls, name, bases, dct):
            for attr in dir(base):
                if attr not in skip:
                    func = getattr(base, attr)
                    if isinstance(func, methods):
                        dct[attr] = func_add_callback(func)
            return type.__new__(cls, name, bases, dct)

    # inherit from base class and use metaclass TrackableMeta
    # to apply callback to base class methods
    class TrackableObject(base, metaclass=TrackableMeta):
        # metaclass kwarg -> py3
        # py2: __metaclass__ = TrackableMeta
        pass
    TrackableObject.__name__ = f"{name}_{base.__name__}"

    # initialize TrackableObject (uses base.__init__) with init_args/kwargs
    return TrackableObject(*init_args, **init_kwargs)


class AssociatedColumn:

    def __init__(self, table_name, assoc_table=None, **kwargs):
        self.table_name = table_name
        self.assoc_table = assoc_table
        self.values = WeakKeyDictionary()
        self.callbacks = WeakKeyDictionary()

    # new in py3.6: Called at the time the owning class owner is created. The descriptor has been
    # assigned to name
    def __set_name__(self, owner, name):
        # add col name to ASSOCIATED_COLUMNS of class
        try:
            owner.ASSOCIATED_COLUMNS.append(name)
        except AttributeError:
            owner.ASSOCIATED_COLUMNS = [name]
        self.name = name

    def __get__(self, instance, owner):
        # if we would just return None we wouldn't be able to know
        # if the actual value was None or if the key wasnt present yet (when in __init__)
        try:
            return self.values[instance]
        except KeyError:
            return ColumnValue.NO_VALUE

    def __set__(self, instance, value):
        if value:
            value = trackable_type(instance, self.name, set, committed_state_callback, value)
        else:
            value = None
        # since __get__ returns None if key isnt present
        committed_state_callback(instance, self.name, value)
        # call registered callback and inform them of new value
        # important this happens b4 setting the value otherwise we cant retrieve old value
        for callback in self.callbacks.get(instance, []):
            callback(instance, self.name, value)

        self.values[instance] = value

    def __delete__(self, instance):
        del self.values[instance]

    def add_callback(self, instance, callback):
        """Add a new function to call everytime the descriptor updates
        To be able to call add_callback you have to call it on the class level,
        since when descriptors get called they always invoke __get__ but when called
        on the class level the 1st argument to get is None"""
        if instance not in self.callbacks:
            self.callbacks[instance] = set()
        self.callbacks[instance].add(callback)
