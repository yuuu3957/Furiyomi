"""切段規則：把長文切成每頁不超過 limit 字，貼上文字與 PDF 共用。

1. 段落：一頁盡量放完整段落，在最後一個放得下的段落結尾切。
2. 句子：單一段落超過 limit 時，在 limit 內最後一個句尾切。
3. 硬切：單一句子超過 limit 時，在第 limit 字切。

所有頁面依序串起來會等於原文。
"""

import re

PAGE_LIMIT = 2000

# 段落：內容連同後面的換行（換行之後接的是下一段的開頭）
_PARAGRAPH = re.compile(r"(?<=\n)(?=[^\n])")
# 句子：到句尾標點為止，連同後面的收尾括號與換行（「…。」 不會把 」 切到下一句）
_SENTENCE = re.compile(r".*?(?:[。！？!?]+[」』）)]*\n*|$)", re.S)


def _units(text: str, limit: int) -> list[str]:
    """把文字拆成不超過 limit 的單位：完整段落 → 句子 → 硬切。"""
    units = []
    for para in _PARAGRAPH.split(text):
        if len(para) <= limit:
            units.append(para)
            continue
        for sentence in _SENTENCE.findall(para):
            units.extend(sentence[i:i + limit] for i in range(0, len(sentence), limit))
    return [u for u in units if u]


def split_pages(text: str, limit: int = PAGE_LIMIT) -> list[str]:
    """依序把單位裝進頁面，裝不下就換頁。"""
    pages: list[str] = []
    page = ""
    for unit in _units(text, limit):
        if page and len(page) + len(unit) > limit:
            pages.append(page)
            page = ""
        page += unit
    if page:
        pages.append(page)
    return pages
