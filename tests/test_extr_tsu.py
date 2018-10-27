import datetime

from manga_db.extractor.tsumino import TsuminoExtractor

from utils import build_testsdir_furl


manual = {
        "url": "http://www.tsumino.com/Book/Info/43357/negimatic-paradise-05-05",
        "pages": 23,
        "id_onpage": 43357,
        "rating": 4.8,
        "ratings": 5,
        "favorites": 137,
        "uploader": "nekoanime15",
        "upload_date": datetime.datetime.strptime("2018-10-07", "%Y-%m-%d").date(),
        "title_eng": "Negimatic Paradise! 05'",
        "title_foreign": "ネギまちっく天国05'",
        "tag": ["Cosplay", "Large Breasts", "Mind Control", "Nakadashi", "Sleeping",
                "Straight Shota", "Sweating", "Teacher", "Wings"],
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
        "character": ["Ayaka Yukihiro", "Negi Springfield"]
        }


def test_extr_tsu():
    t = TsuminoExtractor("http://www.tsumino.com/Book/Info/43357/negimatic-paradise-05-05-")
    t.html = TsuminoExtractor.get_html(build_testsdir_furl("extr_tsu_files/tsumino_43357_negimatic-paradise-05-05.html"))
    res = t.get_metadata()

    assert res == manual
    assert t.get_cover() == "http://www.tsumino.com/Image/Thumb/43357"


def test_extr_tsu_bookidfromurl():
    urls = {
            "http://www.tsumino.com/Book/Info/43357": 43357,
            "http://www.tsumino.com/Read/View/43357": 43357,
            "http://www.tsumino.com/Download/Index/43357": 43357,
            "http://www.tsumino.com/Book/Info/43360/saimin-idol-happy-clover-ga-chiriochiru-made-ch-1-1-": 43360,
            "http://www.tsumino.com/Book/Info/43360/saimin-idol-happy-clover-ga-chiriochiru-made-ch-1-1": 43360
            }
    for u, i in urls.items():
        assert TsuminoExtractor.book_id_from_url(u) == i
