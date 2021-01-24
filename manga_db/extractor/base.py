import urllib.request
import urllib.error
import logging

from typing import Dict, Tuple, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..ext_info import ExternalInfo

logger = logging.getLogger(__name__)


class BaseMangaExtractor:
    headers: Dict[str, str] = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    # these need to be re-defined by sub-classes!!
    site_name: str = ""
    site_id: int = 0

    def __init__(self, url: str):
        self.url = url

    @classmethod
    def match(cls, url: str) -> bool:
        """
        Returns True on URLs the extractor is compatible with
        """
        raise NotImplementedError

    def get_metadata(self) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def get_cover(self) -> str:
        raise NotImplementedError

    @classmethod
    def split_title(cls, title: str) -> Tuple[str, str]:
        # split tile into english and foreign title
        raise NotImplementedError

    @classmethod
    def book_id_from_url(cls, url: str) -> int:
        raise NotImplementedError

    @classmethod
    def url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        raise NotImplementedError

    @classmethod
    def read_url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        raise NotImplementedError

    # contrary to @staticmethod classmethod has a reference to the class as first parameter
    @classmethod
    def get_html(cls, url: str) -> Optional[str]:
        res = None

        req = urllib.request.Request(url, headers=cls.headers)
        try:
            site = urllib.request.urlopen(req)
        except urllib.error.HTTPError as err:
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
