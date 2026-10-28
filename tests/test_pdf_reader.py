import io

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from core.pdf_reader import PdfError, extract_text, join_lines

FONT = "HeiseiKakuGo-W5"  # reportlab 內建的日文字型，不需要字型檔
pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def make_pdf(pages: list[list[str]], password: str | None = None) -> bytes:
    """每頁一個字串列表，每個字串畫成一行；空列表就是沒有文字的頁面。"""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt=password)
    for lines in pages:
        c.setFont(FONT, 12)
        for i, line in enumerate(lines):
            c.drawString(50, 800 - 20 * i, line)
        c.showPage()
    c.save()
    return buf.getvalue()


# --- join_lines ---

def test_lines_join_into_paragraph():
    assert join_lines("今日は天気がいいので、公園へ\n散歩に行きました。") == "今日は天気がいいので、公園へ散歩に行きました。"


def test_new_paragraph_after_sentence_end():
    assert join_lines("散歩しました。\n楽しかった。") == "散歩しました。\n楽しかった。"


def test_new_paragraph_after_closing_quote():
    assert join_lines("「行こう！」\nと言った。") == "「行こう！」\nと言った。"


def test_new_paragraph_at_indent_and_blank_line():
    assert join_lines("一段落目で\n　二段落目") == "一段落目で\n　二段落目"
    assert join_lines("一段落目で\n\n二段落目") == "一段落目で\n二段落目"


def test_ascii_words_keep_space():
    assert join_lines("Hello\nworld です") == "Hello world です"


def test_page_numbers_are_dropped():
    assert join_lines("前のページの\n- 3 -\n続きです。\n12") == "前のページの続きです。"


# --- extract_text ---

def test_extract_text_from_pdf():
    data = make_pdf([
        ["　今日は天気がいいので、公園へ", "散歩に行きました。", "「楽しかった！」と言った。"],
        ["　次の日も", "行きました。"],
    ])
    assert extract_text(data) == (
        "　今日は天気がいいので、公園へ散歩に行きました。\n"
        "「楽しかった！」と言った。\n"
        "　次の日も行きました。"
    )


def test_paragraph_continues_across_pages():
    data = make_pdf([["ページをまたぐ"], ["段落です。"]])
    assert extract_text(data) == "ページをまたぐ段落です。"


def test_pdf_without_text():
    with pytest.raises(PdfError) as e:
        extract_text(make_pdf([[], []]))
    assert e.value.code == "no_text"


def test_not_a_pdf():
    with pytest.raises(PdfError) as e:
        extract_text("これは PDF ではありません".encode())
    assert e.value.code == "invalid_pdf"


def test_password_protected_pdf():
    with pytest.raises(PdfError) as e:
        extract_text(make_pdf([["秘密です。"]], password="secret"))
    assert e.value.code == "encrypted_pdf"
