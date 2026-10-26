"""用 SudachiPy 斷詞，轉成 Token 列表。

SudachiPy 會把活用拆開（食べました → 食べ／まし／た），對學習者來說不直覺，
所以把「動詞／形容詞／助動詞」與緊接在後的助動詞合併成一個 Token，
原形、詞性、活用形沿用第一個詞（食べました → 原形 食べる、動詞、連用形）。
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from sudachipy import Dictionary, SplitMode

from core.furigana import katakana_to_hiragana

# 可以吸收後面助動詞的詞性
_MERGE_HEAD_POS = {"動詞", "形容詞", "助動詞"}
# 讀音直接用表記的詞性（Sudachi 給空白的讀音是「キゴウ」）
_NO_READING_POS = {"空白", "補助記号"}
# 句子在句末標點或換行之後切開，保留分隔字元，讓各段串回去等於原文
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?\n])")


@dataclass
class Token:
    surface: str     # 表記：食べました
    lemma: str       # 原形：食べる
    reading: str     # 讀音（平假名）：たべました
    pos: str         # 詞性：動詞
    conj_form: str   # 活用形：連用形
    sentence: str    # 所在句子（給 AI 用）


@lru_cache(maxsize=1)
def _get_tokenizer():
    return Dictionary().tokenizer(mode=SplitMode.C)


def _conj_form(raw: str) -> str:
    # 「連用形-一般」→「連用形」；沒有活用時 Sudachi 給「*」
    return "" if raw == "*" else raw.split("-")[0]


def _reading(morpheme, pos: str) -> str:
    if pos in _NO_READING_POS:
        return morpheme.surface()
    return katakana_to_hiragana(morpheme.reading_form())


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if s]


def tokenize(text: str) -> list[Token]:
    """斷詞。所有 Token 的 surface 依序串起來會等於原文（含空白、換行）。"""
    tokens: list[Token] = []
    for chunk in split_sentences(text):
        sentence = chunk.strip()
        sentence_tokens: list[Token] = []
        for m in _get_tokenizer().tokenize(chunk):
            pos_info = m.part_of_speech()
            pos = pos_info[0]
            prev = sentence_tokens[-1] if sentence_tokens else None
            if pos == "助動詞" and prev is not None and prev.pos in _MERGE_HEAD_POS:
                prev.surface += m.surface()
                prev.reading += _reading(m, pos)
                continue
            sentence_tokens.append(Token(
                surface=m.surface(),
                lemma=m.dictionary_form(),
                reading=_reading(m, pos),
                pos=pos,
                conj_form=_conj_form(pos_info[5]),
                sentence=sentence,
            ))
        tokens.extend(sentence_tokens)
    return tokens
