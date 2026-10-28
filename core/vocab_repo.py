"""單字庫：SQLite 存取（收藏、搜尋、篩選、刪除），以及 AI 解釋的快取與查詢紀錄。

一個原形一筆（vocab），在不同句子收藏就多一個例句（vocab_example），一詞多義的中文意思各自保存。

資料庫檔預設放在 data/furiyomi.db，可用環境變數 FURIYOMI_DB 改路徑；檔案不存在時自動建立。
函式都接收 connection，測試用 ":memory:"，不碰真正的資料庫檔。
"""

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core.llm_client import AIExplanation, Provider, explain, parse_explanation
from core.tokenizer import lemma_reading

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "furiyomi.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vocab (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL UNIQUE,
    reading TEXT NOT NULL,
    pos TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vocab_example (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocab_id INTEGER NOT NULL REFERENCES vocab (id) ON DELETE CASCADE,
    surface TEXT NOT NULL DEFAULT '',
    context_sentence TEXT NOT NULL DEFAULT '',
    meaning_zh TEXT NOT NULL DEFAULT '',
    usage_note TEXT NOT NULL DEFAULT '',
    example_ja TEXT NOT NULL DEFAULT '',
    example_zh TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (vocab_id, context_sentence)
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
class VocabExample:
    """同一個詞在不同句子裡收藏一次就是一個例句；中文意思是該句中的意思（一詞多義各自保存）。
    meaning_zh 到 example_zh 是該句的 AI 解釋，還沒查時是空白。"""
    id: int
    surface: str
    context_sentence: str
    meaning_zh: str
    usage_note: str
    example_ja: str
    example_zh: str
    created_at: str


@dataclass
class VocabEntry:
    id: int
    lemma: str
    reading: str
    pos: str
    created_at: str
    examples: list[VocabExample] = field(default_factory=list)


class DuplicateVocabError(Exception):
    """同一個原形在同一句已經收藏過；existing 是已存在的那個詞。"""

    def __init__(self, existing: VocabEntry):
        super().__init__(f"「{existing.lemma}」的這個例句已在單字庫中。")
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
    conn.execute("PRAGMA foreign_keys = ON")  # 刪除詞時一併刪除例句
    conn.executescript(SCHEMA)
    return conn


def _now(now: datetime | None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")


def _entries(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[VocabEntry]:
    """把詞的資料列加上各自的例句（依收藏先後）。"""
    entries = {row["id"]: VocabEntry(**dict(row)) for row in rows}
    if entries:
        marks = ",".join("?" * len(entries))
        for ex in conn.execute(
            f"SELECT * FROM vocab_example WHERE vocab_id IN ({marks}) ORDER BY created_at, id", list(entries)
        ):
            ex = dict(ex)
            entries[ex.pop("vocab_id")].examples.append(VocabExample(**ex))
    return list(entries.values())


def get_vocab(conn: sqlite3.Connection, vocab_id: int) -> VocabEntry | None:
    rows = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchall()
    return next(iter(_entries(conn, rows)), None)


def get_vocab_by_lemma(conn: sqlite3.Connection, lemma: str) -> VocabEntry | None:
    rows = conn.execute("SELECT * FROM vocab WHERE lemma = ?", (lemma,)).fetchall()
    return next(iter(_entries(conn, rows)), None)


def add_vocab(
    conn: sqlite3.Connection,
    lemma: str,
    pos: str,
    reading: str = "",
    surface: str = "",
    context_sentence: str = "",
    meaning_zh: str = "",
    usage_note: str = "",
    example_ja: str = "",
    example_zh: str = "",
    now: datetime | None = None,
) -> VocabEntry:
    """收藏一個詞與它所在的句子：新的詞就建立，已收藏的詞就多加一個例句。
    同一個詞在同一句已經收藏過時丟 DuplicateVocabError。還沒查 AI 解釋時中文意思先留空。
    reading 留空時由原形推算（表記不是原形時，例如點「食べ」收藏「食べる」）。"""
    created_at = _now(now)
    reading = reading or lemma_reading(lemma)
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO vocab (lemma, reading, pos, created_at) VALUES (?, ?, ?, ?)",
                (lemma, reading, pos, created_at),
            )
            vocab_id = conn.execute("SELECT id FROM vocab WHERE lemma = ?", (lemma,)).fetchone()["id"]
            conn.execute(
                "INSERT INTO vocab_example (vocab_id, surface, context_sentence, meaning_zh, usage_note,"
                " example_ja, example_zh, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (vocab_id, surface, context_sentence, meaning_zh, usage_note, example_ja, example_zh, created_at),
            )
    except sqlite3.IntegrityError:
        raise DuplicateVocabError(get_vocab_by_lemma(conn, lemma))
    return get_vocab(conn, vocab_id)


def fill_missing_meaning(conn: sqlite3.Connection, lemma: str, sentence: str, result: AIExplanation) -> bool:
    """先收藏、後查 AI 解釋時，把 AI 解釋補進該句的例句；已經有中文意思的不覆蓋。"""
    with conn:
        cur = conn.execute(
            "UPDATE vocab_example SET meaning_zh = ?, usage_note = ?, example_ja = ?, example_zh = ?"
            " WHERE context_sentence = ? AND meaning_zh = '' AND vocab_id = (SELECT id FROM vocab WHERE lemma = ?)",
            (result.meaning_zh, result.usage_note, result.example_ja, result.example_zh, sentence, lemma),
        )
    return cur.rowcount > 0


def _escape_like(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_vocab(conn: sqlite3.Connection, keyword: str | None = None, pos: str | None = None) -> list[VocabEntry]:
    """依關鍵字（比對原形、讀音、任一例句的中文意思）與詞性篩選，新收藏的在前面。"""
    sql = "SELECT * FROM vocab WHERE 1 = 1"
    params: list[str] = []
    if keyword and keyword.strip():
        pattern = f"%{_escape_like(keyword.strip())}%"
        sql += (
            " AND (lemma LIKE ? ESCAPE '\\' OR reading LIKE ? ESCAPE '\\' OR id IN"
            " (SELECT vocab_id FROM vocab_example WHERE meaning_zh LIKE ? ESCAPE '\\'))"
        )
        params += [pattern] * 3
    if pos:
        sql += " AND pos = ?"
        params.append(pos)
    sql += " ORDER BY created_at DESC, id DESC"
    return _entries(conn, conn.execute(sql, params).fetchall())


def delete_vocab(conn: sqlite3.Connection, vocab_id: int) -> bool:
    """刪除整個詞（連同所有例句）；找不到時回傳 False。"""
    with conn:
        cur = conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))
    return cur.rowcount > 0


def delete_example(conn: sqlite3.Connection, example_id: int) -> int | None:
    """刪除一個例句；刪掉最後一個例句時詞也一起刪除。
    回傳被刪的詞 id（詞還留著時為 0）；找不到例句時回傳 None。"""
    with conn:
        row = conn.execute("SELECT vocab_id FROM vocab_example WHERE id = ?", (example_id,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM vocab_example WHERE id = ?", (example_id,))
        if conn.execute("SELECT 1 FROM vocab_example WHERE vocab_id = ?", (row["vocab_id"],)).fetchone():
            return 0
        conn.execute("DELETE FROM vocab WHERE id = ?", (row["vocab_id"],))
        return row["vocab_id"]


# --- AI 解釋快取與查詢紀錄 ---

def sentence_hash(surface: str, sentence: str) -> str:
    """快取鍵的一部分：同一句裡選取範圍不同（食べ／食べました）解釋也不同，所以表記一起算進去。"""
    return hashlib.sha256(f"{surface}\n{sentence}".encode()).hexdigest()


def get_cached_explanation(conn: sqlite3.Connection, lemma: str, surface: str, sentence: str) -> AIExplanation | None:
    row = conn.execute(
        "SELECT response_json FROM lookup_cache WHERE lemma = ? AND sentence_hash = ?",
        (lemma, sentence_hash(surface, sentence)),
    ).fetchone()
    return parse_explanation(row["response_json"]) if row else None


def save_cached_explanation(
    conn: sqlite3.Connection, lemma: str, surface: str, sentence: str, result: AIExplanation,
    now: datetime | None = None,
) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO lookup_cache (lemma, sentence_hash, response_json, created_at) VALUES (?, ?, ?, ?)",
            (lemma, sentence_hash(surface, sentence), json.dumps(asdict(result), ensure_ascii=False), _now(now)),
        )


def log_lookup(conn: sqlite3.Connection, lemma: str, pos: str, now: datetime | None = None) -> None:
    with conn:
        conn.execute("INSERT INTO lookup_log (lemma, pos, looked_up_at) VALUES (?, ?, ?)", (lemma, pos, _now(now)))


def explain_with_cache(
    conn: sqlite3.Connection, get_provider: Callable[[], Provider],
    lemma: str, surface: str, pos: str, sentence: str,
) -> AIExplanation:
    """先查快取，沒有才呼叫 LLM（失敗時丟 LLMError、不寫快取）；成功的查詢都記一筆，命中快取也算。
    已收藏但還沒有中文意思的詞，順手補上。

    get_provider 等到真的要呼叫 LLM 才執行，所以沒設金鑰時快取裡有的仍查得到。
    """
    result = get_cached_explanation(conn, lemma, surface, sentence)
    if result is None:
        result = explain(get_provider(), lemma, surface, pos, sentence)
        save_cached_explanation(conn, lemma, surface, sentence, result)
    log_lookup(conn, lemma, pos)
    fill_missing_meaning(conn, lemma, sentence, result)
    return result
