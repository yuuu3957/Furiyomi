"""用 SudachiPy 斷詞，轉成 Token 列表。

保留 SudachiPy 的原始切分（食べました → 食べ／まし／た），不自動合併：
合併會把「らしい」「でしょう」等文法吃掉，改由使用者在前端自行選取範圍。
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from sudachipy import Dictionary, SplitMode

from core.furigana import katakana_to_hiragana

# 讀音直接用表記的詞性（Sudachi 給空白的讀音是「キゴウ」）
_NO_READING_POS = {"空白", "補助記号"}
# 句子在句末標點或換行之後切開，保留分隔字元，讓各段串回去等於原文
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?\n])")


@dataclass
class Token:
    surface: str     # 表記：食べ
    lemma: str       # 原形：食べる
    reading: str     # 讀音（平假名）：たべ
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
        for m in _get_tokenizer().tokenize(chunk):
            pos_info = m.part_of_speech()
            pos = pos_info[0]
            tokens.append(Token(
                surface=m.surface(),
                lemma=m.dictionary_form(),
                reading=_reading(m, pos),
                pos=pos,
                conj_form=_conj_form(pos_info[5]),
                sentence=sentence,
            ))
    return tokens
