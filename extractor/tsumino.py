import logging
import datetime
import re

import bs4

from .base import BaseMangaExtractor

logger = logging.getLogger(__name__)


class TsuminoExtractor(BaseMangaExtractor):
    site_name = "Tsumino"
    ID_ONPAGE_RE = re.compile(r"tsumino\.com/Book|Read|Download/Info|View|Index/(\d+)")
    ENG_TITLE_RE = re.compile(r"^(.+) \/")
    metadata_helper = {  # attribute/col in db: key in metadata extracted from tsumino
            "title": "Title", "uploader": "Uploader", "upload_date": "Uploaded",
            "pages": "Pages", "rating_full": "Rating", "my_rating": "My Rating",
            "category": "Category", "collection": "Collection", "groups": "Group",
            "artist": "Artist", "parody": "Parody", "character": "Character",
            "tags": "Tag", "url": None, "id_onpage": None, "rating": None,
            "title_eng": None
            }

    def __init__(self, url):
        super().__init__(url)
        self.url = url
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
                self.html = TsuminoExtractor.get_url(self.url)
            self.metadata = self.transform_metadata(TsuminoExtractor.extract_info(self.html))
        return self.metadata

    def transform_metadata(self, metadata):
        """
        Transform metadata parsed from tsumino.com into DB format
        """
        result = {}
        for attr, key in self.metadata_helper.items():
            # not every key present on every book page (e.g. "Parody", "Group"..)
            if attr == "url":
                result[attr] = self.url
            elif attr == "pages":
                result[attr] = int(metadata[key])
            elif attr == "id_onpage":
                result[attr] = re.search(self.ID_ONPAGE_RE, self.url).group(1)
            elif attr == "rating":
                result[attr] = float(metadata["Rating"].split()[0])
            elif attr == "category":
                result[attr] = ", ".join(metadata[key])
            elif attr == "upload_date":
                result[attr] = datetime.datetime.strptime(metadata[key], "%Y %B %d").date()
            elif attr == "title_eng":
                eng_title = re.match(self.ENG_TITLE_RE, metadata["Title"])
                eng_title = eng_title.group(1) if eng_title else metadata["Title"]
                result[attr] = eng_title
            else:
                try:
                    result[attr] = metadata[key]
                except KeyError:
                    logger.warning("Key '%s' for attribute '%s' was not found! HTML on"
                                   "tsumino.com probably changed!", key, attr)
                    # TODO custom exc?
                    raise
        return result

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
            return int(re.match(cls.ID_ONPAGE_RE, url).group(1))
        except IndexError:
            logger.warning("No book id could be extracted from \"%s\"!", url)
            # reraise or continue and check if bookid returned in usage code?
            raise
