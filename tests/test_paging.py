from core.paging import split_pages


def test_empty_text():
    assert split_pages("") == []


def test_short_text_is_one_page():
    assert split_pages("今日は晴れ。\n明日は雨。") == ["今日は晴れ。\n明日は雨。"]


def test_cuts_at_last_paragraph_that_fits():
    a, b, c = "あ" * 4 + "\n", "い" * 4 + "\n", "う" * 4
    assert split_pages(a + b + c, limit=10) == [a + b, c]


def test_blank_lines_stay_with_previous_paragraph():
    text = "あいう。\n\nかきく。"
    assert split_pages(text, limit=8) == ["あいう。\n\n", "かきく。"]


def test_long_paragraph_cuts_at_sentence_end():
    text = "あいう。かきく。さしす。"
    assert split_pages(text, limit=10) == ["あいう。かきく。", "さしす。"]


def test_closing_quote_stays_with_sentence():
    text = "「あいう。」かきく。"
    assert split_pages(text, limit=7) == ["「あいう。」", "かきく。"]


def test_long_sentence_is_hard_cut():
    text = "あ" * 25
    assert split_pages(text, limit=10) == ["あ" * 10, "あ" * 10, "あ" * 5]


def test_pages_join_back_to_original():
    text = ("今日は天気がいいので、公園へ散歩に行きました。\n" * 30
            + "長い段落です。" * 400 + "\n\n" + "句点のない長い文" * 300)
    pages = split_pages(text)
    assert "".join(pages) == text
    assert all(len(p) <= 2000 for p in pages)
