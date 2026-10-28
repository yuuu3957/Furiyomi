from datetime import date, datetime

import pytest

from core.stats import get_stats
from core.vocab_repo import add_vocab, connect, log_lookup

TODAY = date(2026, 10, 28)  # 星期三，本週從 10/26（一）開始


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def test_empty_database(conn):
    stats = get_stats(conn, TODAY)
    assert (stats.vocab_total, stats.vocab_this_week, stats.lookups_total) == (0, 0, 0)
    assert stats.pos_distribution == []
    assert len(stats.daily_lookups) == 14
    assert stats.daily_lookups[0] == {"date": "2026-10-15", "count": 0}
    assert stats.daily_lookups[-1] == {"date": "2026-10-28", "count": 0}


def test_vocab_counts_and_this_week(conn):
    add_vocab(conn, "猫", "名詞", "ねこ", now=datetime(2026, 10, 25, 23, 59))  # 上週日
    add_vocab(conn, "犬", "名詞", "いぬ", now=datetime(2026, 10, 26, 0, 0))   # 本週一
    add_vocab(conn, "食べる", "動詞", "たべる", context_sentence="寿司を食べた。", now=datetime(2026, 10, 28))
    # 一詞多義：同一個詞多一個例句，單字數不變
    add_vocab(conn, "食べる", "動詞", "たべる", context_sentence="パンを食べる。", now=datetime(2026, 10, 28))
    stats = get_stats(conn, TODAY)
    assert stats.vocab_total == 3
    assert stats.vocab_this_week == 2


def test_pos_distribution_most_first(conn):
    add_vocab(conn, "食べる", "動詞", "たべる")
    add_vocab(conn, "猫", "名詞", "ねこ")
    add_vocab(conn, "犬", "名詞", "いぬ")
    assert get_stats(conn, TODAY).pos_distribution == [{"pos": "名詞", "count": 2}, {"pos": "動詞", "count": 1}]


def test_daily_lookups_last_14_days(conn):
    log_lookup(conn, "食べる", "動詞", now=datetime(2026, 10, 14, 12))  # 超過 14 天：只算進累計
    log_lookup(conn, "食べる", "動詞", now=datetime(2026, 10, 15, 8))
    log_lookup(conn, "食べる", "動詞", now=datetime(2026, 10, 28, 9))
    log_lookup(conn, "猫", "名詞", now=datetime(2026, 10, 28, 21))
    stats = get_stats(conn, TODAY)
    assert stats.lookups_total == 4
    counts = {d["date"]: d["count"] for d in stats.daily_lookups}
    assert counts["2026-10-15"] == 1
    assert counts["2026-10-28"] == 2
    assert sum(counts.values()) == 3
