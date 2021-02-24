import datetime
import logging
import json
import pytest
import os.path

from typing import Dict, Any, Set

from manga_db.manga_db import update_cookies_from_file
from manga_db.extractor.base import BaseMangaExtractor, MangaExtractorData
from manga_db.extractor.tsumino import TsuminoExtractor
from manga_db.extractor.nhentai import NhentaiExtractor
from manga_db.extractor.mangadex import MangaDexExtractor
from manga_db.extractor.manganelo import ManganeloExtractor
from manga_db.extractor.toonily import ToonilyExtractor
from manga_db.extractor.mangasee123 import MangaSee123Extractor
from manga_db.constants import CENSOR_IDS, STATUS_IDS

from utils import build_testsdir_furl, TESTS_DIR


# NOTE: IMPORTANT extractor tests that test sites that require special cookies to succeed
# should be marked with @pytest.mark.requires_cookies
# and should load the cookies file tests\cookies.txt themselves
# update_cookies_from_file(os.path.join(TESTS_DIR, 'cookies.txt'))


minimal_extr_data = {
    "title_eng": "Negimatic Paradise! 05'",
    "title_foreign": None,
    "language": "English",
    "pages": 0,
    "status_id": 1,
    "nsfw": 0,

    "note": None,

    "category": [],
    "collection": [],
    "groups": [],
    "artist": [],
    "parody": [],
    "character": [],
    "tag": [],
    
    "url": "https://www.tsumino.com/entry/43357",
    "id_onpage": '43357',
    "imported_from": 1,
    "censor_id": 1,
    "upload_date": datetime.date.min,

    "uploader": None,
    "rating": None,
    "ratings": None,
    "favorites": None,
}

def test_extractor_data_at_least_one_title():
    src = minimal_extr_data.copy() 

    MangaExtractorData(**src)
    src['title_eng'] = None
    src['title_foreign'] = 'Foreign'
    MangaExtractorData(**src)

    src['title_eng'] = None
    src['title_foreign'] = None
    with pytest.raises(AssertionError):
        MangaExtractorData(**src)

    src['title_eng'] = ""
    src['title_foreign'] = ""
    with pytest.raises(AssertionError):
        MangaExtractorData(**src)


def test_extractor_data_tags_capitalized():
    src = minimal_extr_data.copy() 
    src['category'] = ['This was capitalized', 'title']
    src['collection'] = ['This was capitalized', 'title']
    src['groups'] = ['This was capitalized', 'title']
    src['artist'] = ['This was capitalized', 'title']
    src['parody'] = ['This was capitalized', 'title']
    src['character'] = ['This was capitalized', 'title']
    src['tag'] = ['This was capitalized', 'title']

    med = MangaExtractorData(**src)
    # site_id 1 is in FORCE_TITLECASE_EXCEPTIONS so case should be the same
    assert src == vars(med)

    src['imported_from'] = 2
    med = MangaExtractorData(**src)

    assert med.category     == ['This Was Capitalized', 'Title']
    assert med.collection   == ['This Was Capitalized', 'Title']
    assert med.groups       == ['This Was Capitalized', 'Title']
    assert med.artist       == ['This Was Capitalized', 'Title']
    assert med.parody       == ['This Was Capitalized', 'Title']
    assert med.character    == ['This Was Capitalized', 'Title']
    assert med.tag          == ['This Was Capitalized', 'Title']


manual_tsumino = {
        "url": "https://www.tsumino.com/entry/43357",
        "pages": 23,
        "id_onpage": '43357',
        "rating": 4.57,
        "ratings": 7,
        "favorites": 211,
        "uploader": "nekoanime15",
        "upload_date": datetime.datetime.strptime("2018-10-07", "%Y-%m-%d").date(),
        "title_eng": "Negimatic Paradise! 05'",
        "title_foreign": "ネギまちっく天国05'",
        "tag": ["Cosplay", "Large Breasts", "Mind Control", "Multi-Part", "Nakadashi", "Rape",
                "Sleeping", "Straight Shota", "Sweating", "Teacher", "Wings"],
        "censor_id": 2,
        "language": "English",
        "status_id": 1,
        "imported_from": 1,
        "category": ["Doujinshi"],
        "collection": ["Negimatic Paradise!"],
        "groups": ["Gakuen Yuushabu"],
        "artist": ["Tsurugi Yasuyuki"],
        "parody": ["Mahou Sensei Negima! / 魔法先生ネギま！"],
        "character": ["Ayaka Yukihiro", "Negi Springfield"],
        "nsfw": 1,
        "note": None,
        }


