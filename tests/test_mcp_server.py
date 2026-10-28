import asyncio

import pytest

from core.pdf_reader import PdfError
from mcp_server import add_furigana, analyze_japanese, extract_pdf_text, mcp
from tests.test_pdf_reader import make_pdf


def test_analyze_japanese():
    result = analyze_japanese("食べました")
    assert [t["surface"] for t in result] == ["食べ", "まし", "た"]
    assert result[0] == {"surface": "食べ", "lemma": "食べる", "reading": "たべ", "pos": "動詞"}


def test_add_furigana():
    assert add_furigana("寿司を食べました。") == "寿司(すし)を食(た)べました。"
    assert add_furigana("3本") == "3本(さんぼん)"


def test_empty_text():
    assert analyze_japanese("") == []
    assert add_furigana("") == ""


def test_extract_pdf_text(tmp_path):
    path = tmp_path / "article.pdf"
    path.write_bytes(make_pdf([["今日は天気がいいので、公園へ", "散歩に行きました。"]]))
    assert extract_pdf_text(str(path)) == ["今日は天気がいいので、公園へ散歩に行きました。"]


def test_extract_pdf_text_without_text(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_pdf([[]]))
    with pytest.raises(PdfError):
        extract_pdf_text(str(path))


def test_tools_registered():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {"analyze_japanese", "add_furigana", "extract_pdf_text"}
