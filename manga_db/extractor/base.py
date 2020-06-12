import urllib.request
import logging

logger = logging.getLogger(__name__)


class BaseMangaExtractor:
    site_name = ""
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }
    URL_PATTERN_RE = ""

    def __init__(self, url):
        self.url = url

    def get_metadata(self):
        raise NotImplementedError

    def get_cover(self):
        raise NotImplementedError

    @classmethod
    def split_title(cls, title):
        # split tile into english and foreign title
        raise NotImplementedError

    @classmethod
    def book_id_from_url(cls, url):
        raise NotImplementedError

    @classmethod
    def read_url_from_id_onpage(cls, id_onpage):
        raise NotImplementedError

    # contrary to @staticmethod classmethod has a reference to the class as first parameter
    @classmethod
    def get_html(cls, url):
        res = None

        req = urllib.request.Request(url, headers=cls.headers)
        try:
            site = urllib.request.urlopen(req)
        except urllib.request.HTTPError as err:
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
