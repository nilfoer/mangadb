import urllib.request
import urllib.error
import logging
import datetime

from dataclasses import dataclass
from typing import Dict, Tuple, Optional, TYPE_CHECKING, Literal, List, ClassVar

if TYPE_CHECKING:
    from ..ext_info import ExternalInfo

logger = logging.getLogger(__name__)


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
    nsfw: Literal[0, 1]

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

    # run last in generated __init__
    def __post_init__(self):
        assert self.title_eng or self.title_foreign
    

class BaseMangaExtractor:
    headers: Dict[str, str] = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    # assumes that requests are all made to the same domain so we don't
    # need to have separate dicts per domain
    cookies: ClassVar[Dict[str, str]] = {}

    # these need to be re-defined by sub-classes!!
    # they are not allowed to changed after the extractor has been added
    # doing so would require a db migration
    site_name: ClassVar[str] = ""
    site_id: ClassVar[int] = 0

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
    def get_html(cls, url: str, user_agent: Optional[str] = None,
                 cookies: Optional[Dict[str, str]] = None) -> Optional[str]:
        res = None

        headers = cls.headers.copy()
        if user_agent is not None:
            headers['User-Agent'] = user_agent

        all_cookies = cls.cookies.copy()
        if cookies is not None:
            # specific cookies overwrite default class cookies
            all_cookies.update(cookies)
        if all_cookies:
            # cookie_name = cookie_value; cookie_name = cookie_value
            cookie_str = "; ".join(f"{name} = {value}" for name, value in all_cookies.items())
            headers['Cookie'] = cookie_str

        # NOTE: passing the headers kwarg means we don't use the headers from the
        # globally installed opener
        req = urllib.request.Request(url)
        for name, val in req.header_items():
            print(name, '/', val)

        try:
            site = urllib.request.urlopen(req)
            print(type(site))
            print(site.getheaders())
        except urllib.error.HTTPError as err:
            # 503 is also sent by cloudflare if we don't pass the js/captcha challenge
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