def test_extr_tsu(monkeypatch, caplog):
    url = "https://www.tsumino.com/entry/43357"
    t = TsuminoExtractor(url)
    t.html = TsuminoExtractor.get_html(
            build_testsdir_furl("extr_files/tsumino_43357_negimatic-paradise-05-05.html"))
    res = t.extract()

    assert res == MangaExtractorData(**manual_tsumino)
    assert t.get_cover() == "https://content.tsumino.com/thumbs/43357/1"

    # test no data receieved
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: None)
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover",
                        lambda x: None)
    caplog.clear()
    t = TsuminoExtractor(url)
    assert t.extract() is None
    assert caplog.record_tuples == [
            ("manga_db.extractor.tsumino", logging.WARNING,
             # url without last dash
             f"Extraction failed! HTML was empty for url '{url}'"),
            ]


def test_extr_tsu_bookidfromurl():
    urls = {
            "http://www.tsumino.com/entry/43357": '43357',
            "http://www.tsumino.com/entry/1337": '1337',
            "http://www.tsumino.com/Read/Index/43357": '43357',
            "http://www.tsumino.com/Read/Index/1337": '1337',
            }
    for u, i in urls.items():
        assert TsuminoExtractor.book_id_from_url(u) == i


manual_nhentai = {
        "url": "https://nhentai.net/g/77052/",
        "pages": 26,
        "id_onpage": '77052',
        "favorites": 6865,
        "upload_date": datetime.datetime.strptime("2014-06-29", "%Y-%m-%d").date(),
        "title_eng": "Zecchou Trans Poison",
        "title_foreign": "絶頂トランスポイズン",
        "tag": ['Futanari', 'Transformation', 'Big Breasts', 'Pregnant', 'Big Ass',
                'Anal', 'Crossdressing', 'Shemale', 'Yuri', 'Lactation',
                'Hotpants', 'Impregnation', 'Gender Bender', 'Shotacon', 'Deepthroat',
                'Autofellatio', 'Dickgirl On Dickgirl', 'Dickgirl On Male', 'Prostate Massage'],
        "censor_id": 2,
        "language": "English",
        "status_id": 1,
        "imported_from": 2,
        "category": ["Doujinshi"],
        "groups": ["Arsenothelus"],
        "artist": ["Rebis", "Chinbotsu"],
        "parody": ["Street Fighter", "Tekken", "Final Fight"],
        "character": ['Lili Rochefort', 'Ibuki', 'Cammy White', 'Poison',
                      'Asuka Kazama', 'Chun-Li'],
        'note': ("Full titles on nhentai.net: English '(Futaket 8) [Arsenothelus "
                 "(Rebis, Chinbotsu)] Zecchou Trans Poison (Street Fighter X Tekken) "
                 "[English] [Pineapples R' Us + Doujin-Moe.us]' Foreign '(ふたけっと8) "
                 "[アルセノテリス (Rebis＆沈没)] 絶頂トランスポイズン "
                 "(ストリートファイター×鉄拳) [英訳]'"),
        'nsfw': 1,
        'collection': [],
        'uploader': None,
        'rating': None,
        'ratings': None,
        }


