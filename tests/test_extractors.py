import datetime
import logging
import json
import pytest
import os.path

from manga_db.extractor.base import BaseMangaExtractor
from manga_db.extractor.tsumino import TsuminoExtractor
from manga_db.extractor.nhentai import NhentaiExtractor
from manga_db.extractor.mangadex import MangaDexExtractor
from manga_db.constants import CENSOR_IDS, STATUS_IDS

from utils import build_testsdir_furl, TESTS_DIR


manual_tsumino = {
        "url": "https://www.tsumino.com/entry/43357",
        "pages": 23,
        "id_onpage": 43357,
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
        "my_rating": None,
        "category": ["Doujinshi"],
        "collection": ["Negimatic Paradise!"],
        "groups": ["Gakuen Yuushabu"],
        "artist": ["Tsurugi Yasuyuki"],
        "parody": ["Mahou Sensei Negima! / 魔法先生ネギま！"],
        "character": ["Ayaka Yukihiro", "Negi Springfield"],
        "nsfw": 1,
        }


def test_extr_tsu(monkeypatch, caplog):
    url = "https://www.tsumino.com/entry/43357"
    t = TsuminoExtractor(url)
    t.html = TsuminoExtractor.get_html(
            build_testsdir_furl("extr_files/tsumino_43357_negimatic-paradise-05-05.html"))
    res = t.get_metadata()

    assert res == manual_tsumino
    assert t.get_cover() == "https://content.tsumino.com/thumbs/43357/1"

    # test no data receieved
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html", lambda x: None)
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover",
                        lambda x: None)
    caplog.clear()
    t = TsuminoExtractor(url)
    assert t.get_metadata() is None
    assert caplog.record_tuples == [
            ("manga_db.extractor.tsumino", logging.WARNING,
             # url without last dash
             f"Extraction failed! HTML was empty for url '{url}'"),
            ]


def test_extr_tsu_bookidfromurl():
    urls = {
            "http://www.tsumino.com/entry/43357": 43357,
            "http://www.tsumino.com/entry/1337": 1337,
            "http://www.tsumino.com/Read/Index/43357": 43357,
            "http://www.tsumino.com/Read/Index/1337": 1337,
            }
    for u, i in urls.items():
        assert TsuminoExtractor.book_id_from_url(u) == i


manual_nhentai = {
        "url": "https://nhentai.net/g/77052/",
        "pages": 26,
        "id_onpage": 77052,
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
        }


def test_extr_nhent(monkeypatch, caplog):
    # decensored, ongoing in title
    url = "https://nhentai.net/g/77052/"
    t = NhentaiExtractor(url)
    t.json = json.loads(t.get_json_from_html(
        NhentaiExtractor.get_html(build_testsdir_furl("extr_files/nhentai_251287.html"))))
    res = t.get_metadata()
    assert res["censor_id"] == CENSOR_IDS["Decensored"]
    assert res["status_id"] == STATUS_IDS["Ongoing"]

    t = NhentaiExtractor(url)
    html_str = NhentaiExtractor.get_html(build_testsdir_furl("extr_files/nhentai_77052.html"))
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html",
                        lambda x: html_str)
    res = t.get_metadata()

    assert res == manual_nhentai
    assert t.get_cover() == "https://t.nhentai.net/galleries/501421/cover.jpg"

    # test no data receieved
    args = []
    monkeypatch.setattr("manga_db.extractor.base.BaseMangaExtractor.get_html",
                        lambda x: args.append(x))
    monkeypatch.setattr("manga_db.extractor.tsumino.TsuminoExtractor.get_cover",
                        lambda x: None)
    caplog.clear()
    t = NhentaiExtractor(url)
    assert t.get_metadata() is None
    assert args == ["https://nhentai.net/g/77052/"]
    assert caplog.record_tuples == [
            ("manga_db.extractor.nhentai", logging.WARNING,
             # url without last dash
             f"Extraction failed! HTML response was empty for url '{url}'"),
            ]


def test_extr_nhentai_bookid_from_url():
    urls = {
            "https://nhentai.net/g/77052/": 77052,
            "https://nhentai.net/g/97725/": 97725,
            "https://nhentai.net/g/158268/": 158268
            }
    for u, i in urls.items():
        assert NhentaiExtractor.book_id_from_url(u) == i


@pytest.mark.parametrize('inp, expected', [
    ('https://mangadex.org/title/358239/escaped-title-123', 358239),
    ('https://www.mangadex.org/title/12464/escaped-title-123', 12464),
    ('https://mangadex.cc/title/358239/escaped-title-123', 358239),
    ('http://mangadex.org/title/358239/escaped-title-123', 358239),
    ('https://mangadex.cc/title/358239', 358239),
    ])
def test_extr_mangadex_bookid_from_url(inp, expected):
    assert MangaDexExtractor.book_id_from_url(inp) == expected


manual_mangadex = {
        "url": "https://mangadex.org/title/111/escaped-title-123",
        "pages": 0,
        "id_onpage": 111,
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
                 "later?")
        }

manual_mangadex2 = {
        "url": "https://mangadex.org/title/52391/the-garden-of-red-flowers",
        "pages": 0,
        "id_onpage": 52391,
        "rating": 7.89 / 2,
        "ratings": 293,  # 128 from api 131 on page??
        "favorites": 12588,
        "uploader": None,
        "upload_date": datetime.date.min,
        "title_eng": "The Garden of Red Flowers",
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
                 "&lt;supporting&gt; in a friend's novel, but takes on the misery of "
                 "&lt;the main character&gt;.")
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
    assert extr.id_onpage == 111
    assert extr.escaped_title == 'escaped-title-123'
    assert extr.get_cover() == "https://mangadex.org/images/manga/111.jpg"
    data = extr.get_metadata()
    assert set(data.keys()) == set(manual_mangadex.keys())

    url = "https://mangadex.org/title/52391/the-garden-of-red-flowers"
    extr = MangaDexExtractor(url)
    assert extr.id_onpage == 52391
    assert extr.escaped_title == 'the-garden-of-red-flowers'
    assert extr.get_cover() == "https://mangadex.org/images/manga/52391.png"
    data2 = extr.get_metadata()
    assert set(data2.keys()) == set(manual_mangadex2.keys())

    for expected, actual in ((manual_mangadex, data), (manual_mangadex2, data2)):
        for k, v in expected.items():
            if k == 'tag':
                assert sorted(actual[k]) == sorted(v)
            else:
                assert actual[k] == v

def test_extr_mangadex_tag_retry(monkeypatch, caplog):

    MangaDexExtractor._tag_map = None
    MangaDexExtractor._tag_map_tries_left = 3
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
            if i == 2:
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
    assert extr.get_metadata() is not None
    assert MangaDexExtractor._tag_map == tag_map

    caplog.set_level(logging.WARNING)
    caplog.clear()

    MangaDexExtractor._tag_map = None
    extr = MangaDexExtractor(url)
    assert extr.get_metadata() is None
    assert len(caplog.messages) == 1
    assert "Failed to get tag map from MangaDex" in caplog.messages[0]
