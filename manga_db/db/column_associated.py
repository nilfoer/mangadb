from typing import (
    Generic, TypeVar, Dict, Any, Callable, Optional, Union, Type,
    Set, overload, List, Iterable, Sequence
)

from .column import committed_state_callback, UninitializedColumn
from .constants import Relationship


# adapted from https://stackoverflow.com/a/8859168 Andrew Clark
def trackable_type(instance: Any, name: str, base: Type,
                   on_change_callback: Callable[[Any, str, bool, Any, Any], None],
                   *init_args, **init_kwargs) -> Any:
    def func_add_callback(func):
        def wrapped(self, *args, **kwargs):
            before = base(self)
            result = func(self, *args, **kwargs)
            after = base(self)
            if before != after:
                # on_change_callback(instance, name, was_uninitialized, before, after)
                # can access an uninitialized value here?
                on_change_callback(instance, name, False, before, after)
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
                    # wrap method call so we get a callback
                    if isinstance(func, methods):
                        dct[attr] = func_add_callback(func)
            return type.__new__(cls, name, bases, dct)

    # inherit from base class and use metaclass TrackableMeta
    # to apply callback to base class methods
    # NOTE: mypy can't check this since Base class base is dynamic
    class TrackableObject(base, metaclass=TrackableMeta):  # type: ignore
        # metaclass kwarg -> py3
        # py2: __metaclass__ = TrackableMeta
        pass
    TrackableObject.__name__ = f"{name}_{base.__name__}"

    # initialize TrackableObject (uses base.__init__) with init_args/kwargs
    return TrackableObject(*init_args, **init_kwargs)


# type of tracked column
T = TypeVar('T')


# mypy generic classes need to inherit from Generic unless another base class
# already does
class AssociatedColumnBase(Generic[T]):

    # attribute name on the "owning" class, will be set by __set_name__
    name: str
    # name -> callabck (instance, name, before, after)
    callbacks: Dict[str, Set[Callable[[T, str, bool, Any, Any], None]]]

    def __init__(self, table_name: str, relationship: Relationship, **kwargs):
        self.table_name = table_name
        self.relationship = relationship
        self.callbacks = {}

    # new in py3.6: Called at the time the owning class owner is created. The descriptor has been
    # assigned to name (there's an attribute named name on owner, which is a type/class)
    def __set_name__(self, owner: Type, name: str) -> None:
        # add col name to ASSOCIATED_COLUMNS of class
        try:
            owner.ASSOCIATED_COLUMNS.append(name)
        except AttributeError:
            owner.ASSOCIATED_COLUMNS = [name]
        self.name = name

    @overload
    def __get__(self, instance: None, owner: Type) -> 'AssociatedColumnBase[T]': ...

    @overload
    def __get__(self, instance: Any, owner: Type) -> List[T]: ...

    def __get__(self, instance: Any, owner: Type) -> Union['AssociatedColumnBase', List[T]]:
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
            return vars(instance)[self.name]
        except KeyError:
            raise UninitializedColumn

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
    # or handle it in the callback by __get__ raising UninitializedColumn
    def add_callback(self, name, callback):
        """Add a new function to call everytime the descriptor updates
        To be able to call add_callback you have to call it on the class level (of the instance),
        since when descriptors get called they always invoke __get__ but when called
        on the class level the 1st argument to get is None"""
        if name not in self.callbacks:
            self.callbacks[name] = set()
        self.callbacks[name].add(callback)


class AssociatedColumnMany(AssociatedColumnBase[T]):

    callbacks: Dict[str, Set[Callable[[T, str, bool, Iterable[T], Iterable[T]], None]]]

    def __init__(self, table_name: str, relationship: Relationship,
                 assoc_table: Optional[str] = None, **kwargs):
        super().__init__(table_name, relationship, **kwargs)
        if self.relationship is Relationship.MANYTOMANY and not assoc_table:
            raise ValueError("Value for assoc_table is needed when relationship"
                             " is MANYTOMANY")
        self.table_name = table_name
        self.assoc_table = assoc_table

    def __set__(self, instance: Any, value: Iterable[T]) -> None:
        if value:
            value = trackable_type(instance, self.name, list, committed_state_callback, value)
        else:
            # dont set to None or other unwanted type use our trackable set instead
            value = trackable_type(instance, self.name, list, committed_state_callback)

        was_uninitialized = False
        try:
            before = self.__get__(instance, instance.__class__)
        except UninitializedColumn:
            was_uninitialized = True
            before = None

        committed_state_callback(instance, self.name, was_uninitialized, before, value)

        # same problem as with getattr arises with setattr -> descriptor __set__
        # get called infinitely -> can't use it
        vars(instance)[self.name] = value

        for callback in self.callbacks.get(self.name, []):
            callback(instance, self.name, was_uninitialized, before, value)


class AssociatedColumnOne(AssociatedColumnBase[T]):

    callbacks: Dict[str, Set[Callable[[T, str, bool, Optional[T], Optional[T]], None]]]

    def __set__(self, instance: Any, value: Optional[T]):
        was_uninitialized = False
        try:
            before = self.__get__(instance, instance.__class__)
        except UninitializedColumn:
            was_uninitialized = True
            before = None

        committed_state_callback(instance, self.name, was_uninitialized, before, value)
        # call registered callback and inform them of new value
        # important this happens b4 setting the value otherwise we cant retrieve old value
        for callback in self.callbacks.get(self.name, []):
            callback(instance, self.name, was_uninitialized, before, value)

        vars(instance)[self.name] = value
