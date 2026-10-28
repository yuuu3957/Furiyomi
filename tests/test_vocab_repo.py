import json
from dataclasses import asdict
from datetime import datetime

import pytest

from core.llm_client import AIExplanation, LLMError
from core.vocab_repo import (
    DuplicateVocabError, add_vocab, connect, db_path, delete_example, delete_vocab, explain_with_cache,
    fill_missing_meaning, get_cached_explanation, get_vocab, save_cached_explanation, search_vocab,
)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def test_creates_tables(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"vocab", "vocab_example", "lookup_cache", "lookup_log"} <= names


def test_creates_db_file_and_parent_dir(tmp_path):
    path = tmp_path / "data" / "furiyomi.db"
    connect(path).close()
    assert path.exists()


def test_db_path_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FURIYOMI_DB", str(tmp_path / "x.db"))
    assert db_path() == tmp_path / "x.db"


def test_add_and_get(conn):
    entry = add_vocab(conn, "食べる", "たべる", "動詞", surface="食べ", context_sentence="ご飯を食べました。",
                      meaning_zh="吃", now=datetime(2026, 10, 28, 9, 30))
    assert entry.id > 0
    assert entry.created_at == "2026-10-28T09:30:00"
    [ex] = entry.examples
    assert (ex.surface, ex.context_sentence, ex.meaning_zh) == ("食べ", "ご飯を食べました。", "吃")
    assert get_vocab(conn, entry.id) == entry


def test_add_without_ai_explanation_leaves_blank(conn):
    entry = add_vocab(conn, "猫", "ねこ", "名詞")
    assert entry.examples[0].meaning_zh == "" and entry.examples[0].usage_note == ""


def test_same_lemma_in_another_sentence_adds_example(conn):
    first = add_vocab(conn, "かける", "かける", "動詞", context_sentence="電話をかける。", meaning_zh="打（電話）",
                      now=datetime(2026, 10, 27))
    second = add_vocab(conn, "かける", "かけ", "動詞", context_sentence="眼鏡をかけた。", meaning_zh="戴",
                       now=datetime(2026, 10, 28))
    assert second.id == first.id
    assert second.reading == "かける" and second.created_at == first.created_at  # 詞的資料維持第一次收藏時
    assert [ex.meaning_zh for ex in second.examples] == ["打（電話）", "戴"]
    assert len(search_vocab(conn)) == 1


def test_duplicate_sentence_reports_existing(conn):
    first = add_vocab(conn, "食べる", "たべる", "動詞", context_sentence="ご飯を食べた。")
    with pytest.raises(DuplicateVocabError) as exc:
        add_vocab(conn, "食べる", "たべる", "動詞", context_sentence="ご飯を食べた。")
    assert exc.value.existing == first
    assert len(get_vocab(conn, first.id).examples) == 1


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


def test_search_keyword_matches_any_example_meaning(conn):
    add_vocab(conn, "かける", "かける", "動詞", context_sentence="電話をかける。", meaning_zh="打（電話）")
    add_vocab(conn, "かける", "かける", "動詞", context_sentence="眼鏡をかけた。", meaning_zh="戴")
    [entry] = search_vocab(conn, keyword="戴")
    assert len(entry.examples) == 2  # 回傳整個詞，所有例句都在


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


def test_delete_removes_examples(conn):
    entry = add_vocab(conn, "猫", "ねこ", "名詞", context_sentence="猫がいる。")
    assert delete_vocab(conn, entry.id) is True
    assert get_vocab(conn, entry.id) is None
    assert conn.execute("SELECT COUNT(*) FROM vocab_example").fetchone()[0] == 0
    assert delete_vocab(conn, entry.id) is False


def test_can_add_again_after_delete(conn):
    entry = add_vocab(conn, "猫", "ねこ", "名詞")
    delete_vocab(conn, entry.id)
    assert add_vocab(conn, "猫", "ねこ", "名詞").lemma == "猫"


def test_delete_example_keeps_word(conn):
    add_vocab(conn, "かける", "かける", "動詞", context_sentence="電話をかける。")
    entry = add_vocab(conn, "かける", "かける", "動詞", context_sentence="眼鏡をかけた。")
    assert delete_example(conn, entry.examples[0].id) == 0
    assert [ex.context_sentence for ex in get_vocab(conn, entry.id).examples] == ["眼鏡をかけた。"]


def test_delete_last_example_removes_word(conn):
    entry = add_vocab(conn, "猫", "ねこ", "名詞", context_sentence="猫がいる。")
    assert delete_example(conn, entry.examples[0].id) == entry.id
    assert get_vocab(conn, entry.id) is None
    assert delete_example(conn, entry.examples[0].id) is None


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


def test_fill_missing_meaning(conn):
    entry = add_vocab(conn, "食べる", "たべる", "動詞", context_sentence="寿司を食べた。")
    assert fill_missing_meaning(conn, "食べる", "寿司を食べた。", EXPLANATION) is True
    [ex] = get_vocab(conn, entry.id).examples
    assert (ex.meaning_zh, ex.usage_note) == ("吃", "連用形。")


def test_fill_missing_meaning_only_that_sentence(conn):
    add_vocab(conn, "食べる", "たべる", "動詞", context_sentence="寿司を食べた。")
    entry = add_vocab(conn, "食べる", "たべる", "動詞", context_sentence="パンを食べる。")
    fill_missing_meaning(conn, "食べる", "パンを食べる。", EXPLANATION)
    assert [ex.meaning_zh for ex in get_vocab(conn, entry.id).examples] == ["", "吃"]


def test_fill_missing_meaning_keeps_existing(conn):
    entry = add_vocab(conn, "食べる", "たべる", "動詞", context_sentence="寿司を食べた。", meaning_zh="進食")
    assert fill_missing_meaning(conn, "食べる", "寿司を食べた。", EXPLANATION) is False
    assert get_vocab(conn, entry.id).examples[0].meaning_zh == "進食"


def test_explain_with_cache_fills_collected_word(conn):
    entry = add_vocab(conn, "食べる", "たべる", "動詞", context_sentence="寿司を食べた。")
    provider = FakeProvider(json.dumps(asdict(EXPLANATION)))
    explain_with_cache(conn, lambda: provider, "食べる", "食べ", "動詞", "寿司を食べた。")
    assert get_vocab(conn, entry.id).examples[0].meaning_zh == "吃"
