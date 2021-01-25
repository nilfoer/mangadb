import json
from datetime import datetime, date
from functools import singledispatch

# from ..ext_info import ExternalInfo

# Put simply, you define a default function and then register additional versions of that functions
# depending on the type of the first argument


@singledispatch
def to_serializable(val):
    """Used by default."""
    # print(type(val))
    return json.dumps({a: getattr(a) for a in vars(val)})


@to_serializable.register(datetime)
def to_datetime(val):
    """Used if *val* is an instance of datetime."""
    # NOTE: see to_date
    # return val.strftime("%Y-%m-%d %H:%M:%S %Z")
    return val.isoformat()


@to_serializable.register(date)
def to_date(val):
    """Used if *val* is an instance of date."""
    # NOTE: strftime's %Y is inconsistent between OSs; pads with 0 to 4 digits
    # on Windows but doesn't pad on linux
    # isoformat does not seemt to have that problem???
    # return val.strftime("%Y-%m-%d")
    return val.isoformat()


# incomplete
# @to_serializable.register(ExternalInfo)
# def to_ext_info(val):
#     dic = {a: json.dumps(getattr(a)) for a in vars(val)}
