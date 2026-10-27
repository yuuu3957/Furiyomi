import asyncio

from mcp_server import add_furigana, analyze_japanese, mcp


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


def test_tools_registered():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {"analyze_japanese", "add_furigana"}
