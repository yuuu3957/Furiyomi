"""MCP server：把 core 的功能包成工具，給 Claude Desktop 等 MCP 客戶端使用。

工具只是 core 函式的薄包裝，不放邏輯。啟動：python mcp_server.py（stdio）。
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

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


if __name__ == "__main__":
    mcp.run()
