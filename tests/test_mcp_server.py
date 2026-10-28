import asyncio

import pytest

import mcp_server
from core.pdf_reader import PdfError
from core.vocab_repo import DuplicateVocabError, connect
from mcp_server import (
    add_furigana, add_to_vocab, analyze_japanese, delete_vocab, delete_vocab_example, extract_pdf_text, mcp,
    search_vocab,
)
from tests.test_pdf_reader import make_pdf


@pytest.fixture
def db(monkeypatch):
    """單字庫工具改用記憶體資料庫，不碰 data/furiyomi.db。"""
    conn = connect(":memory:")
    monkeypatch.setattr(mcp_server, "_db", lambda: conn)
    yield conn
    conn.close()


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


def test_add_and_search_vocab(db):
    entry = add_to_vocab("かける", "動詞", context_sentence="電話をかけた。", meaning_zh="打（電話）")
    assert entry["reading"] == "かける"
    add_to_vocab("かける", "動詞", context_sentence="眼鏡をかけた。", meaning_zh="戴")
    [found] = search_vocab(keyword="戴")
    assert found["id"] == entry["id"]
    assert [ex["meaning_zh"] for ex in found["examples"]] == ["打（電話）", "戴"]
    assert search_vocab(pos="名詞") == []


def test_add_duplicate_sentence(db):
    add_to_vocab("食べる", "動詞", context_sentence="寿司を食べた。")
    with pytest.raises(DuplicateVocabError):
        add_to_vocab("食べる", "動詞", context_sentence="寿司を食べた。")


def test_delete_vocab_and_example(db):
    add_to_vocab("かける", "動詞", context_sentence="電話をかけた。")
    entry = add_to_vocab("かける", "動詞", context_sentence="眼鏡をかけた。")
    assert delete_vocab_example(entry["examples"][0]["id"]) is True
    assert delete_vocab_example(entry["examples"][0]["id"]) is False
    assert delete_vocab(entry["id"]) is True
    assert delete_vocab(entry["id"]) is False
    assert search_vocab() == []


def test_tools_registered():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {
        "analyze_japanese", "add_furigana", "extract_pdf_text",
        "search_vocab", "add_to_vocab", "delete_vocab", "delete_vocab_example",
    }
