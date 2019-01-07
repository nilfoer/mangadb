import logging
import datetime
import json
import re

from .base import BaseMangaExtractor
from ..constants import CENSOR_IDS, STATUS_IDS

logger = logging.getLogger(__name__)


class NhentaiExtractor(BaseMangaExtractor):
    site_name = "nhentai.net"
    site_id = 2
    URL_PATTERN_RE = re.compile(r"^(?:https?://)?(?:www\.)?nhentai\.net/g/(\d+)/?")
    ID_ONPAGE_RE = re.compile(r"nhentai\.net/g/(\d+)/?")
    # grp 1 is prob contained magazine?/vol? grp 2 is title
    TITLE_RE = re.compile(r"^(\(.+?\))? ?(?:\[.+?\])? ?([^\[(]+)")
    API_URL_FORMAT = "https://nhentai.net/api/gallery/{id_onpage}"
    THUMB_URL_FORMAT = "https://t.nhentai.net/galleries/{media_id}/cover.{img_ext}"
    READ_URL_FORMAT = "https://nhentai.net/g/{id_onpage}/1/"
    KW_LOOKP_RE_FORMAT = r"(?:\[|\(){keyword}[^)\]\n]*(?:\]|\))"

    def __init__(self, url):
        super().__init__(url)
        self.id_onpage = NhentaiExtractor.book_id_from_url(url)
        self.thumb_url = None
        self.json = None
        self.metadata = None

    def __repr__(self):
        if self.metadata:
            metastring = ', '.join((f"{k}: '{v}'" for k, v in self.metadata.items()))
            return f"NhentaiExtractor('{self.url}', {metastring})"
        else:
            return f"NhentaiExtractor('{self.url}')"

    @classmethod
    def read_url_from_id_onpage(cls, id_onpage):
        return cls.READ_URL_FORMAT.format(id_onpage=id_onpage)

    def build_cover_url(self):
        img_type = self.json["images"]["cover"]["t"]
        if img_type == "j":
            img_ext = "jpg"
        elif img_type == "p":
            img_ext = "png"
        else:
            logger.error("Didn't recognize nhentai's image type: %s", img_type)
            return None
        return self.THUMB_URL_FORMAT.format(media_id=self.json["media_id"], img_ext=img_ext)

    def get_metadata(self):
        if self.metadata is None:
            if self.json is None:
                self.json = NhentaiExtractor.get_html(
                        self.API_URL_FORMAT.format(id_onpage=self.id_onpage))
                if not self.json:
                    logger.warning(
                            "Extraction failed! JSON response was empty for url '%s'", self.url)
                    return None
                self.json = json.loads(self.json)
            self.thumb_url = self.build_cover_url()
            self.metadata = self.transform_metadata(self.json)
        return self.metadata

    @staticmethod
    def search_nhent_tagname(metadata, name):
        return any(tag for tag in metadata["tags"] if tag["name"] == name)

    @staticmethod
    def tags_of_type(metadata, type_name):
        # MangaDB style if titelized tags etc.: chun-li -> Chun-Li, big ass -> Big Ass
        return ["-".join(tn.title() for tn in tag["name"].split("-"))
                for tag in metadata["tags"] if tag["type"] == type_name]

    def transform_metadata(self, metadata):
        """
        Transform metadata parsed from tsumino.com into DB format
        """
        result = {}
        result["imported_from"] = self.site_id
        result["url"] = self.url
        result["id_onpage"] = self.id_onpage

        title_eng = metadata["title"]["english"]
        title_foreign = metadata["title"]["japanese"]
        if title_eng:
            title_eng_cleaned = self.TITLE_RE.match(title_eng).group(2).strip()
            result["title_eng"] = title_eng_cleaned
        if title_foreign:
            title_foreign_cleaned = self.TITLE_RE.match(title_foreign).group(2).strip()
            result["title_foreign"] = title_foreign_cleaned
        result["note"] = (f"Full titles on nhentai.net: English '{title_eng}' "
                          f"Foreign '{title_foreign}'")
        result["pages"] = metadata["num_pages"]
        result["favorites"] = metadata["num_favorites"]

        if "upload_date" in metadata:
            upload_date = metadata["upload_date"]
        else:
            # else instead elif since we want it to fail if its not in images either
            upload_date = metadata["images"]["upload_date"]
        result["upload_date"] = datetime.date.fromtimestamp(int(upload_date))

        for status_kw in ("Completed", "Ongoing"):
            if re.search(self.KW_LOOKP_RE_FORMAT.format(keyword=status_kw),
                         metadata["title"]["english"], re.IGNORECASE):
                result["status_id"] = STATUS_IDS[status_kw]
                break
        else:
            result["status_id"] = STATUS_IDS["Unknown"]

        result["tag"] = self.tags_of_type(metadata, "tag")
        result["artist"] = self.tags_of_type(metadata, "artist")
        result["category"] = self.tags_of_type(metadata, "category")
        result["character"] = self.tags_of_type(metadata, "character")
        result["groups"] = self.tags_of_type(metadata, "group")
        result["parody"] = self.tags_of_type(metadata, "parody")

        uncensored = self.search_nhent_tagname(metadata, "uncensored")
        if uncensored:
            if re.search(self.KW_LOOKP_RE_FORMAT.format(keyword="decensored"),
                         metadata["title"]["english"], re.IGNORECASE):
                result["censor_id"] = CENSOR_IDS["Decensored"]
            else:
                result["censor_id"] = CENSOR_IDS["Uncensored"]
        else:
            result["censor_id"] = CENSOR_IDS["Censored"]

        if self.search_nhent_tagname(metadata, "english"):
            result["language"] = "English"
        elif self.search_nhent_tagname(metadata, "japanese"):
            result["language"] = "Japanese"
        elif self.search_nhent_tagname(metadata, "chinese"):
            result["language"] = "Chinese"
        else:
            result["language"] = "Unknown"

        return result

    def get_cover(self):
        return self.thumb_url

    # mb move to baseclass? but mb not able to get id from url
    @classmethod
    def book_id_from_url(cls, url):
        try:
            return int(re.search(cls.ID_ONPAGE_RE, url).group(1))
        except IndexError:
            logger.warning("No book id could be extracted from \"%s\"!", url)
            # reraise or continue and check if bookid returned in usage code?
            raise
