"""統計：單字庫與 AI 解釋查詢的彙總數字，給統計頁與 MCP 使用。

時間欄位是 vocab_repo 寫入的本地時間 ISO 字串（2026-10-28T09:30:00），前 10 碼就是日期。
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

DAILY_DAYS = 14


@dataclass
class Stats:
    vocab_total: int             # 單字庫的單字數（一詞多義算一個）
    vocab_this_week: int         # 本週（週一起）新收藏的單字數
    lookups_total: int           # 累計 AI 解釋查詢次數（命中快取也算）
    pos_distribution: list[dict]  # [{"pos": "動詞", "count": 3}]，多的在前
    daily_lookups: list[dict]    # 近 14 天每天的查詢數 [{"date": "2026-10-15", "count": 0}]，舊的在前、含今天


def get_stats(conn: sqlite3.Connection, today: date | None = None) -> Stats:
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    first_day = today - timedelta(days=DAILY_DAYS - 1)

    def count(sql: str, *params) -> int:
        return conn.execute(sql, params).fetchone()[0]

    per_day = dict(conn.execute(
        "SELECT substr(looked_up_at, 1, 10) AS day, COUNT(*) FROM lookup_log WHERE day >= ? GROUP BY day",
        (first_day.isoformat(),),
    ).fetchall())
    days = [first_day + timedelta(days=i) for i in range(DAILY_DAYS)]

    return Stats(
        vocab_total=count("SELECT COUNT(*) FROM vocab"),
        vocab_this_week=count("SELECT COUNT(*) FROM vocab WHERE substr(created_at, 1, 10) >= ?", monday.isoformat()),
        lookups_total=count("SELECT COUNT(*) FROM lookup_log"),
        pos_distribution=[
            {"pos": pos, "count": n}
            for pos, n in conn.execute("SELECT pos, COUNT(*) AS n FROM vocab GROUP BY pos ORDER BY n DESC, pos")
        ],
        daily_lookups=[{"date": d.isoformat(), "count": per_day.get(d.isoformat(), 0)} for d in days],
    )
