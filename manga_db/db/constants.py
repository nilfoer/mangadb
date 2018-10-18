import enum


class ColumnValue(enum.Enum):
    NO_VALUE = 0

# could also use a helper class instance to represent my constants
# since they wont compare true against values that could be stored in a cell
# >>> a=1
# >>> b=1
# >>> a is b
# True
# >>> class A:
# ...     a=1
# ...
# >>> class B:
# ...     b=1
# ...
# >>> A.a is B.b
# True
# >>> class symbol:
# ...     def __init__(self, name, value):
# ...             self.name = name
# ...             self.value = value
# ...
# >>> a=symbol("NO_VALUE", 0)
# >>> b=symbol("NO_VALUE", 0)
# >>> a==b
# False
# >>> a is b
# False