def test_extr_nhent(monkeypatch, caplog):
    # decensored, ongoing in title
    url = "https://nhentai.net/g/77052/"
    t = NhentaiExtractor(url)
    t.json = json.loads(t.get_json_from_html(
        NhentaiExtractor.get_html(build_testsdir_furl("extr_files/nhentai_251287.html"))))
    res = t.extract()
    assert res.censor_id == CENSOR_IDS["Decensored"]
    assert res.status_id == STATUS_IDS["Ongoing"]

    t = NhentaiExtractor(url)
    html_str = NhentaiExtractor.get_html(build_testsdir_furl("extr_files/nhentai_77052.html"))
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html",
                        lambda x: html_str)
    res = t.extract()

    assert res == MangaExtractorData(**manual_nhentai)
    assert t.get_cover() == "https://t.nhentai.net/galleries/501421/cover.jpg"

    # test no data receieved
    args = []
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html",
                        lambda x: args.append(x))
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover",
                        lambda x: None)
    caplog.clear()
    t = NhentaiExtractor(url)
    assert t.extract() is None
    assert args == ["https://nhentai.net/g/77052/"]
    assert caplog.record_tuples == [
            ("manga_db.extractor.nhentai", logging.WARNING,
             # url without last dash
             f"Extraction failed! HTML response was empty for url '{url}'"),
            ]


def test_extr_nhentai_bookid_from_url():
    urls = {
            "https://nhentai.net/g/77052/": '77052',
            "https://nhentai.net/g/97725/": '97725',
            "https://nhentai.net/g/158268/": '158268'
            }
    for u, i in urls.items():
        assert NhentaiExtractor.book_id_from_url(u) == i


@pytest.mark.parametrize('inp, expected', [
    ('https://mangadex.org/title/358239/escaped-title-123', '358239'),
    ('https://www.mangadex.org/title/12464/escaped-title-123', '12464'),
    ('https://mangadex.cc/title/358239/escaped-title-123', '358239'),
    ('http://mangadex.org/title/358239/escaped-title-123', '358239'),
    ('https://mangadex.cc/title/358239', '358239'),
    ])
def test_extr_mangadex_bookid_from_url(inp, expected):
    assert MangaDexExtractor.book_id_from_url(inp) == expected


manual_mangadex = {
        "url": "https://mangadex.org/title/111/escaped-title-123",
        "pages": 0,
        "id_onpage": '111',
        "rating": 8.53 / 2,
        "ratings": 128,  # 128 from api 131 on page??
        "favorites": 1752,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "Cheese in the Trap",
        "title_foreign": "치즈인더트랩 (순끼)",
        "tag": ['Full Color', 'Long Strip', 'Web Comic', 'Drama', 'Mystery', 'Psychological',
                'Romance', 'Slice of Life', 'School Life', 'Josei'],
        "censor_id": CENSOR_IDS['Unknown'],
        "language": "Korean",
        "status_id": STATUS_IDS['Completed'],
        "imported_from": MangaDexExtractor.site_id,
        "category": ["Manga"],
        "groups": [],
        "artist": ["Soon-Ki"],
        "parody": [],
        "character": [],
        'note': ("Description: Having returned to college after a year long break, Hong Sul, "
                 "a hard-working over-achiever, inadvertently got on the wrong side "
                 "of a suspiciously perfect senior named Yoo Jung. From then on, her "
                 "life took a turn for the worse - and Sul was almost certain it was "
                 "all Jung's doing. So why is he suddenly acting so friendly a year "
                 "later?"),
        'nsfw': 0,
        'collection': [],
        }

manual_mangadex2 = {
        "url": "https://mangadex.org/title/52391/the-garden-of-red-flowers",
        "pages": 0,
        "id_onpage": '52391',
        "rating": 7.89 / 2,
        "ratings": 293,  # 128 from api 131 on page??
        "favorites": 12588,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "The Garden of Red’s Flowers",
        "title_foreign": "붉은 꽃의 정원",
        "tag": ['Full Color', 'Long Strip', 'Web Comic', 'Comedy', 'Drama', 'Fantasy',
                'Isekai', 'Romance', 'Sci-Fi', 'Reincarnation'],
        "censor_id": CENSOR_IDS['Unknown'],
        "language": "Korean",
        "status_id": STATUS_IDS['Ongoing'],
        "imported_from": MangaDexExtractor.site_id,
        "category": ["Manga"],
        "groups": [],
        "artist": ["Maru (마루)"],
        "parody": [],
        "character": [],
        'note': ("Description: A story that reincarnates as a happy "
                 "<supporting> in a friend's novel, but takes on the misery of "
                 "<the main character>."),
        'nsfw': 0,
        'collection': [],
        }


