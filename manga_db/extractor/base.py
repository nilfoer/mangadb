import urllib.request
import urllib.error
import logging
import datetime

from dataclasses import dataclass
from typing import Dict, Tuple, Optional, TYPE_CHECKING, Literal, List, ClassVar

if TYPE_CHECKING:
    from ..ext_info import ExternalInfo

logger = logging.getLogger(__name__)

# NOTE: tag-like values (e.g. artist name or traditional tags) will be forced to titlecase
# when passing them to MangaExtractorData, exceptions are defined here in form of the
# extractor's site_id
FORCE_TITLECASE_EXCEPTIONS = [1, 3, 4, 5]


# could also use TypedDict which means it would accept regular dicts that use only
# __and__ all the required keys of the correct type
@dataclass
class MangaExtractorData:
    # NOTE: !IMPORTANT! needs at least one of the titles
    title_eng: Optional[str]
    title_foreign: Optional[str]
    language: str  # will be added if not present
    pages: int
    status_id: int  # from STATUS_IDS
    nsfw: int  # 0 or 1

    note: Optional[str]

    category: List[str]
    collection: List[str]
    groups: List[str]
    artist: List[str]
    parody: List[str]
    character: List[str]
    tag: List[str]

    # ExternalInfo data
    url: str
    # if there are mutliple parts, separate them with '##'
    id_onpage: str
    imported_from: int  # extractor's site_id
    censor_id: int  # from CENSOR_IDS
    upload_date: datetime.date

    uploader: Optional[str]
    rating: Optional[float]
    ratings: Optional[int]
    favorites: Optional[int]

    # runs after generated __init__
    def __post_init__(self):
        assert self.title_eng or self.title_foreign

        if self.imported_from not in FORCE_TITLECASE_EXCEPTIONS:
            # ensure all "tags" are titlecased so we a) dont have to use case-insensitive search
            # and b) dont have to titlecase them when loading them from the DB (when e.g.
            # all titles in the db are lowercase)
            for attr in ('category', 'collection', 'groups', 'artist', 'parody', 'character', 'tag'):
                setattr(self, attr, [s.title() for s in getattr(self, attr)])
    

class BaseMangaExtractor:
    # headers that get added when the class makes a request
    # will overwrite default headers from the opener
    add_headers: Dict[str, str] = {}

    # these need to be re-defined by sub-classes!!
    # they are not allowed to changed after the extractor has been added
    # doing so would require a db migration
    site_name: ClassVar[str] = ""
    site_id: ClassVar[int] = 0

    url: str

    def __init__(self, url: str):
        self.url = url

    @classmethod
    def match(cls, url: str) -> bool:
        """
        Returns True on URLs the extractor is compatible with
        """
        raise NotImplementedError

    def extract(self) -> Optional[MangaExtractorData]:
        raise NotImplementedError

    def get_cover(self) -> Optional[str]:
        raise NotImplementedError

    @classmethod
    def split_title(cls, title: str) -> Tuple[Optional[str], Optional[str]]:
        # split tile into english and foreign title
        raise NotImplementedError

    @classmethod
    def book_id_from_url(cls, url: str) -> str:
        raise NotImplementedError

    @classmethod
    def url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        raise NotImplementedError

    @classmethod
    def read_url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        raise NotImplementedError

    @classmethod
    def get_html(cls, url: str, add_headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        res = None

        headers = cls.add_headers.copy()
        if add_headers is not None:
            headers.update(add_headers)

        # NOTE: passing the headers kwarg means we will stil use the headers from the opener
        # but names that already exist in the opener's headers will be overwritten
        req = urllib.request.Request(url, headers=headers)
        # removing headers with req.remove_header will not remove the headers installed by
        # the opener
        # req.remove_header('User-Agent')
        # NOTE: after the request has been sent the req.unredirected_hdrs will contain the headers
        # added by the opener, and req.headers will then contain all the headers including

        try:
            # site = cls.opener.open(req)
            site = urllib.request.urlopen(req)
        except urllib.error.HTTPError as err:
            # 503 is also sent by cloudflare if we don't pass the js/captcha challenge
            # @Hack only re-raising 503 so we can conviently pass that on and tell
            # a webGUI user to create/update the cookies.txt
            if err.code == 503:
                raise
            logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
        else:
            # leave the decoding up to bs4
            res = site.read()
            site.close()

            # try to read encoding from headers otherwise use utf-8 as fallback
            encoding = site.headers.get_content_charset()
            res = res.decode(encoding.lower() if encoding else "utf-8")
            logger.debug("Getting html done!")

        return res
