import pytest
from fastapi.testclient import TestClient

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
