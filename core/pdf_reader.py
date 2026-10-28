"""PDF 讀取：抽出文字型橫書 PDF 的文字，並把每行的換行接回段落。

接回段落的判斷（不準時由切段規則的句子、硬切兜底）：
- 空行、行首是全形空白（段落縮排）、上一行以句尾標點結束 → 新段落
- 其餘的行直接接在上一行後面；英數之間補一個半形空白
- 只有數字的行視為頁碼，略過
"""

import io
import re

from pypdf import PdfReader

_PARAGRAPH_END = re.compile(r"[。！？!?」』）)]$")
_PAGE_NUMBER = re.compile(r"^[-－—\s]*\d+[-－—\s]*$")
_ASCII_WORD = re.compile(r"[A-Za-z0-9]")


class PdfError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def join_lines(raw: str) -> str:
    paragraphs: list[str] = []
    current = ""
    for line in raw.splitlines():
        # 只去掉半形空白，保留行首的全形空白來判斷段落縮排
        line = line.strip(" \t").rstrip()
        if _PAGE_NUMBER.match(line):
            continue
        if not line or line.startswith("　") or _PARAGRAPH_END.search(current):
            if current:
                paragraphs.append(current)
            current = line
        elif _ASCII_WORD.match(current[-1:]) and _ASCII_WORD.match(line):
            current += " " + line
        else:
            current += line
    if current:
        paragraphs.append(current)
    return "\n".join(paragraphs)


def extract_text(data: bytes) -> str:
    """回傳接回段落後的全文；不是 PDF、加密或沒有文字時丟 PdfError。"""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfError("encrypted_pdf", "這個 PDF 有密碼保護，無法讀取。")
        # 每頁結尾的換行要去掉，否則接頁時會多出空行，跨頁的段落被切斷
        raw = "\n".join((page.extract_text() or "").rstrip("\n") for page in reader.pages)
    except PdfError:
        raise
    except Exception:
        raise PdfError("invalid_pdf", "無法讀取這個檔案，請確認是 PDF。")
    text = join_lines(raw)
    if not text.strip():
        raise PdfError("no_text", "這個 PDF 沒有可以抽出的文字（可能是掃描檔或圖片）。")
    return text
