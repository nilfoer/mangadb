import json
from datetime import datetime, date
from functools import singledispatch

# from ..ext_info import ExternalInfo

# singledispatch:
# Put simply, you define a default function and then register additional versions of that functions
# depending on the type of the first argument


# will be used as dumps(default=to_serializable) function
# default is called whenever the JSONEncoder doesn't know how to encode a type
# and expects a return value that it knows how to encode
@singledispatch
def to_serializable(val):
    """Used by default."""
    # print(type(val))
    # in order for our dispatch (dispatching to different 'overloads' based on the first
    # argument type(s)) to work recursively we need to pass ourselves to json.dumps
    # as default again
    # another method would be to (ab)use str and do return str(val)
    # if we use json.dumps like this here the entire thing wil be serialized to a string
    # and then in turn be serialized __as__ a string by the original JSONEncoder
    # return json.dumps({a: getattr(val, a) for a in vars(val)}, default=to_serializable)
    # json.loads would load it back as a string rather than a dict
    # give the original JSONEncoder the dict back directly instead
    return {a: getattr(val, a) for a in vars(val)}


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
