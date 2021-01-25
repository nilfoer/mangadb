import logging
import datetime
import json
import re

from typing import cast, Match, Optional

from .base import BaseMangaExtractor
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
    API_URL_FORMAT = "https://nhentai.net/api/gallery/{id_onpage}"
    THUMB_URL_FORMAT = "https://t.nhentai.net/galleries/{media_id}/cover.{img_ext}"
    KW_LOOKP_RE_FORMAT = r"(?:\[|\(){keyword}[^)\]\n]*(?:\]|\))"

    def __init__(self, url: str):
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
    def match(cls, url: str) -> bool:
        return bool(cls.URL_PATTERN_RE.match(url))

    @classmethod
    def url_from_ext_info(cls, ext_info):
        return cls.URL_FORMAT.format(id_onpage=ext_info.id_onpage)

    @classmethod
    def read_url_from_ext_info(cls, ext_info):
        return cls.READ_URL_FORMAT.format(id_onpage=ext_info.id_onpage)

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

    def get_json_from_html(self, html):
        try:
            json_str = html.split("window._gallery = JSON.parse(\"")[1].split("\");")[0]
            # https://stackoverflow.com/questions/41466814/python-unicode-double-backslashes
            # by jsbueno <- code served as starting point
            # escaped unicode chars in gallery json e.g. \u0022 or \u005Cu3083
            # site ended up double encoding those unicode arguments
            # (\u005 is \ so the above becomes \u3083 which then becomes a japanese char)
            # first re-encode those to byte-string objects, and then decode
            # with the unicode_escape codec. For these purposes it is usefull to
            # make use of the latin1 codec as the transparent encoding: all
            # bytes in the str object are preserved in the new bytes object
            # doesnt work with these japanese chars since latin1 can't encode it
            # utf-8 can but when decoding we just get the escaped unicode back
            # for SOME characters (where the \ for escpaing the \u code has been escaped as well)
            # -> encode and decode those chars manually using utf-8 for encoding and
            # unicode-escape codec for decoding
            # OR even better just encode and decode twice utf-8/unicode-escape
            json_str = json_str.encode('utf-8').decode('unicode-escape')
            json_str = json_str.encode('utf-8').decode('unicode-escape')
            # # decode escaped unicode chars manually
            # str_list = []
            # i = 0
            # last_append = 0
            # while i < len(json_str):
            #     # check if we should expect an escaped unicode char
            #     # \u0000 -> 6 chars needed
            #     if i < (len(json_str) - 6) and (json_str[i] == "\\" and json_str[i+1] == "u"):
            #         esc_seq = json_str[i:i+6]
            #         char = esc_seq.encode("utf-8").decode("unicode-escape")
            #         print(repr(esc_seq), repr(char))
            #         # save str till last substitution with our decoded char
            #         str_list.append(json_str[last_append:i] + char)
            #         i += 6  # advance to next char that is not part of current escape sequence
            #         if i >= len(json_str):
            #             break
            #         last_append = i
            #     elif i >= (len(json_str) - 6):
            #         str_list.append(json_str[last_append:len(json_str)])
            #         break
            #     else:
            #         i += 1
            # json_str = "".join(str_list)
            # remove formatting that was inbetween: json_end});\r\n\t\tgallery.init()
        except IndexError:
            json_str = None
        if not json_str:
            logger.warning("Couldn't extract JSON string from html on %s", self.url)
        return json_str

    def get_metadata(self):
        if self.metadata is None:
            if self.json is None:
                html = NhentaiExtractor.get_html(
                        self.INFO_URL_FORMAT.format(id_onpage=self.id_onpage))
                if not html:
                    logger.warning(
                            "Extraction failed! HTML response was empty for url '%s'", self.url)
                    return None
                self.json = self.get_json_from_html(html)
                if not self.json:
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

        # assume nhentai content is nsfw - there is a Non-h tag but that is no guarantee
        result["nsfw"] = 1

        return result

    def get_cover(self) -> Optional[str]:
        if self.thumb_url is None:
            self.get_metadata()
        return self.thumb_url

    # mb move to baseclass? but mb not able to get id from url
    @classmethod
    def book_id_from_url(cls, url: str) -> int:
        try:
            return int(cast(Match, re.search(cls.URL_PATTERN_RE, url)).group(1))
        except IndexError:
            logger.warning("No book id could be extracted from \"%s\"!", url)
            # reraise or continue and check if bookid returned in usage code?
            raise