def test_extr_mangadex(monkeypatch):

    orig_get_html = MangaDexExtractor.get_html

    def patched_get_html(*args):
        # a classmethod calling a patched classmethod doesn't seem to work
        # as it doesn't recoginze cls as the first arg
        if (isinstance(args[0], BaseMangaExtractor) or
                args[0] is MangaDexExtractor or args[0] is BaseMangaExtractor):
            url = args[1]
        else:
            url = args[0]

        if url.endswith('/tag'):
            return orig_get_html(build_testsdir_furl('extr_files/mangadex_tag.json'))
        elif '/111' in url:
            return orig_get_html(build_testsdir_furl('extr_files/mangadex_111.json'))
        else:
            return orig_get_html(build_testsdir_furl('extr_files/mangadex_52391.json'))

    monkeypatch.setattr('manga_db.extractor.mangadex.MangaDexExtractor.get_html',
                        patched_get_html)

    url = "https://mangadex.org/title/111/escaped-title-123"
    extr = MangaDexExtractor(url)
    assert extr.id_onpage == '111'
    assert extr.escaped_title == 'escaped-title-123'
    assert extr.get_cover() == "https://mangadex.org/images/manga/111.jpg"
    # make sure get_cover calls extract and sets api_response
    assert extr.api_response is not None
    data = extr.extract()
    comp_dict_manga_extr_data(manual_mangadex, data)

    url = "https://mangadex.org/title/52391/the-garden-of-red-flowers"
    extr = MangaDexExtractor(url)
    assert extr.id_onpage == '52391'
    assert extr.escaped_title == 'the-garden-of-red-flowers'
    assert extr.get_cover() == "https://mangadex.org/images/manga/52391.png"
    data2 = extr.extract()
    comp_dict_manga_extr_data(manual_mangadex2, data2)


def test_extr_mangadex_tag_retry(monkeypatch, caplog):

    MangaDexExtractor._tag_map = None
    MangaDexExtractor._tag_map_retries_left = 3
    orig_get_html = MangaDexExtractor.get_html
    i = 0

    def patched_get_html(*args):
        # a classmethod calling a patched classmethod doesn't seem to work
        # as it doesn't recoginze cls as the first arg
        if (isinstance(args[0], BaseMangaExtractor) or
                args[0] is MangaDexExtractor or args[0] is BaseMangaExtractor):
            url = args[1]
        else:
            url = args[0]

        if url.endswith('/tag'):
            nonlocal i
            i += 1
            # one initial call and then 3 retries
            if i == 4:
                return orig_get_html(build_testsdir_furl('extr_files/mangadex_tag.json'))
            else:
                return None
        else:
            return orig_get_html(build_testsdir_furl('extr_files/mangadex_111.json'))

    monkeypatch.setattr('manga_db.extractor.mangadex.MangaDexExtractor.get_html',
                        patched_get_html)

    with open(os.path.join(TESTS_DIR, 'extr_files', 'mangadex_tag.json'), 'r') as f:
        raw_json = f.read()
    tag_map = {int(k): v for k, v in json.loads(raw_json)['data'].items()}

    url = "https://mangadex.org/title/111/escaped-title-123"
    extr = MangaDexExtractor(url)
    assert extr.extract() is not None
    assert MangaDexExtractor._tag_map == tag_map

    caplog.set_level(logging.WARNING)
    caplog.clear()

    MangaDexExtractor._tag_map = None
    extr = MangaDexExtractor(url)
    assert extr.extract() is None
    assert len(caplog.messages) == 1
    assert "Failed to get tag map from MangaDex" in caplog.messages[0]


