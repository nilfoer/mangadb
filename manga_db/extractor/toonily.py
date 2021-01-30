import re
import datetime

import bs4

from typing import Dict, Tuple, Optional, TYPE_CHECKING, ClassVar, Pattern, cast, Match, Any

from .base import BaseMangaExtractor, MangaExtractorData
from ..constants import STATUS_IDS, CENSOR_IDS

if TYPE_CHECKING:
    from ..ext_info import ExternalInfo


class ToonilyExtractor(BaseMangaExtractor):
    site_name: ClassVar[str] = "Toonily"
    site_id: ClassVar[int] = 5

    URL_PATTERN_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?toonily\.com/webtoon/([-A-Za-z0-9]+)")

    BASE_URL = "https://toonily.com"
    MANGA_URL = "https://toonily.com/webtoon/{id_onpage}"

    def __init__(self, url: str):
        super().__init__(url)
        self.id_onpage: str = self.book_id_from_url(url)
        self.cover_url: Optional[str] = None
        self.export_data: Optional[MangaExtractorData] = None

    @classmethod
    def match(cls, url: str) -> bool:
        """
        Returns True on URLs the extractor is compatible with
        """
        return bool(cls.URL_PATTERN_RE.match(url))

    def extract(self) -> Optional[MangaExtractorData]:
        if self.export_data is None:
            html = self.get_html(self.url)
            if html is None:
                return None
            data_dict = self._extract_info(html)

            self.export_data = MangaExtractorData(
                pages=0,
                language='Unknown',
                collection=[],
                groups=[],
                parody=[],
                character=[],
                url=self.url,
                id_onpage=self.id_onpage,
                imported_from=ToonilyExtractor.site_id,
                uploader=None,
                upload_date=datetime.date.min,
                **data_dict)

        return self.export_data

    def _extract_info(self, html: str) -> Dict[str, Any]:
        res: Dict[str, Any] = {}

        soup = bs4.BeautifulSoup(html, "html.parser")
        cover_url = soup.select_one("div.summary_image img")
        self.cover_url = cover_url.attrs['data-src']

        res['title_eng'] = soup.select_one("div.post-title h1").text.strip()

        book_data = soup.select_one("div.summary_content")
        # labels = book_data.select("div.summary-heading")
        content = book_data.select("div.summary-content")

        # assumes order stays the same
        res['rating'] = float(content[0].select_one("#averagerate").text.strip())
        res['ratings'] = int(content[0].select_one("#countrate").text.strip())

        # sep is ','
        alt_titles = [s.strip() for s in content[2].text.split(",")]
        if alt_titles[0] == 'N/A':
            res['title_foreign'] = None
        else:
            # @Incomplete take first non-latin title; alnum() supports unicode and thus returns
            # true for """"alphanumeric"""" japanese symbols !?!?
            non_latin = [s for s in alt_titles if ord(s[0]) > 128]
            if non_latin:
                res['title_foreign'] = non_latin[0]
            else:
                res['title_foreign'] = alt_titles[0]

        authors = [s.text.strip() for s in content[3].select("a")]
        artists = [s.text.strip() for s in content[4].select("a")]
        res['artist'] = [n for n in authors if n not in artists] + artists

        tags = [a.text.strip() for a in book_data.select('div.genres-content a')]
        res['tag'] = tags
        res['nsfw'] = 'Mature' in tags
        uncensored = 'Uncensored' in tags
        res['censor_id'] = (
                CENSOR_IDS['Uncensored'] if uncensored else CENSOR_IDS['Censored'])

        # type
        res['category'] = [content[6].text.strip()]
        # OnGoing or Completed
        status_str = content[8].text.strip().capitalize()
        res['status_id'] = STATUS_IDS[status_str]

        # e.g.: 128 Users bookmarked this
        # e.g.: 128K Users bookmarked this
        favorites_str = book_data.select_one("div.add-bookmark span").text.split()[0].strip().lower()
        if 'k' in favorites_str:
            res['favorites'] = int(float(favorites_str[:-1]) * 1000)
        else:
            res['favorites'] = int(favorites_str)


        summary = soup.select_one("div.description-summary div.summary__content").text.strip()
        # @CleanUp
        res['note'] = f"{'Summary: ' if not uncensored else ''}{summary}"

        return res

    def get_cover(self) -> Optional[str]:
        return self.cover_url

    @classmethod
    def book_id_from_url(cls, url: str) -> str:
        # guaranteed match since we only get passed matching urls
        match = cast(Match, cls.URL_PATTERN_RE.match(url))
        return match.group(1)

    @classmethod
    def url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        return cls.MANGA_URL.format(id_onpage=ext_info.id_onpage)

    @classmethod
    def read_url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        # @CleanUp just uses first chapter
        return f"{cls.url_from_ext_info(ext_info)}/chapter-1"
