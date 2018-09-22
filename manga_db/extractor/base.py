import urllib.request
import logging

logger = logging.getLogger(__name__)


class BaseMangaExtractor:
    site_name = ""
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    def __init__(self, url):
        self.url = url

    def get_metadata(self):
        pass

    def get_cover(self):
        pass

    # contrary to @staticmethod classmethod has a reference to the class as first parameter
    @classmethod
    def get_url(cls, url):
        res = None

        req = urllib.request.Request(url, headers=cls.headers)
        try:
            site = urllib.request.urlopen(req)
        except urllib.request.HTTPError as err:
            logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
        else:
            res = site.read().decode('utf-8')
            site.close()
            logger.debug("Getting html done!")

        return res
