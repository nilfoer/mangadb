# some of this code is taken from:
# https://github.com/mikf/gallery-dl/tree/master/gallery_dl by Mike Fährmann
import os
import inspect
import importlib

from typing import List, Iterator, Union, Dict, Type

from .base import BaseMangaExtractor
from ..exceptions import MangaDBException


module_dir: str = os.path.dirname(os.path.realpath(__file__))

# account for being bundled (e.g. using pyinstaller)
# when trying to find data files relative to the main script, sys._MEIPASS can be used
# if getattr(sys, 'frozen', False):  # check if we're bundled
#     bundle_dir = os.path.abspath(sys._MEIPASS)
#     module_dir = os.path.join(bundle_dir, os.path.dirname(__file__))
# the above does not work since python modules are embedded in the exe as a
# compressed ZlibArchive instead of being saved in a normal folder structure
# custom import hooks make sure that normal imports work
# but since we try to import files based on a folders content it won't work
# since __file__ just points to the location at the time of import and
# not to the location in the exe (since that's not possible with a path anyway)
# => either import them by a list of static names or store them
#    as data files in the pyinstaller output

# get all modules in dir (except __init__.py) and remove ending
# also possible to specify all names
# don't include base module since empty pattern "" of BaseExtractor matches on everything
modules: List[str] = [f[:-3] for f in os.listdir(module_dir) if not f.startswith("__") and
                      f != 'base.py' and f.endswith('.py')]

# holds extractor classes already imported extractor modules
_cache: List[Type[BaseMangaExtractor]] = []

# these should never be changed, only new ones can be added!
SUPPORTED_SITES: Dict[Union[int, str], Union[int, str]] = {
        # site id, site name
        1: "tsumino.com",
        2: "nhentai.net",
        3: "MangaDex",
        4: "Manganelo",
        5: "Toonily",
        6: "MangaSee123",
        # site name, id
        "tsumino.com": 1,
        "nhentai.net": 2,
        "MangaDex": 3,
        "Manganelo": 4,
        "Toonily": 5,
        "MangaSee123": 6,
}
# TODO add to mangasee123 to db


def find(url: str) -> Type[BaseMangaExtractor]:
    """Find extractor for given url"""
    for cls in _list_extractor_classes():
        if cls.match(url):
            return cls
    else:
        raise NoExtractorFound(f"No matching extractor found for '{url}'")


def find_by_site_id(site_id: int) -> Type[BaseMangaExtractor]:
    """Find extractor for given site_id"""
    for cls in _list_extractor_classes():
        if cls.site_id == site_id:
            return cls
    else:
        raise NoExtractorFound(f"No matching extractor found for site_id '{site_id}'")


def add_extractor_cls_module(module):
    # needed if a class can have more than one pattern
    # then add (pattern, class) tuples for all cls in _get_classes_in_module
    pass


def _list_extractor_classes() -> Iterator[Type[BaseMangaExtractor]]:
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


def _get_classes_in_module(module) -> List[Type[BaseMangaExtractor]]:
    """Returns a list of all subclasses of BaseMangaExtractor in module"""
    # get all members if isclass
    # and class has URL_PATTERN_RE
    # Return all the members of an object in a list of (name, value) pairs
    # sorted by name. If the optional predicate argument is supplied, only
    # members for which the predicate returns a true value are included
    # inspect.getmembers(module, inspect.isclass) also includes imported classes!!!
    # -> check that cls module name matches module.__name__
    return [insp_tuple[1] for insp_tuple in inspect.getmembers(module, inspect.isclass) if
            issubclass(insp_tuple[1], BaseMangaExtractor) and
            insp_tuple[1].__module__ == module.__name__]


class NoExtractorFound(MangaDBException):
    def __init__(self, msg):
        # Call the base class constructor with the parameters it needs
        super().__init__(msg)
