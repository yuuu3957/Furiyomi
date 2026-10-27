import json

import pytest
from fastapi.testclient import TestClient

from api.routes import llm_provider
from core.llm_client import LLMError, get_provider
from main import app

client = TestClient(app)


def analyze(text):
    return client.post("/api/analyze", json={"text": text})


def test_analyze_returns_tokens_with_ruby():
    res = analyze("寿司を食べました。")
    assert res.status_code == 200
    tokens = res.json()["tokens"]
    assert "".join(t["surface"] for t in tokens) == "寿司を食べました。"
    tabe = next(t for t in tokens if t["surface"] == "食べ")
    assert tabe["lemma"] == "食べる"
    assert tabe["ruby"] == [{"text": "食", "rt": "た"}, {"text": "べ", "rt": None}]
    assert tabe["pos_class"] == "verb"
    wo = next(t for t in tokens if t["surface"] == "を")
    assert wo["ruby"] == [{"text": "を", "rt": None}]


@pytest.mark.parametrize("text, code", [
    ("", "empty_text"),
    ("  \n ", "empty_text"),
    ("あ" * 2001, "text_too_long"),
    ("我今天吃了壽司。", "no_japanese"),
])
def test_analyze_rejects_bad_input(text, code):
    res = analyze(text)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == code


def test_analyze_accepts_max_length():
    assert analyze("あ" * 2000).status_code == 200


@pytest.mark.parametrize("body", [{}, {"text": 123}, None])
def test_analyze_invalid_body(body):
    res = client.post("/api/analyze", json=body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_request"


def test_unknown_api_path_uses_error_format():
    res = client.get("/api/nope")
    assert res.status_code == 404
    assert "error" in res.json()


def test_index_page_served():
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


# --- /api/explain：用假的 Provider，不打網路 ---

EXPLAIN_BODY = {"lemma": "食べる", "surface": "食べ", "pos": "動詞", "sentence": "寿司を食べました。"}
EXPLANATION = {"meaning_zh": "吃", "usage_note": "說明", "example_ja": "パンを食べます。", "example_zh": "吃麵包。"}


class FakeProvider:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def complete(self, system, user):
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def use_provider():
    def install(provider):
        app.dependency_overrides[llm_provider] = lambda: provider
    yield install
    app.dependency_overrides.clear()


def test_explain_ok(use_provider):
    use_provider(FakeProvider(json.dumps(EXPLANATION)))
    res = client.post("/api/explain", json=EXPLAIN_BODY)
    assert res.status_code == 200
    assert res.json() == EXPLANATION


def test_explain_bad_response(use_provider):
    use_provider(FakeProvider("不是 JSON"))
    res = client.post("/api/explain", json=EXPLAIN_BODY)
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "llm_bad_response"


def test_explain_service_error(use_provider):
    use_provider(FakeProvider(error=LLMError("llm_quota", "AI 服務額度不足。")))
    res = client.post("/api/explain", json=EXPLAIN_BODY)
    assert res.status_code == 503
    assert res.json()["error"] == {"code": "llm_quota", "message": "AI 服務額度不足。"}


def test_explain_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_provider.cache_clear()
    res = client.post("/api/explain", json=EXPLAIN_BODY)
    get_provider.cache_clear()
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "llm_not_configured"


@pytest.mark.parametrize("override", [{"lemma": ""}, {"sentence": ""}, {"surface": "あ" * 101}])
def test_explain_invalid_body(use_provider, override):
    use_provider(FakeProvider("{}"))
    res = client.post("/api/explain", json={**EXPLAIN_BODY, **override})
    assert res.status_code == 422
