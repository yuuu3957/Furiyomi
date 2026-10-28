"""API 路由：只做驗證與轉換，邏輯都在 core。"""

import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from functools import lru_cache

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel, Field

from core.furigana import contains_japanese, pos_class, ruby_segments
from core.llm_client import LLMError, Provider, get_provider
from core.paging import PAGE_LIMIT, split_pages
from core.pdf_reader import PdfError, extract_text
from core.tokenizer import lemma_reading, tokenize
from core.vocab_repo import (
    DuplicateVocabError, add_vocab, connect, delete_example, delete_vocab, explain_with_cache, search_vocab,
)

MAX_TEXT_LENGTH = PAGE_LIMIT  # /analyze 一次只處理一頁
MAX_DOCUMENT_LENGTH = 20000
MAX_PDF_BYTES = 20 * 1024 * 1024

router = APIRouter(prefix="/api")


class ApiError(Exception):
    """會轉成 {"error": {"code", "message"}} 的錯誤。"""

    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def llm_provider() -> Callable[[], Provider]:
    """回傳取得 Provider 的函式，命中快取時就不必建立；測試用 app.dependency_overrides 換成假的。"""
    return get_provider


@lru_cache(maxsize=1)
def get_db() -> sqlite3.Connection:
    """整個程式共用一個連線；測試用 app.dependency_overrides 換成記憶體資料庫。"""
    return connect()


class TextRequest(BaseModel):
    text: str


def check_text(text: str, max_length: int) -> None:
    if not text.strip():
        raise ApiError(400, "empty_text", "請輸入文章。")
    if len(text) > max_length:
        raise ApiError(400, "text_too_long", f"文章超過 {max_length:,} 字（目前 {len(text):,} 字）。")
    if not contains_japanese(text):
        raise ApiError(400, "no_japanese", "沒有偵測到日文（平假名或片假名）。")


@router.post("/paginate")
def paginate(req: TextRequest):
    check_text(req.text, MAX_DOCUMENT_LENGTH)
    return {"pages": split_pages(req.text)}


@router.post("/pdf/extract")
async def pdf_extract(file: UploadFile):
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise ApiError(400, "file_too_large", "PDF 檔案超過 20 MB。")
    try:
        text = extract_text(data)
    except PdfError as e:
        raise ApiError(400, e.code, e.message)
    check_text(text, MAX_DOCUMENT_LENGTH)
    return {"pages": split_pages(text)}


@router.post("/analyze")
def analyze(req: TextRequest):
    check_text(req.text, MAX_TEXT_LENGTH)
    return {
        "tokens": [
            {
                **asdict(t),
                "pos_class": pos_class(t.pos),
                "ruby": [{"text": s, "rt": rt} for s, rt in ruby_segments(t.surface, t.reading)],
            }
            for t in tokenize(req.text)
        ]
    }


class ExplainRequest(BaseModel):
    lemma: str = Field(min_length=1, max_length=100)
    surface: str = Field(min_length=1, max_length=100)
    pos: str = Field(max_length=50)
    sentence: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


@router.post("/explain")
def explain_word(
    req: ExplainRequest,
    provider: Callable[[], Provider] = Depends(llm_provider),
    db: sqlite3.Connection = Depends(get_db),
):
    try:
        result = explain_with_cache(db, provider, req.lemma, req.surface, req.pos, req.sentence)
    except LLMError as e:
        raise ApiError(502 if e.code == "llm_bad_response" else 503, e.code, e.message)
    return asdict(result)


class VocabRequest(BaseModel):
    lemma: str = Field(min_length=1, max_length=100)
    reading: str = Field("", max_length=100)  # 空白時由原形推算
    pos: str = Field(max_length=50)
    surface: str = Field("", max_length=100)
    meaning_zh: str = Field("", max_length=200)
    usage_note: str = Field("", max_length=2000)
    context_sentence: str = Field("", max_length=MAX_TEXT_LENGTH)


@router.get("/vocab")
def list_vocab(keyword: str | None = None, pos: str | None = None, db: sqlite3.Connection = Depends(get_db)):
    return {"items": [asdict(e) for e in search_vocab(db, keyword, pos)]}


@router.post("/vocab", status_code=201)
def create_vocab(req: VocabRequest, db: sqlite3.Connection = Depends(get_db)):
    try:
        entry = add_vocab(db, **{**req.model_dump(), "reading": req.reading or lemma_reading(req.lemma)})
    except DuplicateVocabError as e:
        raise ApiError(409, "vocab_exists", str(e))
    return asdict(entry)


@router.delete("/vocab/{vocab_id}")
def remove_vocab(vocab_id: int, db: sqlite3.Connection = Depends(get_db)):
    if not delete_vocab(db, vocab_id):
        raise ApiError(404, "vocab_not_found", "找不到這個單字，可能已被刪除。")
    return {"deleted": vocab_id}


@router.delete("/vocab/examples/{example_id}")
def remove_example(example_id: int, db: sqlite3.Connection = Depends(get_db)):
    deleted_vocab = delete_example(db, example_id)
    if deleted_vocab is None:
        raise ApiError(404, "example_not_found", "找不到這個例句，可能已被刪除。")
    # 刪掉最後一個例句時詞也一起刪除，前端據此更新收藏狀態
    return {"deleted": example_id, "deleted_vocab": deleted_vocab or None}