def test_extr_mangadex_tag_retry_if_map_success(monkeypatch):
    # make sure we don't run out of retries if the map is already valid

    MangaDexExtractor._tag_map = {x: {'name': f"tag{x}"} for x in (8, 20, 22, 23, 24, 31, 36, 44, 45)}
    MangaDexExtractor._tag_map_retries_left = 3
    orig_get_html = MangaDexExtractor.get_html

    def patched_get_html(*args):
        return orig_get_html(build_testsdir_furl('extr_files/mangadex_111.json'))

    monkeypatch.setattr('manga_db.extractor.mangadex.MangaDexExtractor.get_html',
                        patched_get_html)

    for _ in range(6):
        url = "https://mangadex.org/title/111/escaped-title-123"
        extr = MangaDexExtractor(url)
        assert extr.extract() is not None
    assert MangaDexExtractor._tag_map_retries_left == 3


def comp_dict_manga_extr_data(dic: Dict[str, Any], data: MangaExtractorData,
                              ignore_attrs: Set[str] = []) -> None:
    for attr in data.__dataclass_fields__.keys():
        if attr in ignore_attrs:
            continue
        expected = dic[attr]
        actual = getattr(data, attr)
        if isinstance(actual, (list, tuple)):
            assert sorted(expected) == sorted(actual)
        else:
            assert expected == actual


@pytest.mark.parametrize('inp, expected', [
    ('https://chap.manganelo.com/manga-hc121796', 'hc121796'),
    ('https://m.manganelo.com/manga-hc121796', 'hc121796'),
    ('https://chap.manganelo.com/manga-gb120921/chapter-22', 'gb120921'),
    ('https://chap.manganelo.com/manga-cy116918/chapter-46', 'cy116918'),
    ])
def test_extr_manganelo_bookid_from_url(inp, expected):
    assert ManganeloExtractor.book_id_from_url(inp) == expected


# on chap. subdomain == no rating
manual_manganelo_chap = {
        "url": "https://chap.manganelo.com/manga-hc121796",
        "pages": 0,
        "id_onpage": 'hc121796',
        "rating": None,
        "ratings": None,
        "favorites": None,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "Sword Sheath's Child",
        "title_foreign": "칼집의 아이",
        "tag": ['Action'],
        "censor_id": CENSOR_IDS['Unknown'],
        "language": "Unknown",
        "status_id": STATUS_IDS['Ongoing'],
        "imported_from": ManganeloExtractor.site_id,
        "category": ["Webtoon"],
        "groups": [],
        "artist": ["Hyung Min Kim"],
        "parody": [],
        "character": [],
        'note': ("\nDescription :\nBira is a kid who loves fishing, living and wandering in the wilderness with his dwarf grandfather. One day, his grandfather tells Bira to wait for him at the Northern part of the forest and disappears. Bira waits for many years living in forest while befriending a family of bears and staying away from humans, just as his grandfather had warned him to do. By chance, he meets and saves Tanyu’s life and later becomes friends with him. Upon hearing his friend going on a dangerous mission, Bira leaves the forest for the world outside to save his Tanyu.\n"),
        'nsfw': 0,
        'collection': [],
}

# on m. subdomain == rating
manual_manganelo_m = {
        # always use chap subdomain!
        "url": "https://chap.manganelo.com/manga-gh120927",
        "pages": 0,
        "id_onpage": 'gh120927',
        "rating": 4.78,
        "ratings": 1328,
        "favorites": None,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "Let's Buy The Land And Cultivate In Different World",
        "title_foreign": ("Isekai de Tochi o Katte Noujou o Tsukurou,"
                          "Isekai de Tochi wo Katte Noujou wo Tsukurou,"
                          "異世界で土地を買って農場を作ろう,"
                          "이세계에서 토지를 사서 농장을 만들자"),
        "tag": ['Action', 'Adventure',  'Comedy', 'Ecchi', 'Fantasy', 'Romance', 'Shounen'],
        "censor_id": CENSOR_IDS['Unknown'],
        "language": "Unknown",
        "status_id": STATUS_IDS['Ongoing'],
        "imported_from": ManganeloExtractor.site_id,
        "category": ["Manga"],
        "groups": [],
        "artist": ["Jun Sasameyuki", "Murakami Yuichi", "Rokujuuyon Okazawa"],
        "parody": [],
        "character": [],
        'note': ("\nDescription :\nAs our humble corporatist Itonami Norio is suddenly summoned to another world, it would look as if he'll be sent to a battlefield-- he, however, holds no skill to speak of, and as he is deemed to be useless. He negotiates with The King and receives a plot of land -- an empty, deserted plot of land, with no inhabitant in sight. Norio holds something he couldn't bring himself to tell anyone: The Master of Supremacy, a gift which will grant him the most comfortable of lives in this world. Hereby begins the Norio's colorful story -- having a mermaid he fishes declare herself his wife, becoming neighbors with the Undead King, this is his busy but enjoyable life -- and now a dragon appears ?! "),
        'nsfw': 1,
        'collection': [],
}


