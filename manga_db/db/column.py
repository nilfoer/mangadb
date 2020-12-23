from weakref import WeakKeyDictionary

from .constants import ColumnValue


# callback that sets the current state as commited state on the instance
# the first time the value is changed after a commit
def committed_state_callback(instance, col_name, before, after):
    if col_name not in instance._committed_state:
        if before is not ColumnValue.NO_VALUE:
            instance._committed_state[col_name] = before


class Column:

    # set by __set_name__ on instance
    name = None

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
        # instance is None when we're being called from class level of instance
        # return self so we can access descriptors methods
        if instance is None:
            return self
        # if we would just return None we wouldn't be able to know
        # if the actual value was None or if the key wasnt present yet (when in __init__)
        try:
            # use name (== name of assigned attribute) to access value on INSTANCE's __dict__
            # so we can have unhashable types as instances (e.g. subclass of list or classes that
            # define __eq__ but not __hash__ (ExternalInfo)
            return instance.__dict__[self.name]
        except KeyError:
            return ColumnValue.NO_VALUE

    def __set__(self, instance, value):
        if value is not None and not isinstance(value, self.type):
            raise TypeError("Value doesn't match the column's type!")

        before = self.__get__(instance, instance.__class__)
        committed_state_callback(instance, self.name, before, value)

        instance.__dict__[self.name] = value

    def __delete__(self, instance):
        del instance.__dict__[self.name]


class ColumnWithCallback(Column):

    def __init__(self, value_type, default=None, **kwargs):
        super().__init__(value_type, default=default, **kwargs)
        self.callbacks = {}

    def __set__(self, instance, value):
        # @CopyNPaste from base class; move this to an internal func or sth.
        # so we don't repeat the code
        if value is not None and not isinstance(value, self.type):
            raise TypeError("Value doesn't match the column's type!")

        before = self.__get__(instance, instance.__class__)
        committed_state_callback(instance, self.name, before, value)

        instance.__dict__[self.name] = value

        # call registered callback and inform them of new value
        for callback in self.callbacks.get(self.name, []):
            callback(instance, self.name, before, value)

    # CAREFUL!
    # if we create a 2nd instance of e.g. Obj that contains this cls the callback that appends to
    # events will already be present when event is initialized
    # Obj __init__:
    # self.event = event
    # self.events = []
    # Obj.event.add_callback("event", event_callback)
    # -> tries to append to attr that doesnt exist
    # either make sure the element exists before the descriptors instance is assigned
    # or handle it in the callback by checking if before value is ColumnValue.NO_VALUE
    def add_callback(self, name, callback):
        """Add a new function to call everytime the descriptor updates
        To be able to call add_callback you have to call it on the class level (of the instance),
        since when descriptors get called they always invoke __get__ but when called
        on the class level the 1st argument to get is None"""
        if name not in self.callbacks:
            self.callbacks[name] = set()
        self.callbacks[name].add(callback)
