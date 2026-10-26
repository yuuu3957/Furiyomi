"""用 SudachiPy 斷詞，轉成 Token 列表。

保留 SudachiPy 的原始切分（食べました → 食べ／まし／た），不自動合併：
合併會把「らしい」「でしょう」等文法吃掉，改由使用者在前端自行選取範圍。

例外是「數字＋量詞」：Sudachi 會把 15 讀成「いちご」、不處理 1本→いっぽん 這類音變，
所以把數字和後面的量詞合成一個 Token，讀音改用 pyopenjtalk。
"""

import os
import re
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pyopenjtalk
from sudachipy import Dictionary, SplitMode

from core.furigana import katakana_to_hiragana

# 讀音直接用表記的詞性（Sudachi 給空白的讀音是「キゴウ」）
_NO_READING_POS = {"空白", "補助記号"}
# 可以接在數字後面合併的量詞（Sudachi 詞性第三層）
_COUNTER_POS = {"助数詞", "助数詞可能"}
# 句子在句末標點或換行之後切開，保留分隔字元，讓各段串回去等於原文
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?\n])")
# OpenJTalk 的 C 函式庫在 Windows 開不了含中文的路徑（如「桌面」），字典要複製到純英數路徑；
# 可用環境變數 OPEN_JTALK_DICT_DIR 自行指定
_JTALK_DICT_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "furiyomi" / "open_jtalk_dic_utf_8-1.11"


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


def _is_number(morpheme) -> bool:
    return morpheme.part_of_speech()[1] == "数詞"


def _is_counter(morpheme) -> bool:
    pos_info = morpheme.part_of_speech()
    return pos_info[0] == "接尾辞" or pos_info[2] in _COUNTER_POS


@lru_cache(maxsize=1)
def _init_jtalk_dict():
    if "OPEN_JTALK_DICT_DIR" in os.environ or os.fsdecode(pyopenjtalk.OPEN_JTALK_DICT_DIR).isascii():
        return
    if not _JTALK_DICT_DIR.exists():
        if not os.path.exists(pyopenjtalk.OPEN_JTALK_DICT_DIR):
            pyopenjtalk._extract_dic()  # 第一次使用：下載字典到套件目錄
        # 先複製到暫存名稱再改名，避免中斷時留下不完整的字典
        tmp = _JTALK_DICT_DIR.with_name(_JTALK_DICT_DIR.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(os.fsdecode(pyopenjtalk.OPEN_JTALK_DICT_DIR), tmp)
        tmp.rename(_JTALK_DICT_DIR)
    # 要用 bytes，跟 pyopenjtalk 自己下載後的設定一致；傳 str 會讓 C 端當掉
    pyopenjtalk.OPEN_JTALK_DICT_DIR = str(_JTALK_DICT_DIR).encode("utf-8")


def number_reading(text: str) -> str:
    """數字（含量詞）的平假名讀音，處理 1本→いっぽん、10分→じゅっぷん 等音變。

    pyopenjtalk 的 pron 有音變但長音寫成「ー」並夾帶重音記號「’」，read 沒有音變；
    兩者長度相同時逐字合併：取 pron，遇到「ー」換回 read 的字。
    """
    _init_jtalk_dict()
    reading = ""
    for node in pyopenjtalk.run_frontend(text):
        read, pron = node["read"], node["pron"].replace("’", "")
        if len(read) == len(pron):
            pron = "".join(r if p == "ー" else p for r, p in zip(read, pron))
        reading += pron
    return katakana_to_hiragana(reading)


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if s]


def tokenize(text: str) -> list[Token]:
    """斷詞。所有 Token 的 surface 依序串起來會等於原文（含空白、換行）。"""
    tokens: list[Token] = []
    for chunk in split_sentences(text):
        sentence = chunk.strip()
        morphemes = list(_get_tokenizer().tokenize(chunk))
        i = 0
        while i < len(morphemes):
            m = morphemes[i]
            if _is_number(m):
                has_counter = i + 1 < len(morphemes) and _is_counter(morphemes[i + 1])
                surface = "".join(x.surface() for x in morphemes[i:i + 1 + has_counter])
                tokens.append(Token(
                    surface=surface,
                    lemma=surface,
                    reading=number_reading(surface),
                    pos="名詞",
                    conj_form="",
                    sentence=sentence,
                ))
                i += 1 + has_counter
                continue
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
            i += 1
    return tokens
