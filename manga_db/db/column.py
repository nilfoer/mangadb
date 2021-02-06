from weakref import WeakKeyDictionary
from typing import Generic, TypeVar, Dict, Any, Callable, Optional, Union, Type, overload, Set

from .constants import ColumnValue


# callback that sets the current state as commited state on the instance
# the first time the value is changed after a commit
def committed_state_callback(instance, col_name: str, before, after):
    if col_name not in instance._committed_state:
        if before is not ColumnValue.NO_VALUE:
            instance._committed_state[col_name] = before


# NOTE: if the descriptor (Column is one, since it defines __get__ etc.) depends
# on some specific attributes on instance/owner in the descriptor methods
# (__get, __set, __set_name__ etc.) that it doesn't set itself then it should use
# two type argument e.g. T and O (O for owner); __get__ would then look like:
# def __get__(self, instance: O, ower: Type[O]) -> T:
T = TypeVar('T')


# mypy generic classes need to inherit from Generic unless another base class
# already does
class Column(Generic[T]):

    # set by __set_name__ on instance
    name: str

    def __init__(self, value_type: Type[T], default: Optional[T] = None, **kwargs):
        self.type = value_type
        self.default = default
        # TODO what was this for?
        self.values: WeakKeyDictionary = WeakKeyDictionary()
        self.primary_key: bool = kwargs.pop("primary_key", False)
        self.nullable: bool = kwargs.pop("nullable", True)

    # new in py3.6: Called at the time the owning class owner is created. The descriptor has been
    # assigned to name (there's an attribute named name on owner, which is a type/class)
    def __set_name__(self, owner: Type, name: str):
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

    @overload
    def __get__(self, instance: None, owner: Type) -> 'Column[T]': ...

    @overload
    def __get__(self, instance: Any, owner: Type) -> Union[T, ColumnValue]: ...

    # Descriptors get invoked by the dot "operator" during attribute lookup. If
    # a descriptor is accessed indirectly with vars(some_class)[descriptor_name],
    # the descriptor instance is returned without invoking it.
    # see: https://docs.python.org/3/howto/descriptor.html
    def __get__(self, instance: Optional[Any], owner: Type) -> Union['Column[T]', T, ColumnValue]:
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
            #
            # return default if we have one and the value is None
            # val = instance.__dict__[self.name]
            # better style to use getattr
            val = getattr(instance, self.name)
            if self.default is not None and val is None:
                return self.default
            return val
        except KeyError:
            return ColumnValue.NO_VALUE

    def __set__(self, instance: Any, value: T) -> None:
        # TODO is this still neede with mypy?
        if value is not None and not isinstance(value, self.type):
            raise TypeError(f"Value doesn't match the column's ({self.name}) type! Got "
                            f"{type(value)}: {value} epxected {self.type}")

        before = self.__get__(instance, instance.__class__)
        committed_state_callback(instance, self.name, before, value)

        instance.__dict__[self.name] = value

    def __delete__(self, instance: Any) -> None:
        del instance.__dict__[self.name]


class ColumnWithCallback(Column[T]):

    # name -> callabck (instance, name, before, after)
    callbacks: Dict[str, Set[Callable[[Any, str, Optional[T], Optional[T]], None]]]

    def __init__(self, value_type: Type[T], default: Optional[T] = None, **kwargs):
        super().__init__(value_type, default=default, **kwargs)
        self.callbacks = {}

    def __set__(self, instance: Any, value: Optional[T]):
        # @CopyNPaste from base class; move this to an internal func or sth.
        # so we don't repeat the code
        if value is not None and not isinstance(value, self.type):
            raise TypeError(f"Value doesn't match the column's ({self.name}) type! Got "
                            f"{type(value)}: {value} epxected {self.type}")

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
