import logging
import datetime
import re

import bs4

from .base import BaseMangaExtractor
from ..util import is_foreign
from ..constants import CENSOR_IDS, STATUS_IDS
from ..extractor import SUPPORTED_SITES

logger = logging.getLogger(__name__)


class TsuminoExtractor(BaseMangaExtractor):
    site_name = "tsumino.com"
    site_id = 1
    URL_PATTERN_RE = re.compile(r"^(https?://)?(www\.)?tsumino\.com/(Book|Read|Download)/"
                                r"(Info|View|Index)/(\d+)/?([\w-]+)?")
    ID_ONPAGE_RE = re.compile(r"tsumino\.com/(Book|Read|Download)/(Info|View|Index)/(\d+)")
    TITLE_RE = re.compile(r"^(.+) \/ (.+)")
    RATING_FULL_RE = re.compile(r"(\d\.\d{1,2}) \((\d+) users / (\d+) favs\)")
    metadata_helper = {  # attribute/col in db: key in metadata extracted from tsumino
            "title": "Title", "uploader": "Uploader", "upload_date": "Uploaded",
            "pages": "Pages", "rating": "Rating", "my_rating": "My Rating",
            "category": "Category", "collection": "Collection", "groups": "Group",
            "artist": "Artist", "parody": "Parody", "character": "Character",
            "tag": "Tag", "url": None, "id_onpage": None
            }

    def __init__(self, manga_db, url):
        super().__init__(manga_db, url.strip("-"))
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
            elif attr == "rating":
                rat_full = self.RATING_FULL_RE.match(value)
                result[attr] = float(rat_full.group(1))
                result["ratings"] = int(rat_full.group(2))
                result["favorites"] = int(rat_full.group(3))
            elif attr == "uploader":
                if isinstance(value, list):
                    if len(value) > 1:
                        logger.error("More than one uploader: %s", value)
                    result["uploader"] = value[0]
                else:
                    result["uploader"] = value
            elif attr == "upload_date":
                result[attr] = datetime.datetime.strptime(value, "%Y %B %d").date()
            elif attr == "title":
                result[attr] = value
                title = re.match(self.TITLE_RE, value)
                if title:
                    result["title_eng"] = title.group(1)
                    result["title_foreign"] = title.group(2)
                else:
                    if is_foreign(value):
                        result["title_eng"] = None
                        result["title_foreign"] = value
                    else:
                        result["title_eng"] = value
                        result["title_foreign"] = None
            elif attr == "tag":
                result[attr] = value
                if value is None:
                    censor_id = CENSOR_IDS["Unknown"]
                else:
                    if "Decensored" in value:
                        censor_id = CENSOR_IDS["Decensored"]
                    elif "Uncensored" in value:
                        censor_id = CENSOR_IDS["Uncensored"]
                    else:
                        censor_id = CENSOR_IDS["Censored"]
                result["censor_id"] = censor_id
            else:
                result[attr] = value
        if metadata:
            logger.warning("There are still metadata keys left! The HTML on tsumino.com"
                           "probably changed! Keys left over: %s", ", ".join(metadata.keys()))
        # tsumino only has English books
        result["language_id"] = self.manga_db.language_map["English"]
        result["status_id"] = STATUS_IDS["Unknown"]
        result["imported_from"] = SUPPORTED_SITES["tsumino.com"]

        return result

    def get_cover(self):
        return self.thumb_url

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
                    # TODO cant do myrating until we implement auth with tsumino
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
