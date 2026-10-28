import json

import pytest
from fastapi.testclient import TestClient

from api.routes import get_db, llm_provider
from core.llm_client import LLMError, get_provider
from core.vocab_repo import connect
from main import app
from tests.test_pdf_reader import make_pdf

client = TestClient(app)


@pytest.fixture(autouse=True)
def db():
    """每個測試用新的記憶體資料庫，不碰 data/furiyomi.db。"""
    conn = connect(":memory:")
    app.dependency_overrides[get_db] = lambda: conn
    yield conn
    app.dependency_overrides.pop(get_db, None)
    conn.close()


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


def test_paginate_splits_long_text():
    text = "今日は晴れです。\n" * 500  # 4,500 字
    res = client.post("/api/paginate", json={"text": text})
    assert res.status_code == 200
    pages = res.json()["pages"]
    assert len(pages) == 3
    assert "".join(pages) == text


@pytest.mark.parametrize("text, code", [
    ("", "empty_text"),
    ("あ" * 20001, "text_too_long"),
    ("我今天吃了壽司。", "no_japanese"),
], ids=["empty", "too_long", "no_japanese"])
def test_paginate_rejects_bad_input(text, code):
    res = client.post("/api/paginate", json={"text": text})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == code


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
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def use_provider():
    def install(provider):
        app.dependency_overrides[llm_provider] = lambda: lambda: provider
    yield install
    app.dependency_overrides.pop(llm_provider, None)


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


def lookup_count(db):
    return db.execute("SELECT COUNT(*) FROM lookup_log").fetchone()[0]


def test_explain_second_time_uses_cache(use_provider, db):
    provider = FakeProvider(json.dumps(EXPLANATION))
    use_provider(provider)
    client.post("/api/explain", json=EXPLAIN_BODY)
    res = client.post("/api/explain", json=EXPLAIN_BODY)
    assert res.json() == EXPLANATION
    assert provider.calls == 1
    assert lookup_count(db) == 2  # 命中快取也記錄


def test_explain_cache_keyed_by_selection(use_provider):
    provider = FakeProvider(json.dumps(EXPLANATION))
    use_provider(provider)
    client.post("/api/explain", json=EXPLAIN_BODY)
    client.post("/api/explain", json={**EXPLAIN_BODY, "surface": "食べました"})
    assert provider.calls == 2


def test_explain_cached_works_without_api_key(use_provider, monkeypatch):
    use_provider(FakeProvider(json.dumps(EXPLANATION)))
    client.post("/api/explain", json=EXPLAIN_BODY)
    app.dependency_overrides.pop(llm_provider)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_provider.cache_clear()
    res = client.post("/api/explain", json=EXPLAIN_BODY)
    get_provider.cache_clear()
    assert res.json() == EXPLANATION


def test_explain_failure_not_cached_or_logged(use_provider, db):
    use_provider(FakeProvider("不是 JSON"))
    client.post("/api/explain", json=EXPLAIN_BODY)
    assert db.execute("SELECT COUNT(*) FROM lookup_cache").fetchone()[0] == 0
    assert lookup_count(db) == 0


@pytest.mark.parametrize("override", [{"lemma": ""}, {"sentence": ""}, {"surface": "あ" * 101}])
def test_explain_invalid_body(use_provider, override):
    use_provider(FakeProvider("{}"))
    res = client.post("/api/explain", json={**EXPLAIN_BODY, **override})
    assert res.status_code == 422


# --- PDF ---

def upload_pdf(data, name="article.pdf"):
    return client.post("/api/pdf/extract", files={"file": (name, data, "application/pdf")})


def test_pdf_extract_returns_pages():
    res = upload_pdf(make_pdf([["今日は天気がいいので、公園へ", "散歩に行きました。"]]))
    assert res.status_code == 200
    assert res.json()["pages"] == ["今日は天気がいいので、公園へ散歩に行きました。"]


@pytest.mark.parametrize("pages, code", [
    ([[]], "no_text"),
    ([["Hello world."]], "no_japanese"),
])
def test_pdf_extract_rejects_unusable_pdf(pages, code):
    res = upload_pdf(make_pdf(pages))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == code


def test_pdf_extract_rejects_non_pdf():
    res = upload_pdf(b"not a pdf", name="note.txt")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_pdf"


def test_pdf_extract_rejects_large_file(monkeypatch):
    monkeypatch.setattr("api.routes.MAX_PDF_BYTES", 10)
    res = upload_pdf(make_pdf([["大きいファイル。"]]))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "file_too_large"


def test_pdf_extract_requires_file():
    res = client.post("/api/pdf/extract")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_request"


# --- /api/vocab ---

VOCAB_BODY = {"lemma": "食べる", "reading": "たべる", "pos": "動詞", "meaning_zh": "吃",
              "usage_note": "說明", "context_sentence": "寿司を食べました。"}


def test_vocab_add_and_list():
    res = client.post("/api/vocab", json=VOCAB_BODY)
    assert res.status_code == 201
    entry = res.json()
    assert {k: entry[k] for k in VOCAB_BODY} == VOCAB_BODY
    assert entry["id"] > 0 and entry["created_at"]
    assert client.get("/api/vocab").json() == {"items": [entry]}


def test_vocab_add_without_ai_explanation():
    res = client.post("/api/vocab", json={"lemma": "猫", "reading": "ねこ", "pos": "名詞"})
    assert res.status_code == 201
    assert res.json()["meaning_zh"] == ""


def test_vocab_reading_from_lemma():
    res = client.post("/api/vocab", json={"lemma": "食べる", "pos": "動詞"})
    assert res.json()["reading"] == "たべる"


def test_vocab_duplicate():
    client.post("/api/vocab", json=VOCAB_BODY)
    res = client.post("/api/vocab", json=VOCAB_BODY)
    assert res.status_code == 409
    assert res.json()["error"] == {"code": "vocab_exists", "message": "「食べる」已在單字庫中。"}


def test_vocab_invalid_body():
    res = client.post("/api/vocab", json={**VOCAB_BODY, "lemma": ""})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_request"


def test_vocab_search_and_filter():
    client.post("/api/vocab", json=VOCAB_BODY)
    client.post("/api/vocab", json={"lemma": "猫", "reading": "ねこ", "pos": "名詞", "meaning_zh": "貓"})
    lemmas = lambda params: [e["lemma"] for e in client.get("/api/vocab", params=params).json()["items"]]
    assert lemmas({"keyword": "貓"}) == ["猫"]
    assert lemmas({"pos": "動詞"}) == ["食べる"]
    assert lemmas({"keyword": "食", "pos": "名詞"}) == []


def test_vocab_delete():
    vocab_id = client.post("/api/vocab", json=VOCAB_BODY).json()["id"]
    assert client.delete(f"/api/vocab/{vocab_id}").json() == {"deleted": vocab_id}
    assert client.get("/api/vocab").json() == {"items": []}
    res = client.delete(f"/api/vocab/{vocab_id}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "vocab_not_found"

