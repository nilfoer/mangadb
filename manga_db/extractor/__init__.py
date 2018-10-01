# some of this code is taken from:
# https://github.com/mikf/gallery-dl/tree/master/gallery_dl by Mike Fährmann
import os
import inspect
import importlib
import re

module_dir = os.path.dirname(os.path.realpath(__file__))
# get all modules in dir (except __init__.py) and remove ending
# also possible to specify all names
modules = [f[:-3] for f in os.listdir(module_dir) if f.endswith(".py") and not f.startswith("__")]
# since empty pattern "" of BaseExtractor matches on everything
modules.remove("base")

# holds extractor classes already imported extractor modules
_cache = []

SUPPORTED_SITES = {
        # site id, site name
        1: "tsumino.com",
        # site name, id
        "tsumino.com": 1
        }


def find(url):
    """Find extractor for given url"""
    for cls in _list_extractor_classes():
        if re.match(cls.URL_PATTERN_RE, url):
            return cls
    else:
        # TODO(m): custom exc
        raise Exception(f"No matching extractor found for '{url}'")


def add_extractor_cls_module(module):
    # needed if a class can have more than one pattern
    # then add (pattern, class) tuples for all cls in _get_classes_in_module
    pass


def _list_extractor_classes():
    """
    Yields
    firstly: Extractor classes from _cache (since their modules were already imported)
    secondly: Iterates over all extracotr modules and yields the found Extractor classes
    """
    # yield from g is similar to for c in _cache: yield v; but theres way more to it than just that
    yield from _cache
    for mod_name in modules:
        # using relative import with "." package=base of rel import
        extr_classes = _get_classes_in_module(importlib.import_module(
            "."+mod_name, package=__package__))
        # add extr classes of imported modules to cache
        _cache.extend(extr_classes)
        yield from extr_classes


def _get_classes_in_module(module):
    """Returns a list of all classes in module that have the attribute URL_PATTERN_RE"""
    # get all members if isclass
    # and class has URL_PATTERN_RE
    # Return all the members of an object in a list of (name, value) pairs
    # sorted by name. If the optional predicate argument is supplied, only
    # members for which the predicate returns a true value are included
    # inspect.getmembers(module, inspect.isclass) also includes imported classes!!!
    # -> check that cls module name matches module.__name__
    return [insp_tuple[1] for insp_tuple in inspect.getmembers(module, inspect.isclass) if
            hasattr(insp_tuple[1], "URL_PATTERN_RE") and
            insp_tuple[1].__module__ == module.__name__]
