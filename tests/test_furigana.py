from core.furigana import katakana_to_hiragana


def test_katakana_to_hiragana():
    assert katakana_to_hiragana("タベマシタ") == "たべました"


def test_small_kana_and_vu():
    assert katakana_to_hiragana("ショッヴ") == "しょっゔ"


def test_long_vowel_mark_and_others_unchanged():
    assert katakana_to_hiragana("ラーメン、abc。漢字") == "らーめん、abc。漢字"


def test_empty():
    assert katakana_to_hiragana("") == ""
