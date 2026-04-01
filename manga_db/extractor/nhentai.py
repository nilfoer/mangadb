import logging
import datetime
import json
import re

import bs4

from typing import cast, Match, Optional, Dict, Any

from .base import BaseMangaExtractor, MangaExtractorData
from ..constants import CENSOR_IDS, STATUS_IDS

logger = logging.getLogger(__name__)


class NhentaiExtractor(BaseMangaExtractor):
    site_name = "nhentai.net"
    site_id = 2
    URL_PATTERN_RE = re.compile(r"^(?:https?://)?(?:www\.)?nhentai\.net/g/(\d+)/?")
    URL_FORMAT = "https://nhentai.net/g/{id_onpage}/"
    READ_URL_FORMAT = "https://nhentai.net/g/{id_onpage}/1/"

    # grp 1 is prob contained magazine?/vol? grp 2 is title
    TITLE_RE = re.compile(r"^(?:\[.+?\])? ?(\(.+?\))? ?(?:\[.+?\])? ?([^\[(]+)")
    INFO_URL_FORMAT = "https://nhentai.net/g/{id_onpage}/"
    API_URL_FORMAT = "https://nhentai.net/api/v2/galleries/{id_onpage}"
    KW_LOOKP_RE_FORMAT = r"(?:\[|\(){keyword}[^)\]\n]*(?:\]|\))"

    DEFAULT_THUMB_MIRROR = "https://t1.nhentai.net/"

    def __init__(self, url: str):
        super().__init__(url)
        self.id_onpage = NhentaiExtractor.book_id_from_url(url)
        self.thumb_url: Optional[str] = None
        self.json: Optional[Dict[str, Any]] = None
        self.data: Optional[MangaExtractorData] = None

    def __repr__(self):
        if self.data:
            metastring = ', '.join((f"{k}: '{v}'" for k, v in self.data.__dict__.items()))
            return f"NhentaiExtractor('{self.url}', {metastring})"
        else:
            return f"NhentaiExtractor('{self.url}')"

    @classmethod
    def match(cls, url: str) -> bool:
        return bool(cls.URL_PATTERN_RE.match(url))

    @classmethod
    def url_from_ext_info(cls, ext_info):
        return cls.URL_FORMAT.format(id_onpage=ext_info.id_onpage)

    @classmethod
    def read_url_from_ext_info(cls, ext_info):
        return cls.READ_URL_FORMAT.format(id_onpage=ext_info.id_onpage)

    def build_cover_url(self) -> str:
        assert self.json

        path = self.json["cover"]["path"]
        return f"{self.DEFAULT_THUMB_MIRROR}{path}"

    def extract(self) -> Optional[MangaExtractorData]:
        if self.data is None:
            if self.json is None:
                json_str = NhentaiExtractor.get_html(
                        self.API_URL_FORMAT.format(id_onpage=self.id_onpage))
                if not json_str:
                    logger.warning(
                            "Extraction failed! JSON response was empty for url '%s'", self.url)
                    return None

                self.json = json.loads(json_str)

            self.thumb_url = self.build_cover_url()
            self.data = self.transform_data(self.json)
        return self.data

    @staticmethod
    def search_nhent_tagname(data: Dict[str, Any], name: str):
        return any(tag for tag in data["tags"] if tag["name"] == name)

    @staticmethod
    def tags_of_type(data: Dict[str, Any], type_name: str):
        # MangaDB style if titelized tags etc.: chun-li -> Chun-Li, big ass -> Big Ass
        return ["-".join(tn.title() for tn in tag["name"].split("-"))
                for tag in data["tags"] if tag["type"] == type_name]

    def transform_data(self, data: Dict[str, Any]) -> MangaExtractorData:
        """
        Transform data parsed from tsumino.com into DB format
        """
        upload_date = data["upload_date"]

        title_eng = data["title"]["english"]
        title_eng_cleaned = data["title"]["pretty"]
        title_foreign = data["title"]["japanese"]
        title_foreign_cleaned = title_foreign
        # extract titles, full title inlcuding artist, group etc. will be saved as note
        if title_eng:
            title_eng_match = self.TITLE_RE.match(title_eng)
            if title_eng_match:
                title_eng_cleaned = title_eng_match.group(2).strip()
        if title_foreign:
            title_foreign_match = self.TITLE_RE.match(title_foreign)
            if title_foreign_match:
                title_foreign_cleaned = title_foreign_match.group(2).strip()

        result = MangaExtractorData(
            title_eng = title_eng_cleaned,
            title_foreign = title_foreign_cleaned,
            language = "Unknown",
            pages = data["num_pages"],
            status_id = cast(int, STATUS_IDS['Unknown']),
            # assume nhentai content is nsfw - there is a Non-h tag but that is no guarantee
            nsfw = 1,

            note = f"Full titles on nhentai.net: English '{title_eng}' "
                   f"Foreign '{title_foreign}'",

            category = self.tags_of_type(data, "category"),
            collection = [],
            groups = self.tags_of_type(data, "group"),
            artist = self.tags_of_type(data, "artist"),
            parody = self.tags_of_type(data, "parody"),
            character = self.tags_of_type(data, "character"),
            tag = self.tags_of_type(data, "tag"),

            # ExternalInfo data
            url = self.url,
            id_onpage = self.id_onpage,
            imported_from = self.site_id,
            censor_id = cast(int, CENSOR_IDS['Unknown']),
            upload_date = datetime.date.fromtimestamp(int(upload_date)),

            uploader = None,
            rating = None,
            ratings = None,
            favorites = data["num_favorites"],
        )

        for status_kw in ("Completed", "Ongoing"):
            if re.search(self.KW_LOOKP_RE_FORMAT.format(keyword=status_kw),
                         data["title"]["english"], re.IGNORECASE):
                result.status_id = cast(int, STATUS_IDS[status_kw])
                break

        uncensored = self.search_nhent_tagname(data, "uncensored")
        if uncensored:
            if re.search(self.KW_LOOKP_RE_FORMAT.format(keyword="decensored"),
                         data["title"]["english"], re.IGNORECASE):
                result.censor_id = cast(int, CENSOR_IDS["Decensored"])
            else:
                result.censor_id = cast(int, CENSOR_IDS["Uncensored"])
        else:
            result.censor_id = cast(int, CENSOR_IDS["Censored"])

        if self.search_nhent_tagname(data, "english"):
            result.language = "English"
        elif self.search_nhent_tagname(data, "japanese"):
            result.language = "Japanese"
        elif self.search_nhent_tagname(data, "chinese"):
            result.language = "Chinese"

        return result

    def get_cover(self) -> Optional[str]:
        if self.thumb_url is None:
            self.extract()
        return self.thumb_url

    # mb move to baseclass? but mb not able to get id from url
    @classmethod
    def book_id_from_url(cls, url: str) -> str:
        try:
            return cast(Match, re.search(cls.URL_PATTERN_RE, url)).group(1)
        except IndexError:
            logger.warning("No book id could be extracted from \"%s\"!", url)
            # reraise or continue and check if bookid returned in usage code?
            raise
