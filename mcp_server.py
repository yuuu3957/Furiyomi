"""MCP server：把 core 的功能包成工具，給 Claude Desktop 等 MCP 客戶端使用。

工具只是 core 函式的薄包裝，不放邏輯。啟動：python mcp_server.py（stdio）。
單字庫工具和網頁共用同一個資料庫檔（data/furiyomi.db，或 FURIYOMI_DB 指定的路徑）。
"""

import sqlite3
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core import vocab_repo
from core.furigana import bracket_text
from core.paging import split_pages
from core.pdf_reader import extract_text
from core.tokenizer import tokenize

mcp = FastMCP("furiyomi")


@mcp.tool()
def analyze_japanese(text: str) -> list[dict]:
    """把日文斷詞，回傳每個詞的表記、原形、讀音（平假名）、詞性。

    保留 SudachiPy 的原始切分，不合併活用（食べました → 食べ／まし／た）；數字＋量詞合成一個詞。
    """
    return [
        {"surface": t.surface, "lemma": t.lemma, "reading": t.reading, "pos": t.pos}
        for t in tokenize(text)
    ]


@mcp.tool()
def add_furigana(text: str) -> str:
    """在日文漢字後面用括號標上平假名讀音，例如「寿司を食べました」→「寿司(すし)を食(た)べました」。"""
    return bracket_text(tokenize(text))


@mcp.tool()
def extract_pdf_text(path: str) -> list[str]:
    """抽出文字型橫書 PDF 的文字，把每行接回段落，再切成每段 2,000 字內的區塊（盡量在段落結尾切）。

    掃描檔等沒有文字的 PDF 會回傳錯誤。
    """
    return split_pages(extract_text(Path(path).read_bytes()))


@lru_cache(maxsize=1)
def _db() -> sqlite3.Connection:
    return vocab_repo.connect()


@mcp.tool()
def search_vocab(keyword: str | None = None, pos: str | None = None) -> list[dict]:
    """查詢單字庫。keyword 比對原形、讀音、中文意思；pos 是詞性（如「動詞」「名詞」）。

    每個單字含 examples：收藏時所在的句子（context_sentence）與該句中的中文意思（meaning_zh），一詞多義各自一筆。
    """
    return [asdict(e) for e in vocab_repo.search_vocab(_db(), keyword, pos)]


@mcp.tool()
def add_to_vocab(
    lemma: str,
    pos: str,
    context_sentence: str = "",
    reading: str = "",
    surface: str = "",
    meaning_zh: str = "",
    usage_note: str = "",
) -> dict:
    """把單字加入單字庫。lemma 是原形（如「食べる」），pos 是詞性，context_sentence 是它所在的句子。

    reading 留空時由原形推算。已收藏的單字在新的句子收藏時加為新的例句；同一句重複收藏會回傳錯誤。
    """
    return asdict(vocab_repo.add_vocab(
        _db(), lemma, pos, reading=reading, surface=surface, context_sentence=context_sentence,
        meaning_zh=meaning_zh, usage_note=usage_note,
    ))


@mcp.tool()
def delete_vocab(vocab_id: int) -> bool:
    """刪除單字庫中的單字（連同所有例句）；找不到時回傳 false。"""
    return vocab_repo.delete_vocab(_db(), vocab_id)


@mcp.tool()
def delete_vocab_example(example_id: int) -> bool:
    """刪除單字的一個例句；刪掉最後一個例句時單字也一起刪除。找不到時回傳 false。"""
    return vocab_repo.delete_example(_db(), example_id) is not None


if __name__ == "__main__":
    mcp.run()
