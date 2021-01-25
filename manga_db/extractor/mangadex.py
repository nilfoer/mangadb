import re
import json
import datetime
import logging
import time

from typing import cast, Match, Optional, Dict, Any, Tuple, Pattern, ClassVar, List, TYPE_CHECKING

from .base import BaseMangaExtractor
from ..constants import CENSOR_IDS, STATUS_IDS

if TYPE_CHECKING:
    from ..ext_info import ExternalInfo

logger = logging.getLogger(__name__)


class MangaDexExtractor(BaseMangaExtractor):
    site_name = "MangaDex"
    site_id = 3

    # MangaDex said official domains are mangadex.com|org|cc but com redirects
    # somewhere else
    URL_PATTERN_RE: Pattern = re.compile(
            r"(?:https?://)?(?:www\.)?mangadex\.(?:org|cc)/(?:title|manga)/(\d+)(?:/([-a-z0-9]+))?")

    BASE_URL: ClassVar[str] = "https://mangadex.org"
    BASE_API_URL: ClassVar[str] = "https://api.mangadex.org/v2"

    STATUS_MAP: ClassVar[List[int]] = [
        # 0
        cast(int, STATUS_IDS['Unknown']),
        # 1 == Ongoing
        cast(int, STATUS_IDS['Ongoing']),
        # 2 == Completed
        cast(int, STATUS_IDS['Completed']),
        # 3 == Cancelled
        cast(int, STATUS_IDS['Cancelled']),
        # 4 == Hiatus
        cast(int, STATUS_IDS['Hiatus']),
    ]

    DEMOGRAPHIC_MAP: ClassVar[List[Optional[str]]] = [
        None,
        # 1
        'Shounen',
        # 2
        'Shoujo',
        # 3
        'Seinen',
        # 4
        'Josei',
    ]

    # fetched from mangadex api when we use MangaDexExtractor the first time
    # so we don't have to fetch it for every manga or query for every tag name
    # one by one
    _tag_map: ClassVar[Optional[Dict[int, Dict[str, Any]]]] = None
    _tag_map_tries_left: ClassVar[int] = 3

    id_onpage: int
    escaped_title: Optional[str]
    api_reponse: Optional[Dict[str, Any]]

    def __init__(self, url: str):
        super().__init__(url)
        match = cast(Match, self.URL_PATTERN_RE.match(url))
        self.id_onpage = int(match.group(1))
        if len(match.groups()) > 1:
            self.escaped_title = match.group(2)
        else:
            self.escaped_title = None
        self.api_reponse = None

    @classmethod
    def manga_url_from_id(cls, id: int, escaped_title: Optional[str] = None) -> str:
        if escaped_title:
            return f"{cls.BASE_URL}/title/{id}/{escaped_title}"
        else:
            return f"{cls.BASE_URL}/title/{id}"

    @classmethod
    def match(cls, url: str) -> bool:
        return bool(cls.URL_PATTERN_RE.match(url))

    @classmethod
    def _get_tag_map(cls) -> Optional[Dict[int, Dict[str, Any]]]:
        if not cls._tag_map:
            api_url = f"{cls.BASE_API_URL}/tag"
            response = cls.get_html(api_url)
            if response:
                tag_dict = json.loads(response)
                if tag_dict['code'] != 200:
                    return None
                # returns sequential? string keys?
                cls._tag_map = {int(k): v for k, v in tag_dict['data'].items()}

        return cls._tag_map

    def get_metadata(self) -> Optional[Dict[str, Any]]:
        if not self.api_reponse:
            self.api_reponse = self._get_manga_json()
            if not self.api_reponse:
                return None

        # getting the tag map fails sporadicly with error 500
        tag_map = None
        while tag_map is None and MangaDexExtractor._tag_map_tries_left > 0:
            tag_map = MangaDexExtractor._get_tag_map()
            MangaDexExtractor._tag_map_tries_left -= 1
            time.sleep(0.5)
        if tag_map is None:
            logger.warning("Failed to get tag map from MangaDex after 3 tries. "
                           "Import aborted since Books would be without tags. Try again "
                           "at a later time or submit a github issue if this error "
                           "keeps happening!")
            return None

        manga_data = self.api_reponse['data']

        result = {
            'imported_from': self.site_id,
            'url': self.manga_url_from_id(self.id_onpage, self.escaped_title),
            'id_onpage': self.id_onpage,
            'title_eng': manga_data['title'],
            # TODO @CleanUp contains bbcode
            'note': f"Description: {manga_data['description']}",
            # @CleanUp mb add volumes/chapters?
            'pages': 0,
            # use follows as favories
            'favorites': manga_data['follows'],
            # MangaDex uses max 10 rating
            'rating': (manga_data['rating']['bayesian'] / 2
                       if manga_data['rating']['bayesian'] > 0 else 0.0),
            'ratings': manga_data['rating']['users'],
            'uploader': None,
            # @CleanUp cant be None due to db constraint; use min date for now
            'upload_date': datetime.date.min,
            'tag': [],
            'censor_id': CENSOR_IDS['Unknown'],
            'language': ABBR_LANG_MAP.get(manga_data['publication']['language'], 'Unknown'),
            'status_id': self.STATUS_MAP[manga_data['publication']['status']],
            # deduplicate if author and artist are the same
            'artist': list(set(manga_data['artist']).union(manga_data['author'])),
            'category': ['Manga'],
            'character': [],
            'groups': [],
            'parody': [],
        }
        if 'altTitles' in manga_data and manga_data['altTitles']:
            # multiple titles with no way to easy way to get the language
            # jp seems to be last mostly so use that
            result['title_foreign'] = manga_data['altTitles'][-1]
        if tag_map:
            result['tag'] = [
                    tag_map[mdex_tag_id]['name'] for mdex_tag_id in manga_data['tags']]

            # demographic 0 in api means none assigned
            demographic_tag = self.DEMOGRAPHIC_MAP[manga_data['publication']['demographic']]
            if demographic_tag is not None:
                result['tag'].append(demographic_tag)

        return result

    def get_cover(self) -> Optional[str]:
        if not self.api_reponse:
            self.api_reponse = self._get_manga_json()
            if not self.api_reponse:
                return None

        # might have different extension
        # return f"{self.BASE_URL}/images/manga/{self.id_onpage}.jpg"
        return self.api_reponse['data']['mainCover']

    @classmethod
    def book_id_from_url(cls, url: str) -> int:
        return int(cast(Match, cls.URL_PATTERN_RE.match(url)).group(1))

    @classmethod
    def url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        return cls.manga_url_from_id(ext_info.id_onpage)

    @classmethod
    def read_url_from_ext_info(cls, ext_info: 'ExternalInfo') -> str:
        # read url requires specific chapter id
        return "#"

    def _get_manga_json(self) -> Optional[Dict[str, Any]]:
        manga_api_url = f"{self.BASE_API_URL}/manga/{self.id_onpage}"

        response = self.get_html(manga_api_url)
        if response:
            pass
        else:
            return None

        manga_dict = json.loads(response)
        if manga_dict['code'] != 200:
            return None

        return manga_dict


