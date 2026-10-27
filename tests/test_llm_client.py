import json

import httpx
import openai
import pytest

from core.llm_client import (
    SYSTEM_PROMPT, AIExplanation, LLMError, OpenAIProvider, explain, get_provider, parse_explanation,
)

VALID = {
    "meaning_zh": "吃",
    "usage_note": "「食べる」的連用形，後接「ます」。",
    "example_ja": "パンを食べます。",
    "example_zh": "吃麵包。",
}


class FakeProvider:
    """依序回傳預先準備的回應，並記錄收到的 prompt。"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.responses.pop(0)


def run(provider):
    return explain(provider, "食べる", "食べ", "動詞", "寿司を食べました。")


def test_valid_json():
    provider = FakeProvider(json.dumps(VALID))
    assert run(provider) == AIExplanation(**VALID)
    assert len(provider.calls) == 1


def test_prompt_contains_word_and_sentence():
    provider = FakeProvider(json.dumps(VALID))
    run(provider)
    system, user = provider.calls[0]
    assert system == SYSTEM_PROMPT
    assert "繁體中文" in system
    for text in ["食べる", "食べ", "動詞", "寿司を食べました。"]:
        assert text in user


@pytest.mark.parametrize("raw", [
    "這不是 JSON",
    "",
    "[1, 2]",
    json.dumps({k: v for k, v in VALID.items() if k != "example_zh"}),  # 缺欄位
    json.dumps({**VALID, "meaning_zh": "  "}),                          # 空字串
    json.dumps({**VALID, "usage_note": 123}),                           # 型別錯誤
])
def test_parse_rejects_bad_response(raw):
    assert parse_explanation(raw) is None


def test_parse_strips_whitespace_and_ignores_extra_fields():
    result = parse_explanation(json.dumps({**VALID, "meaning_zh": " 吃 ", "extra": "x"}))
    assert result.meaning_zh == "吃"


def test_retry_once_then_succeed():
    provider = FakeProvider("壞掉的回應", json.dumps(VALID))
    assert run(provider) == AIExplanation(**VALID)
    assert len(provider.calls) == 2


def test_fail_after_retry():
    provider = FakeProvider("壞掉", "{}")
    with pytest.raises(LLMError) as e:
        run(provider)
    assert e.value.code == "llm_bad_response"
    assert len(provider.calls) == 2


def test_service_error_not_retried():
    class Failing:
        calls = 0

        def complete(self, system, user):
            self.calls += 1
            raise LLMError("llm_timeout", "逾時")

    provider = Failing()
    with pytest.raises(LLMError):
        run(provider)
    assert provider.calls == 1


def test_get_provider_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_provider.cache_clear()
    with pytest.raises(LLMError) as e:
        get_provider()
    assert e.value.code == "llm_not_configured"
    get_provider.cache_clear()


# --- OpenAIProvider：用 mock 取代真正的 API 呼叫 ---

_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _status_error(cls, status, code=None):
    body = {"code": code} if code else None
    return cls("error", response=httpx.Response(status, request=_REQUEST), body=body)


@pytest.mark.parametrize("error, code", [
    (openai.APITimeoutError(request=_REQUEST), "llm_timeout"),
    (_status_error(openai.AuthenticationError, 401), "llm_auth"),
    (_status_error(openai.RateLimitError, 429, "insufficient_quota"), "llm_quota"),
    (_status_error(openai.RateLimitError, 429), "llm_rate_limit"),
    (_status_error(openai.InternalServerError, 500), "llm_unavailable"),
    (openai.APIConnectionError(request=_REQUEST), "llm_unavailable"),
])
def test_openai_errors_mapped(monkeypatch, error, code):
    provider = OpenAIProvider("sk-test")

    def raise_error(**kwargs):
        raise error

    monkeypatch.setattr(provider._client.chat.completions, "create", raise_error)
    with pytest.raises(LLMError) as e:
        provider.complete("system", "user")
    assert e.value.code == code


def test_openai_returns_content(monkeypatch):
    provider = OpenAIProvider("sk-test", model="test-model")
    seen = {}

    def fake_create(**kwargs):
        seen.update(kwargs)
        message = type("M", (), {"content": json.dumps(VALID)})
        choice = type("C", (), {"message": message})
        return type("R", (), {"choices": [choice]})

    monkeypatch.setattr(provider._client.chat.completions, "create", fake_create)
    assert parse_explanation(provider.complete("system", "user")) == AIExplanation(**VALID)
    assert seen["model"] == "test-model"
    assert seen["response_format"] == {"type": "json_object"}
