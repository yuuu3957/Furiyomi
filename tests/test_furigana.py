import pytest

from core.furigana import bracket_text, contains_japanese, katakana_to_hiragana, pos_class, ruby_segments
from core.tokenizer import Token


def test_katakana_to_hiragana():
    assert katakana_to_hiragana("タベマシタ") == "たべました"


def test_small_kana_and_vu():
    assert katakana_to_hiragana("ショッヴ") == "しょっゔ"


def test_long_vowel_mark_and_others_unchanged():
    assert katakana_to_hiragana("ラーメン、abc。漢字") == "らーめん、abc。漢字"


def test_empty():
    assert katakana_to_hiragana("") == ""


@pytest.mark.parametrize("surface, reading, expected", [
    ("寿司", "すし", [("寿司", "すし")]),
    ("食べ", "たべ", [("食", "た"), ("べ", None)]),                         # 送假名不加讀音
    ("お茶", "おちゃ", [("お", None), ("茶", "ちゃ")]),
    ("取り扱い", "とりあつかい", [("取", "と"), ("り", None), ("扱", "あつか"), ("い", None)]),
    ("時々", "ときどき", [("時々", "ときどき")]),
    ("10日", "とおか", [("10日", "とおか")]),                              # 數字＋量詞整組
    ("15", "じゅうご", [("15", "じゅうご")]),
])
def test_ruby_segments(surface, reading, expected):
    assert ruby_segments(surface, reading) == expected


@pytest.mark.parametrize("surface", ["まし", "コーヒー", "。", "Python", " "])
def test_no_ruby_for_kana_punctuation_and_latin(surface):
    assert ruby_segments(surface, surface) == [(surface, None)]


def test_ruby_falls_back_to_whole_token_when_reading_does_not_match():
    # ヶ 轉平假名後是 ゖ，對不上讀音的「か」
    assert ruby_segments("三ヶ月", "さんかげつ") == [("三ヶ月", "さんかげつ")]


def _token(surface, reading):
    return Token(surface, surface, reading, "", "", "")


def test_bracket_text():
    tokens = [_token("寿司", "すし"), _token("を", "を"), _token("食べ", "たべ"),
              _token("まし", "まし"), _token("た", "た"), _token("。", "。")]
    assert bracket_text(tokens) == "寿司(すし)を食(た)べました。"


def test_bracket_text_number_and_empty():
    assert bracket_text([_token("10日", "とおか")]) == "10日(とおか)"
    assert bracket_text([]) == ""


@pytest.mark.parametrize("text, expected", [
    ("寿司を食べました。", True),
    ("コーヒー", True),
    ("我今天吃了壽司。", False),
    ("Hello, world!", False),
    ("", False),
])
def test_contains_japanese(text, expected):
    assert contains_japanese(text) == expected


@pytest.mark.parametrize("pos, expected", [
    ("名詞", "noun"),
    ("代名詞", "noun"),
    ("動詞", "verb"),
    ("形状詞", "adjective"),
    ("副詞", "adverb"),
    ("助動詞", "auxiliary"),
    ("助詞", "particle"),
    ("接頭辞", "affix"),
    ("補助記号", "symbol"),
    ("未知の詞性", "other"),
])
def test_pos_class(pos, expected):
    assert pos_class(pos) == expected
