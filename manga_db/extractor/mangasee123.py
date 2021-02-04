import re
import datetime
import json

import bs4

from typing import Dict, Tuple, Optional, TYPE_CHECKING, ClassVar, cast, Match, Final, List

from .base import BaseMangaExtractor, MangaExtractorData
from ..constants import STATUS_IDS, CENSOR_IDS, LANG_IDS

if TYPE_CHECKING:
    from ..ext_info import ExternalInfo


class MangaSee123Extractor(BaseMangaExtractor):
    # headers that get added when the class makes a request
    # will overwrite default headers from the opener
    add_headers: Dict[str, str] = {}

    # these need to be re-defined by sub-classes!!
    # they are not allowed to changed after the extractor has been added
    # doing so would require a db migration
    site_name: ClassVar[str] = "MangaSee123"
    site_id: ClassVar[int] = 6

    URL_PATTERN_RE = re.compile(
        r"(?:https?://)?(?:www\.)?mangasee123\.com/(manga|read-online)/([-A-Za-z0-9]+)")

    BASE_URL: Final[str] = "https://mangasee123.com"
    MANGA_URL: Final[str] = "https://mangasee123.com/manga/{id_onpage}"
    READ_URL: Final[str] = ("https://mangasee123.com/read-online/{id_onpage}-"
                            "chapter-{chap}-page-{page}.html")

    STATUS_MAP: Final[Dict[str, int]] = {
        "Cancelled": STATUS_IDS['Cancelled'],
        "Complete": STATUS_IDS['Completed'],
        "Discontinued": STATUS_IDS['Cancelled'],
        "Hiatus": STATUS_IDS['Hiatus'],
        "Ongoing": STATUS_IDS['Ongoing'],
    }

    id_onpage: str
    cover_url: Optional[str]
    export_data: Optional[MangaExtractorData]

    def __init__(self, url: str):
        # get id_onpage first since we accept chapter urls
        self.id_onpage = self.book_id_from_url(url)
        # re-build url from id_onpage
        super().__init__(self.MANGA_URL.format(id_onpage=self.id_onpage))
        self.cover_url = None
        self.export_data = None

    @classmethod
    def match(cls, url: str) -> bool:
        """
        Returns True on URLs the extractor is compatible with
        """
        return bool(cls.URL_PATTERN_RE.match(url))

    def extract(self) -> Optional[MangaExtractorData]:
        if self.export_data is not None:
            return self.export_data

        html = self.get_html(self.url)
        soup = bs4.BeautifulSoup(html, "html.parser")

        # cover_img = soup.select_one("div.BoxBody > .row > div > img")
        # self.cover_url = cover_img['src']
        # or use https://cover.nep.li/cover/{{Series.IndexName}}.jpg (id_onpage)
        self.cover_url = f"https://cover.nep.li/cover/{self.id_onpage}.jpg"

        # the html that we get from the server still has a lot of unprocessed template code
        # but data is available in script tags
        json_str = soup.select_one('script[type="application/ld+json"]').get_text(strip=True)
        main_data = json.loads(json_str)['mainEntity']

        # can we even trust this at all now?!?!
        title_eng = main_data['name']
        tag: List[str] = main_data['genre']

        # apparently the author in the json data is not always complete!??!?!
        # artist: List[str] = main_data['author']
        artist_start = html.index(">Author(s):</span>") + 18  # 18 len of srch str
        # closing </li> is just a </i> -> use next <li
        artist_end = html.index("<li", artist_start)
        artist = [anch.get_text(strip=True) for anch in
                  bs4.BeautifulSoup(html[artist_start:artist_end], "html.parser").select("a")]

        fav_start = html.index("vm.NumSubs = ");
        # 2nd param=start searching from fav_start
        fav_end = html.index(";", fav_start);
        favorites = int(html[fav_start + 13:fav_end])

        type_start = html.index(">Type:</span>") + 13  # 13 len of srch str
        # closin </li> is just a </i> -> use next <li
        type_end = html.index("<li", type_start)
        category = [anch.get_text(strip=True) for anch in
                    bs4.BeautifulSoup(html[type_start:type_end], "html.parser").select("a")]

        status_start = html.index(">Status:</span>") + 15  # 15 len of srch str
        status_end = html.index("<li", status_start)
        statuses = [anch.get_text(strip=True) for anch in
                    bs4.BeautifulSoup(html[status_start:status_end], "html.parser").select("a")]
        for stat in statuses:
            if ' (Publish)' in stat:
                status_id = MangaSee123Extractor.STATUS_MAP[stat[:-10]]
                break
        else:
            status_id = MangaSee123Extractor.STATUS_MAP[statuses[0][:-7]]

        descr = soup.select_one("li.list-group-item > div.Content").get_text(strip=True)
        note = f"Description: {descr}"

        if 'Adult' in tag or 'Ecchi' in tag or 'Hentai' in tag:
            nsfw = 1
        else:
            nsfw = 0

        self.export_data = MangaExtractorData(
            title_eng=title_eng,
            title_foreign=None,
            language='English',
            pages=0,
            status_id=status_id,
            nsfw=nsfw,

            note=note,

            category=category,
            collection=[],
            groups=[],
            artist=artist,
            parody=[],
            character=[],
            tag=tag,

            # ExternalInfo data
            url=MangaSee123Extractor.MANGA_URL.format(id_onpage=self.id_onpage),
            id_onpage=self.id_onpage,
            imported_from=MangaSee123Extractor.site_id,
            censor_id=CENSOR_IDS['Unknown'],
            upload_date=datetime.date.min,

            uploader=None,
            rating=None,
            ratings=None,
            favorites=favorites,
        )

        return self.export_data

    def get_cover(self) -> Optional[str]:
        if self.export_data is None:
            self.extract()
        return self.cover_url

    @classmethod
    def book_id_from_url(cls, url: str) -> str:
        match = cast(Match, cls.URL_PATTERN_RE.match(url))
        subpath, id_or_html = match.groups()
        id_onpage: str
        if subpath == "read-online":
            id_onpage, _ = id_or_html.split("-chapter-")
            # chap_id_str, page_html = chap_page_file.split("-page-")
            # # remove .html suffix
            # page_id_str = page_html[:-5]
        else:
            id_onpage = id_or_html
        return id_onpage

    @classmethod
    def url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        return cls.MANGA_URL.format(id_onpage=ext_info.id_onpage)

    @classmethod
    def read_url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        # always returns chap1 pg1
        return cls.READ_URL.format(id_onpage=ext_info.id_onpage, chap=1, page=1)
