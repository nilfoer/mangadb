import logging
import datetime
import re

import bs4

from typing import cast, Match, Optional, TYPE_CHECKING, Tuple, Dict, Any, Union

from .base import BaseMangaExtractor, MangaExtractorData
from ..util import is_foreign
from ..constants import CENSOR_IDS, STATUS_IDS

if TYPE_CHECKING:
    from ..ext_info import ExternalInfo

logger = logging.getLogger(__name__)


class TsuminoExtractor(BaseMangaExtractor):
    site_name = "tsumino.com"
    site_id = 1
    URL_PATTERN_RE = re.compile(r"^(?:https?:\/\/)?(?:www\.)?tsumino\.com\/"
                                r"(?:entry|Read\/Index)\/(\d+)\/?")
    TITLE_RE = re.compile(r"^(.+) \/ (.+)")
    URL_FORMAT = "https://www.tsumino.com/entry/{id_onpage}"
    READ_URL_FORMAT = "https://www.tsumino.com/Read/Index/{id_onpage}"
    RATING_FULL_RE = re.compile(r"(\d\.\d{1,2}|\d) \((\d+) users / (\d+) favs\)")

    def __init__(self, url: str):
        super().__init__(url.strip("-"))
        self.id_onpage: str = TsuminoExtractor.book_id_from_url(url)
        self.thumb_url: str = f"https://content.tsumino.com/thumbs/{self.id_onpage}/1"
        self.html: Optional[str] = None
        self.data: Optional[MangaExtractorData] = None

    def __repr__(self) -> str:
        if self.data:
            metastring = ', '.join((f"{k}: '{v}'" for k, v in self.data.__dict__.items()))
            return f"TsuminoExtractor('{self.url}', {metastring})"
        else:
            return f"TsuminoExtractor('{self.url}')"

    @classmethod
    def match(cls, url: str) -> bool:
        return bool(cls.URL_PATTERN_RE.match(url))

    @classmethod
    def url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        return cls.URL_FORMAT.format(id_onpage=ext_info.id_onpage)

    @classmethod
    def read_url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        return cls.READ_URL_FORMAT.format(id_onpage=ext_info.id_onpage)

    @classmethod
    def split_title(cls, value: str) -> Tuple[Optional[str], Optional[str]]:
        title = re.match(cls.TITLE_RE, value)
        title_eng: Optional[str]
        title_foreign: Optional[str]

        if title:
            title_eng = title.group(1)
            title_foreign = title.group(2)
        else:
            if is_foreign(value):
                title_eng = None
                title_foreign = value
            else:
                title_eng = value
                title_foreign = None
        return title_eng, title_foreign

    def extract(self) -> Optional[MangaExtractorData]:
        if self.data is None:
            if self.html is None:
                self.html = TsuminoExtractor.get_html(self.url)
                if not self.html:
                    logger.warning("Extraction failed! HTML was empty for url '%s'", self.url)
                    return None
            self.data = self.transform_data(TsuminoExtractor.extract_info(self.html))
        return self.data

    def transform_data(self, data_dic: Dict[str, Any]) -> MangaExtractorData:
        """
        Transform data parsed from tsumino.com into DB format
        """
        title_eng, title_foreign = self.split_title(data_dic['Title'])

        # migh be missing altogether
        uploaders: Optional[Union[str, list]] = data_dic.get('Uploader')
        if isinstance(uploaders, list):
            if len(uploaders) > 1:
                logger.info("More than one uploader: %s", data_dic['Uploader'])
            uploader = uploaders[0]
        else:
            uploader = uploaders

        rating_str = data_dic['Rating']
        rat_full = self.RATING_FULL_RE.match(rating_str)
        rating, ratings, favorites = None, None, None
        if rat_full:
            rating = float(rat_full.group(1))
            ratings = int(rat_full.group(2))
            favorites = int(rat_full.group(3))

        tags = data_dic['Tag']
        if tags is None:
            censor_id = CENSOR_IDS["Unknown"]
        else:
            if "Decensored" in tags:
                censor_id = CENSOR_IDS["Decensored"]
            elif "Uncensored" in tags:
                censor_id = CENSOR_IDS["Uncensored"]
            else:
                censor_id = CENSOR_IDS["Censored"]

        result = MangaExtractorData(
            title_eng=title_eng,
            title_foreign=title_foreign,
            language="English",
            pages=int(data_dic['Pages']),
            status_id=cast(int, STATUS_IDS["Unknown"]),
            # assume tsumino content is nsfw - there is a Non-h tag but that is no guarantee
            nsfw=1,

            note=None,

            # not every key present on every book page (e.g. "Parody", "Group"..)
            category=data_dic.get('Category', []),
            collection=data_dic.get('Collection', []),
            groups=data_dic.get('Group', []),
            artist=data_dic.get('Artist', []),
            parody=data_dic.get('Parody', []),
            character=data_dic.get('Character', []),
            tag=tags,

            # ExternalInfo data
            url=self.url,
            id_onpage=self.book_id_from_url(self.url),
            imported_from=self.site_id,
            censor_id=cast(int, censor_id),
            upload_date=datetime.datetime.strptime(data_dic['Uploaded'], "%Y %B %d").date(),

            uploader=uploader,
            rating=rating,
            ratings=ratings,
            favorites=favorites,
        )

        return result

    def get_cover(self) -> Optional[str]:
        return self.thumb_url

    @classmethod
    def extract_info(cls, html: str) -> Dict[str, Any]:
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
    def book_id_from_url(cls, url: str) -> str:
        try:
            return cast(Match, re.search(cls.URL_PATTERN_RE, url)).group(1)
        except IndexError:
            logger.warning("No book id could be extracted from \"%s\"!", url)
            # reraise or continue and check if bookid returned in usage code?
            raise
