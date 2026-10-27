"""AI 解釋：把單字與所在句子送給 LLM，取回固定格式的中文解釋。

LLM 服務包在 Provider 介面後面（只要有 complete(system, user) -> str），換一家只要換 Provider；
測試用假的 Provider，不打網路。

回傳內容缺欄位、不是 JSON、欄位是空字串都算失敗，自動重試一次；仍失敗就丟 LLMError。
逾時、額度不足、金鑰錯誤等服務端錯誤不重試，直接轉成 LLMError 讓 API 回友善訊息。
"""

import json
import os
from dataclasses import dataclass, fields
from functools import lru_cache
from typing import Protocol

# 開發測試用 gpt-4.1-mini；展示時在 .env 設 OPENAI_MODEL=gpt-5.4-mini（說明較自然，但較貴）
DEFAULT_MODEL = "gpt-4.1-mini"
TIMEOUT_SECONDS = 20

SYSTEM_PROMPT = """你是日文老師，對象是程度 N4～N2、母語為繁體中文的學習者。
使用者會給你一個日文詞（原形、表記、詞性）和它所在的句子。請只解釋這個詞「在這句話中」的意思與用法，不要列出其他義項。
全部說明使用繁體中文。不確定時直接說明不確定，不要編造。
詞性與原形學習者已經看得到，說明中不要重述，把篇幅用在用法上。
只回傳 JSON，格式如下，四個欄位都必須是非空字串：
- meaning_zh：這個詞在此句中的中文譯詞，只寫譯詞本身（例如「吃」），不要加「意思是」等前言。
- usage_note：用自然的口吻向學習者說明這個詞在句中的用法，兩三句即可，不需要固定格式。如果它是活用後的形態，順帶提是什麼形（例如連用形、て形、否定形）；如果它屬於固定的文法句型（例如「〜らしい」「〜ことにする」），解釋這個文法的意思和用法。
- example_ja：另一個使用相同用法的簡短日文例句。
- example_zh：例句的中文翻譯。"""


@dataclass
class AIExplanation:
    meaning_zh: str
    usage_note: str
    example_ja: str
    example_zh: str


class LLMError(Exception):
    """LLM 呼叫失敗；code 給 API 回傳用，message 是給使用者看的訊息。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Provider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        import openai  # 只有真的要呼叫時才需要這個套件

        self._openai = openai
        self._client = openai.OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        openai = self._openai
        try:
            res = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
        except openai.APITimeoutError:
            raise LLMError("llm_timeout", "AI 回應逾時，請稍後再試。")
        except openai.AuthenticationError:
            raise LLMError("llm_auth", "AI 服務金鑰錯誤，請檢查 .env 的 OPENAI_API_KEY。")
        except openai.RateLimitError as e:
            if getattr(e, "code", None) == "insufficient_quota":
                raise LLMError("llm_quota", "AI 服務額度不足。")
            raise LLMError("llm_rate_limit", "AI 服務忙碌中，請稍後再試。")
        except openai.APIError:
            raise LLMError("llm_unavailable", "AI 服務暫時無法使用，請稍後再試。")
        return res.choices[0].message.content or ""


@lru_cache(maxsize=1)
def get_provider() -> Provider:
    """依環境變數建立 Provider；沒有設定金鑰時丟 LLMError，其他功能照常運作。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("llm_not_configured", "尚未設定 AI 服務金鑰（.env 的 OPENAI_API_KEY）。")
    return OpenAIProvider(api_key, os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))


def build_user_prompt(lemma: str, surface: str, pos: str, sentence: str) -> str:
    return f"原形：{lemma}\n表記：{surface}\n詞性：{pos}\n句子：{sentence}"


def parse_explanation(raw: str) -> AIExplanation | None:
    """驗證 LLM 回傳的 JSON；不合格回傳 None。"""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    values = {}
    for f in fields(AIExplanation):
        value = data.get(f.name)
        if not isinstance(value, str) or not value.strip():
            return None
        values[f.name] = value.strip()
    return AIExplanation(**values)


def explain(provider: Provider, lemma: str, surface: str, pos: str, sentence: str) -> AIExplanation:
    user = build_user_prompt(lemma, surface, pos, sentence)
    for _ in range(2):  # 第一次失敗自動重試一次
        result = parse_explanation(provider.complete(SYSTEM_PROMPT, user))
        if result:
            return result
    raise LLMError("llm_bad_response", "AI 回應格式有誤，請再試一次。")