def abs_delta(a, b):
    return abs(a - b)


def test_extr_manganelo():
    expected = manual_manganelo_chap
    extr = ManganeloExtractor(expected['url'])
    assert extr.id_onpage == 'hc121796'
    # make sure get_cover calls extract and sets export_data
    assert extr.get_cover() in (
            "https://avt.mkklcdnv6.com/31/r/20-1583502246.jpg",
            "https://avt.mkklcdnv6temp.com/31/r/20-1583502246.jpg")
    assert extr.export_data is not None
    data = extr.extract()
    assert extr.export_data == data
    comp_dict_manga_extr_data(expected, data)

    # NOTE: we alywas use chap subdomain even if we get an url from m.
    url = 'https://m.manganelo.com/manga-gh120927'
    expected = manual_manganelo_m
    extr = ManganeloExtractor(url)
    assert extr.id_onpage == 'gh120927'
    # make sure get_cover calls extract and sets export_data
    assert extr.get_cover() in (
            "https://avt.mkklcdnv6.com/49/b/19-1583500958.jpg",
            "https://avt.mkklcdnv6temp.com/49/b/19-1583500958.jpg")
    assert extr.export_data is not None
    data = extr.extract()
    assert extr.export_data == data
    comp_dict_manga_extr_data(expected, data, ignore_attrs={'rating', 'ratings'})
    # since we check this from the online src we can only check if it's within a threshold
    assert abs_delta(data.rating, expected['rating']) <= 0.5
    assert data.ratings >= expected['ratings']


@pytest.mark.parametrize('inp, expected', [
    ('https://toonily.com/webtoon/leviathan-0002/', 'leviathan-0002'),
    ('http://toonily.com/webtoon/leviathan-0002/chapter-138/', 'leviathan-0002'),
    ('https://toonily.com/webtoon/my-high-school-bully', 'my-high-school-bully'),
    ('https://toonily.com/webtoon/meisters/', 'meisters'),
    ])
def test_extr_toonily_bookid_from_url(inp, expected):
    assert ToonilyExtractor.book_id_from_url(inp) == expected


manual_toonily1 = {
        # always use chap subdomain!
        "url": "https://toonily.com/webtoon/missing-o/",
        "pages": 0,
        "id_onpage": 'missing-o',
        "rating": 4.3,
        "ratings": 262,
        "favorites": 1100,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "The Missing O",
        "title_foreign": "안주는 남자",
        "tag": ['Adult', 'Comedy', 'Drama', 'Mature', 'Romance'],
        "censor_id": CENSOR_IDS['Censored'],
        "language": "English",
        "status_id": STATUS_IDS['Completed'],
        "imported_from": ToonilyExtractor.site_id,
        "category": ["Manhwa"],
        "groups": [],
        "artist": ["Face Park"],
        "parody": [],
        "character": [],
        'note': ("Summary: Sex can be amazing, not to mention ecstasy inducingly mind-blowing. And Eunsung knows that because 7 years ago, she had good sex (an understatement). She felt the universe crack open to show her its secrets. Too bad she hasn’t had a decent orgasm since. It’s been a long journey, but everyone knows, before you get to “P,” you have to go through “O.”"),
        'nsfw': 1,
        'collection': [],
}

