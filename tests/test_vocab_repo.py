import json
from dataclasses import asdict
from datetime import datetime

import pytest

from core.llm_client import AIExplanation, LLMError
from core.vocab_repo import (
    DuplicateVocabError, add_vocab, connect, db_path, delete_vocab, explain_with_cache, get_cached_explanation,
    get_vocab, save_cached_explanation, search_vocab,
)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def test_creates_tables(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"vocab", "lookup_cache", "lookup_log"} <= names


def test_creates_db_file_and_parent_dir(tmp_path):
    path = tmp_path / "data" / "furiyomi.db"
    connect(path).close()
    assert path.exists()


def test_db_path_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FURIYOMI_DB", str(tmp_path / "x.db"))
    assert db_path() == tmp_path / "x.db"


def test_add_and_get(conn):
    entry = add_vocab(conn, "食べる", "たべる", "動詞", meaning_zh="吃", context_sentence="ご飯を食べました。",
                      now=datetime(2026, 10, 28, 9, 30))
    assert entry.id > 0
    assert entry.created_at == "2026-10-28T09:30:00"
    assert get_vocab(conn, entry.id) == entry


def test_add_without_ai_explanation_leaves_blank(conn):
    entry = add_vocab(conn, "猫", "ねこ", "名詞")
    assert entry.meaning_zh == "" and entry.usage_note == ""


def test_duplicate_lemma_reports_existing(conn):
    first = add_vocab(conn, "食べる", "たべる", "動詞")
    with pytest.raises(DuplicateVocabError) as exc:
        add_vocab(conn, "食べる", "たべ", "動詞")
    assert exc.value.existing == first
    assert len(search_vocab(conn)) == 1


def test_search_newest_first(conn):
    add_vocab(conn, "猫", "ねこ", "名詞", now=datetime(2026, 10, 27))
    add_vocab(conn, "犬", "いぬ", "名詞", now=datetime(2026, 10, 28))
    assert [e.lemma for e in search_vocab(conn)] == ["犬", "猫"]


def test_search_keyword_matches_lemma_reading_meaning(conn):
    add_vocab(conn, "食べる", "たべる", "動詞", meaning_zh="吃")
    add_vocab(conn, "飲む", "のむ", "動詞", meaning_zh="喝")
    add_vocab(conn, "猫", "ねこ", "名詞", meaning_zh="貓")
    assert [e.lemma for e in search_vocab(conn, keyword="食")] == ["食べる"]
    assert [e.lemma for e in search_vocab(conn, keyword="のむ")] == ["飲む"]
    assert [e.lemma for e in search_vocab(conn, keyword="貓")] == ["猫"]


def test_search_keyword_treats_wildcards_literally(conn):
    add_vocab(conn, "猫", "ねこ", "名詞")
    assert search_vocab(conn, keyword="%") == []
    assert search_vocab(conn, keyword="_") == []


def test_search_blank_keyword_returns_all(conn):
    add_vocab(conn, "猫", "ねこ", "名詞")
    assert len(search_vocab(conn, keyword="  ")) == 1


def test_filter_by_pos(conn):
    add_vocab(conn, "食べる", "たべる", "動詞", meaning_zh="吃")
    add_vocab(conn, "猫", "ねこ", "名詞", meaning_zh="貓")
    assert [e.lemma for e in search_vocab(conn, pos="名詞")] == ["猫"]
    assert search_vocab(conn, keyword="食", pos="名詞") == []


def test_delete(conn):
    entry = add_vocab(conn, "猫", "ねこ", "名詞")
    assert delete_vocab(conn, entry.id) is True
    assert get_vocab(conn, entry.id) is None
    assert delete_vocab(conn, entry.id) is False


def test_can_add_again_after_delete(conn):
    entry = add_vocab(conn, "猫", "ねこ", "名詞")
    delete_vocab(conn, entry.id)
    assert add_vocab(conn, "猫", "ねこ", "名詞").lemma == "猫"


# --- AI 解釋快取與查詢紀錄 ---

EXPLANATION = AIExplanation("吃", "連用形。", "パンを食べます。", "吃麵包。")


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.response


def test_cache_roundtrip(conn):
    assert get_cached_explanation(conn, "食べる", "食べ", "寿司を食べた。") is None
    save_cached_explanation(conn, "食べる", "食べ", "寿司を食べた。", EXPLANATION)
    assert get_cached_explanation(conn, "食べる", "食べ", "寿司を食べた。") == EXPLANATION
    assert get_cached_explanation(conn, "食べる", "食べた", "寿司を食べた。") is None
    assert get_cached_explanation(conn, "食べる", "食べ", "パンを食べた。") is None


def test_explain_with_cache_calls_llm_once(conn):
    provider = FakeProvider(json.dumps(asdict(EXPLANATION)))
    for _ in range(2):
        assert explain_with_cache(conn, lambda: provider, "食べる", "食べ", "動詞", "寿司を食べた。") == EXPLANATION
    assert provider.calls == 1
    rows = conn.execute("SELECT lemma, pos FROM lookup_log").fetchall()
    assert [tuple(r) for r in rows] == [("食べる", "動詞")] * 2


def test_explain_with_cache_hit_does_not_need_provider(conn):
    save_cached_explanation(conn, "食べる", "食べ", "寿司を食べた。", EXPLANATION)

    def no_provider():
        raise LLMError("llm_not_configured", "沒有金鑰")

    assert explain_with_cache(conn, no_provider, "食べる", "食べ", "動詞", "寿司を食べた。") == EXPLANATION


def test_explain_with_cache_failure_not_saved(conn):
    provider = FakeProvider("壞掉")
    with pytest.raises(LLMError):
        explain_with_cache(conn, lambda: provider, "食べる", "食べ", "動詞", "寿司を食べた。")
    assert conn.execute("SELECT COUNT(*) FROM lookup_cache").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM lookup_log").fetchone()[0] == 0
