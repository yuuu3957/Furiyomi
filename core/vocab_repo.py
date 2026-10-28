"""單字庫：SQLite 存取（收藏、搜尋、篩選、刪除）。

資料庫檔預設放在 data/furiyomi.db，可用環境變數 FURIYOMI_DB 改路徑；檔案不存在時自動建立。
函式都接收 connection，測試用 ":memory:"，不碰真正的資料庫檔。
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "furiyomi.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vocab (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL UNIQUE,
    reading TEXT NOT NULL,
    pos TEXT NOT NULL,
    meaning_zh TEXT NOT NULL DEFAULT '',
    usage_note TEXT NOT NULL DEFAULT '',
    context_sentence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lookup_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL,
    sentence_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (lemma, sentence_hash)
);
CREATE TABLE IF NOT EXISTS lookup_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL,
    pos TEXT NOT NULL,
    looked_up_at TEXT NOT NULL
);
"""


@dataclass
class VocabEntry:
    id: int
    lemma: str
    reading: str
    pos: str
    meaning_zh: str
    usage_note: str
    context_sentence: str
    created_at: str


class DuplicateVocabError(Exception):
    """同一個原形已經收藏過；existing 是已存在的那一筆。"""

    def __init__(self, existing: VocabEntry):
        super().__init__(f"「{existing.lemma}」已在單字庫中。")
        self.existing = existing


def db_path() -> Path:
    return Path(os.environ.get("FURIYOMI_DB") or DEFAULT_DB_PATH)


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """開啟資料庫並建立資料表；path 用 ":memory:" 時是記憶體資料庫。"""
    path = db_path() if path is None else path
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)  # FastAPI 會在不同執行緒使用同一個連線
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now(now: datetime | None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")


def _entry(row: sqlite3.Row) -> VocabEntry:
    return VocabEntry(**dict(row))


def get_vocab(conn: sqlite3.Connection, vocab_id: int) -> VocabEntry | None:
    row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    return _entry(row) if row else None


def get_vocab_by_lemma(conn: sqlite3.Connection, lemma: str) -> VocabEntry | None:
    row = conn.execute("SELECT * FROM vocab WHERE lemma = ?", (lemma,)).fetchone()
    return _entry(row) if row else None


def add_vocab(
    conn: sqlite3.Connection,
    lemma: str,
    reading: str,
    pos: str,
    meaning_zh: str = "",
    usage_note: str = "",
    context_sentence: str = "",
    now: datetime | None = None,
) -> VocabEntry:
    """收藏一個詞；同原形已存在時丟 DuplicateVocabError。還沒查 AI 解釋時中文意思先留空。"""
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO vocab (lemma, reading, pos, meaning_zh, usage_note, context_sentence, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lemma, reading, pos, meaning_zh, usage_note, context_sentence, _now(now)),
            )
    except sqlite3.IntegrityError:
        raise DuplicateVocabError(get_vocab_by_lemma(conn, lemma))
    return get_vocab(conn, cur.lastrowid)


def _escape_like(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_vocab(conn: sqlite3.Connection, keyword: str | None = None, pos: str | None = None) -> list[VocabEntry]:
    """依關鍵字（比對原形、讀音、中文意思）與詞性篩選，新收藏的在前面。"""
    sql = "SELECT * FROM vocab WHERE 1 = 1"
    params: list[str] = []
    if keyword and keyword.strip():
        pattern = f"%{_escape_like(keyword.strip())}%"
        sql += " AND (lemma LIKE ? ESCAPE '\\' OR reading LIKE ? ESCAPE '\\' OR meaning_zh LIKE ? ESCAPE '\\')"
        params += [pattern] * 3
    if pos:
        sql += " AND pos = ?"
        params.append(pos)
    sql += " ORDER BY created_at DESC, id DESC"
    return [_entry(row) for row in conn.execute(sql, params)]


def delete_vocab(conn: sqlite3.Connection, vocab_id: int) -> bool:
    """刪除一筆；找不到時回傳 False。"""
    with conn:
        cur = conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))
    return cur.rowcount > 0