manual_toonily2 = {
        # always use chap subdomain!
        "url": "https://toonily.com/webtoon/golden-scale/",
        "pages": 0,
        "id_onpage": 'golden-scale',
        "rating": 4.1,
        "ratings": 272,
        "favorites": 1700,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "Golden Scale",
        "title_foreign": "金鳞岂是池中物",
        "tag": ['Action', 'Adult', 'Mature', 'Psychological', 'Uncensored'],
        "censor_id": CENSOR_IDS['Uncensored'],
        "language": "English",
        "status_id": STATUS_IDS['Ongoing'],
        "imported_from": ToonilyExtractor.site_id,
        "category": ["Manhua"],
        "groups": [],
        "artist": ["MONKEY(Hou LongTao)"],
        "parody": [],
        "character": [],
        'note': ("Note : This content is UNCENSORED\nA little Beijing hooligan who finished college in the United States was lucky enough to win the California State Lottery. He bribed the General Manager of a Multinational Investment Company and got the opportunity to return back to the Beijing Branch as the manager of the investment department. During his encounter with all kind of beauties, he also encountered many crises, but he relied on his relationship and luck to turn the dangers into opportunities becoming this generation’s Business Giant"),
        'nsfw': 1,
        'collection': [],
}


@pytest.mark.requires_cookies
def test_extr_toonily():
    # NOTE: IMPORTANT ToonilyExtractor needs a current tests\cookies.txt with cloudflare clearance
    # cookies and the User-Agent in the comments
    update_cookies_from_file(os.path.join(TESTS_DIR, 'cookies.txt'))

    expected = manual_toonily1
    extr = ToonilyExtractor(expected['url'])
    assert extr.id_onpage == 'missing-o'
    # make sure get_cover calls extract and sets export_data
    assert extr.get_cover() == (
            "https://toonily.com/wp-content/uploads/2019/12/The-Missing-O-193x278.jpg")
    assert extr.export_data is not None
    data = extr.extract()
    assert extr.export_data == data
    comp_dict_manga_extr_data(expected, data, ignore_attrs={'rating', 'ratings', 'favorites'})
    # since we check this from the online src we can only check if it's within a threshold
    assert abs_delta(data.rating, expected['rating']) <= 0.5
    assert data.ratings >= expected['ratings']
    assert data.favorites >= expected['favorites']

    #
    # uncensored detected
    # manhua category
    #
    expected = manual_toonily2
    extr = ToonilyExtractor(expected['url'])
    assert extr.id_onpage == 'golden-scale'
    # make sure get_cover calls extract and sets export_data
    assert extr.get_cover() == (
            "https://toonily.com/wp-content/uploads/2020/11/Read-Golden-Scale-manhua-"
            "Read-Golden-Scale-Manhwa-for-free-193x278.jpg")
    assert extr.export_data is not None
    data = extr.extract()
    assert extr.export_data == data
    comp_dict_manga_extr_data(expected, data, ignore_attrs={'rating', 'ratings', 'favorites'})
    # since we check this from the online src we can only check if it's within a threshold
    assert abs_delta(data.rating, expected['rating']) <= 0.5
    assert data.ratings >= expected['ratings']
    assert data.favorites >= expected['favorites']

    #
    # non-nsfw
    # author != artist
    url = 'https://toonily.com/webtoon/leviathan-0002/'
    extr = ToonilyExtractor(url)
    assert extr.id_onpage == 'leviathan-0002'
    data = extr.extract()
    assert data.nsfw == 0
    assert sorted(data.artist) == ['Lee Gyuntak', 'Noh Miyoung']


@pytest.mark.parametrize('inp, expected', [
    ('https://www.mangasee123.com/manga/Parallel-Paradise', 'Parallel-Paradise'),
    ('https://mangasee123.com/read-online/Minamoto-Kun-Monogatari-chapter-351-page-1.html',
     'Minamoto-Kun-Monogatari'),
    ('https://www.mangasee123.com/read-online/Tokyo-05-Revengers-chapter-1-page-1.html',
     'Tokyo-05-Revengers'),
    ('https://mangasee123.com/manga/1-Love9', '1-Love9'),
    ])
def test_extr_mangasee123_bookid_from_url(inp, expected):
    assert MangaSee123Extractor.book_id_from_url(inp) == expected


