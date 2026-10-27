"""API 路由：只做驗證與轉換，邏輯都在 core。"""

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from core.furigana import contains_japanese, pos_class, ruby_segments
from core.tokenizer import tokenize

MAX_TEXT_LENGTH = 2000

router = APIRouter(prefix="/api")


class ApiError(Exception):
    """會轉成 {"error": {"code", "message"}} 的錯誤。"""

    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


class AnalyzeRequest(BaseModel):
    text: str


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    text = req.text
    if not text.strip():
        raise ApiError(400, "empty_text", "請輸入文章。")
    if len(text) > MAX_TEXT_LENGTH:
        raise ApiError(400, "text_too_long", f"文章超過 {MAX_TEXT_LENGTH} 字（目前 {len(text)} 字）。")
    if not contains_japanese(text):
        raise ApiError(400, "no_japanese", "沒有偵測到日文（平假名或片假名）。")
    return {
        "tokens": [
            {
                **asdict(t),
                "pos_class": pos_class(t.pos),
                "ruby": [{"text": s, "rt": rt} for s, rt in ruby_segments(t.surface, t.reading)],
            }
            for t in tokenize(text)
        ]
    }