ABBR_LANG_MAP = {
    # abbr -> lang
    'sa': "Arabic",
    'bd': "Bengali",
    'bg': "Bulgarian",
    'mm': "Burmese",
    'ct': "Catalan",
    # mangadex tracks specific language versions, 'base language' is good enough for us
    'cn': "Chinese",  # "Chinese (Simp)",
    'hk': "Chinese",  # "Chinese (Trad)",
    'cz': "Czech",
    'dk': "Danish",
    'nl': "Dutch",
    'gb': "English",
    'ph': "Filipino",
    'fi': "Finnish",
    'fr': "French",
    'de': "German",
    'gr': "Greek",
    'hu': "Hungarian",
    'id': "Indonesian",
    'it': "Italian",
    'jp': "Japanese",
    'kr': "Korean",
    'lt': "Lithuanian",
    'my': "Malay",
    'mn': "Mongolian",
    'ir': "Persian",
    'pl': "Polish",
    'br': "Portuguese",  # "Portuguese (Br)",
    'pt': "Portuguese",  # "Portuguese (Pt)",
    'ro': "Romanian",
    'ru': "Russian",
    'rs': "Serbo-Croatian",
    'es': "Spanish",  # "Spanish (Es)",
    'mx': "Spanish",  # "Spanish (LATAM)",
    'se': "Swedish",
    'th': "Thai",
    'tr': "Turkish",
    'ua': "Ukrainian",
    'vn': "Vietnamese",

}