manual_mangasee123_2art = {
        "url": "https://mangasee123.com/manga/Kaifuku-Jutsushi-No-Yarinaoshi",
        "pages": 0,
        "id_onpage": 'Kaifuku-Jutsushi-No-Yarinaoshi',
        "rating": None,
        "ratings": None,
        "favorites": 1688,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "Kaifuku Jutsushi no Yarinaoshi",
        "title_foreign": None,
        "tag": ['Action', 'Adult', 'Adventure', 'Drama', 'Fantasy', 'Harem', 'Seinen'],
        "censor_id": CENSOR_IDS['Unknown'],
        "language": "English",
        "status_id": STATUS_IDS['Ongoing'],
        "imported_from": MangaSee123Extractor.site_id,
        "category": ["Manga"],
        "groups": [],
        "artist": ["Haga Souken", "Tsukiyo Rui"],
        "parody": [],
        "character": [],
        'note': ("Description: Healing magicians cannot fight alone.â€™ Keare, who was bound by this common knowledge, was exploited again and again by others.\nBut one day, he noticed what lay beyond healing magic, and was convinced that a healing magician was the strongest class. However, by the time he realized that potential, he was deprived of everything. Thus, he used healing magic on the world itself to go back four years, deciding to redo everything.\nThis is a heroic tale of one healing magician who became the strongest by using knowledge from his past life and healing magic."),
        'nsfw': 1,
        'collection': [],
}

manual_mangasee123_pubscan = {
        "url": "https://www.mangasee123.com/read-online/Akuma-No-Hanayome-chapter-15-page-1.html", #"https://www.mangasee123.com/manga/Akuma-No-Hanayome",
        "pages": 0,
        "id_onpage": 'Akuma-No-Hanayome',
        "rating": None,
        "ratings": None,
        "favorites": 5,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "Akuma no Hanayome",
        "title_foreign": None,
        "tag": ['Fantasy', 'Horror', 'Psychological', 'Romance', 'Shoujo', 'Supernatural'],
        "censor_id": CENSOR_IDS['Unknown'],
        "language": "English",
        "status_id": STATUS_IDS['Completed'],
        "imported_from": MangaSee123Extractor.site_id,
        "category": ["Manga"],
        "groups": [],
        "artist": ['Ashibe Yuuho', 'Ikeda Etsuko'],
        "parody": [],
        "character": [],
        'note': ("Description: Deimos was once a handsome god. He loved a beautiful goddess who returns his sentiments. The problem, well, she is his sister. For their crime against nature they were struck down out of Olympus. The brother is now a demon and the sister a rotting corpse at the bottom of the ocean. Deimos must choose between his sister and her living human incarnation. His sister is jealous. The girl is horrified and unsure of just what to make of her situation."),
        'nsfw': 0,
        'collection': [],
}


def test_extr_mangasee123():
    expected = manual_mangasee123_2art
    extr = MangaSee123Extractor(expected['url'])
    assert extr.id_onpage == 'Kaifuku-Jutsushi-No-Yarinaoshi'
    # make sure get_cover calls extract and sets export_data
    assert extr.get_cover() == "https://cover.nep.li/cover/Kaifuku-Jutsushi-No-Yarinaoshi.jpg"
    assert extr.export_data is not None
    data = extr.extract()
    assert extr.export_data == data
    comp_dict_manga_extr_data(expected, data, ignore_attrs={'favorites'})
    assert abs_delta(expected['favorites'], data.favorites) <= 300


    # use (Publish) status which is Complete instead of scan status (Ongoing)
    expected = manual_mangasee123_pubscan
    extr = MangaSee123Extractor(expected['url'])
    assert extr.id_onpage == 'Akuma-No-Hanayome'
    # make sure get_cover calls extract and sets export_data
    assert extr.get_cover() == "https://cover.nep.li/cover/Akuma-No-Hanayome.jpg"
    assert extr.export_data is not None
    data = extr.extract()
    assert extr.export_data == data
    comp_dict_manga_extr_data(expected, data, ignore_attrs={'favorites', 'url'})
    assert data.url == "https://mangasee123.com/manga/Akuma-No-Hanayome"
    assert abs_delta(expected['favorites'], data.favorites) <= 50
