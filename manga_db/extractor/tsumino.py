import logging
import datetime
import os.path
import urllib.request
import re

import bs4

from .base import BaseMangaExtractor

logger = logging.getLogger(__name__)


class TsuminoExtractor(BaseMangaExtractor):
    site_name = "tsumino.com"
    URL_PATTERN_RE = re.compile(r"^(https?://)?(www\.)?tsumino\.com/(Book|Read|Download)/"
                                r"(Info|View|Index)/(\d+)/?([\w-]+)?")
    ID_ONPAGE_RE = re.compile(r"tsumino\.com/(Book|Read|Download)/(Info|View|Index)/(\d+)")
    ENG_TITLE_RE = re.compile(r"^(.+) \/")
    metadata_helper = {  # attribute/col in db: key in metadata extracted from tsumino
            "title": "Title", "uploader": "Uploader", "upload_date": "Uploaded",
            "pages": "Pages", "rating_full": "Rating", "my_rating": "My Rating",
            "category": "Category", "collection": "Collection", "groups": "Group",
            "artist": "Artist", "parody": "Parody", "character": "Character",
            "tags": "Tag", "url": None, "id_onpage": None
            }

    def __init__(self, url):
        super().__init__(url)
        self.url = url
        self.id_onpage = TsuminoExtractor.book_id_from_url(url)
        self.thumb_url = f"http://www.tsumino.com/Image/Thumb/{self.id_onpage}"
        self.html = None
        self.metadata = None

    def __repr__(self):
        if self.metadata:
            metastring = ', '.join((f"{k}: '{v}'" for k, v in self.metadata.items()))
            return f"TsuminoExtractor('{self.url}', {metastring})"
        else:
            return f"TsuminoExtractor('{self.url}')"

    def get_metadata(self):
        if self.metadata is None:
            if self.html is None:
                self.html = TsuminoExtractor.get_html(self.url)
            self.metadata = self.transform_metadata(TsuminoExtractor.extract_info(self.html))
        return self.metadata

    def transform_metadata(self, metadata):
        """
        Transform metadata parsed from tsumino.com into DB format
        """
        result = {}
        value = None
        for attr, key in self.metadata_helper.items():
            # pop(key, default)
            value = metadata.pop(key, None)
            # not every key present on every book page (e.g. "Parody", "Group"..)
            if attr == "url":
                result[attr] = self.url
            elif attr == "pages":
                result[attr] = int(value)
            elif attr == "id_onpage":
                result[attr] = self.book_id_from_url(self.url)
            elif attr == "rating_full":
                result["rating"] = float(value.split()[0])
                result[attr] = value
            elif attr == "upload_date":
                result[attr] = datetime.datetime.strptime(value, "%Y %B %d").date()
            elif attr == "title":
                result[attr] = value
                eng_title = re.match(self.ENG_TITLE_RE, value)
                eng_title = eng_title.group(1) if eng_title else value
                result["title_eng"] = eng_title
            else:
                result[attr] = value
        if metadata:
            logger.warning("There are still metadata keys left! The HTML on tsumino.com"
                           "probably changed! Keys left over: %s", ", ".join(metadata.keys()))
        return result

    # should this be in the Extractor class or rather in a Downloader or the main MangaDB class?
    # but mb specific sites require certain headers or whatever?
    def get_cover(self):
        try:
            urllib.request.urlretrieve(self.thumb_url,
                                       os.path.join("thumbs", str(self.book_id)))
        except urllib.request.HTTPError as err:
            logger.warning(
                "Thumb for book with id (on page) %s couldnt be downloaded!",
                self.id_onpage)
            logger.warning("HTTP Error %s: %s: \"%s\"",
                           err.code, err.reason, self.thumb_url)
            return False
        else:
            return True
            logger.info(
                "Thumb for book with id (on page) %s downloaded successfully!",
                self.id_onpage)

    @classmethod
    def extract_info(cls, html):
        result_dict = {}

        soup = bs4.BeautifulSoup(html, "html.parser")
        book_data = soup.select_one("div.book-info-container").find_all(
            "div", class_="book-data")

        for book_dat_div in book_data:
            tag_id = book_dat_div["id"]
            if tag_id:
                # Using a tag name as an attribute will give you only the first tag by that name
                # -> use find_all
                if book_dat_div.a is not None:  # and book_dat_div["id"] == "Tag"
                    data_list = [
                        a.contents[0].strip() for a in book_dat_div.find_all("a")
                    ]
                    result_dict[tag_id] = data_list
                elif tag_id == "MyRating":
                    # TODO(m)
                    continue
                else:
                    result_dict[book_dat_div["id"]] = book_dat_div.contents[
                        0].strip()
        logger.debug("Extracted book data!")
        return result_dict

    # mb move to baseclass? but mb not able to get id from url
    @classmethod
    def book_id_from_url(cls, url):
        try:
            return int(re.search(cls.ID_ONPAGE_RE, url).group(3))
        except IndexError:
            logger.warning("No book id could be extracted from \"%s\"!", url)
            # reraise or continue and check if bookid returned in usage code?
            raise
