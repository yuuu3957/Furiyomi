"""API 路由：只做驗證與轉換，邏輯都在 core。"""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.furigana import contains_japanese, pos_class, ruby_segments
from core.llm_client import LLMError, Provider, explain, get_provider
from core.tokenizer import tokenize

MAX_TEXT_LENGTH = 2000

router = APIRouter(prefix="/api")


class ApiError(Exception):
    """會轉成 {"error": {"code", "message"}} 的錯誤。"""

    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def llm_provider() -> Provider:
    """測試用 app.dependency_overrides 換成假的 Provider。"""
    try:
        return get_provider()
    except LLMError as e:
        raise ApiError(503, e.code, e.message)


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


class ExplainRequest(BaseModel):
    lemma: str = Field(min_length=1, max_length=100)
    surface: str = Field(min_length=1, max_length=100)
    pos: str = Field(max_length=50)
    sentence: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


@router.post("/explain")
def explain_word(req: ExplainRequest, provider: Provider = Depends(llm_provider)):
    try:
        result = explain(provider, req.lemma, req.surface, req.pos, req.sentence)
    except LLMError as e:
        raise ApiError(502 if e.code == "llm_bad_response" else 503, e.code, e.message)
    return asdict(result)
