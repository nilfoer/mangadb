from .column import committed_state_callback
from .constants import ColumnValue, Relationship


# adapted from https://stackoverflow.com/a/8859168 Andrew Clark
def trackable_type(instance, name, base, on_change_callback, *init_args, **init_kwargs):
    def func_add_callback(func):
        def wrapped(self, *args, **kwargs):
            before = base(self)
            result = func(self, *args, **kwargs)
            after = base(self)
            if before != after:
                # on_change_callback(instance, name, before, after)
                on_change_callback(instance, name, before, after)
            return result
        return wrapped

    # (<class 'method_descriptor'>, <class 'wrapper_descriptor'>)
    methods = (type(list.append), type(list.__setitem__))
    # we also exclude __init__ here so when we initialize the instance
    # it wont call the callback/count as change
    # -> otherwise loading from db would count as change
    # if __init__ is also wrapped it also tracks when item is assigned to
    # a trackable type e.g. instance.tag = ["Tag1", "Tag2"] would add the prev
    # val to _committed_state
    skip = set(['__iter__', '__len__', '__getattribute__', '__init__'])

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


class AssociatedColumnBase:

    def __init__(self, table_name, relationship, **kwargs):
        self.table_name = table_name
        self.relationship = relationship
        self.callbacks = {}

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
        raise NotImplementedError

    def __delete__(self, instance):
        del instance.__dict__[self.name]

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


class AssociatedColumnMany(AssociatedColumnBase):

    def __init__(self, table_name, relationship, assoc_table=None, **kwargs):
        super().__init__(table_name, relationship, **kwargs)
        if self.relationship is Relationship.MANYTOMANY and not assoc_table:
            raise ValueError("Value for assoc_table is needed when relationship"
                             " is MANYTOMANY")
        self.table_name = table_name
        self.assoc_table = assoc_table

    def __set__(self, instance, value):
        if value:
            value = trackable_type(instance, self.name, list, committed_state_callback, value)
        else:
            # dont set to None or other unwanted type use our trackable set instead
            value = trackable_type(instance, self.name, list, committed_state_callback)
        before = self.__get__(instance, instance.__class__)
        committed_state_callback(instance, self.name, before, value)

        instance.__dict__[self.name] = value

        for callback in self.callbacks.get(self.name, []):
            callback(instance, self.name, before, value)


class AssociatedColumnOne(AssociatedColumnBase):

    def __set__(self, instance, value):
        before = self.__get__(instance, instance.__class__)
        committed_state_callback(instance, self.name, before, value)
        # call registered callback and inform them of new value
        # important this happens b4 setting the value otherwise we cant retrieve old value
        for callback in self.callbacks.get(self.name, []):
            callback(instance, self.name, before, value)

        instance.__dict__[self.name] = value
