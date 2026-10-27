"""假名相關的純函式：片假名→平假名、ruby 切分、日文偵測（詞性配色之後加入）。"""

import re

# 片假名 ァ(U+30A1)～ヶ(U+30F6) 與平假名相差固定位移；長音「ー」等不在範圍內，保持原樣
_KATA_START = 0x30A1
_KATA_END = 0x30F6
_KATA_TO_HIRA = 0x60

# 要標讀音的字：漢字（含「々」「〆」）與數字；數字＋量詞的音變讀音無法拆開，跟漢字一起當一組
_RUBY_CHARS = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆0-9０-９]+")
_KANA = re.compile(r"[ぁ-ゖァ-ヺ]")


def katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(ch) - _KATA_TO_HIRA) if _KATA_START <= ord(ch) <= _KATA_END else ch
        for ch in text
    )


def contains_japanese(text: str) -> bool:
    # 以假名判斷：只看漢字會把中文誤認為日文
    return bool(_KANA.search(text))


def ruby_segments(surface: str, reading: str) -> list[tuple[str, str | None]]:
    """把 Token 切成 (文字, 讀音) 片段，送假名不加讀音：食べ／たべ → [("食", "た"), ("べ", None)]。

    漢字與數字各段換成擷取群組、其餘照字面，拿去比對讀音；比對不上（如 三ヶ月）時整個 Token 標一組。
    """
    if not _RUBY_CHARS.search(surface):
        return [(surface, None)]
    parts = re.split(f"({_RUBY_CHARS.pattern})", surface)
    pattern = "".join(
        "(.+?)" if i % 2 else re.escape(katakana_to_hiragana(p))
        for i, p in enumerate(parts)
    )
    match = re.fullmatch(pattern, reading)
    if not match:
        return [(surface, reading)]
    readings = iter(match.groups())
    return [
        (p, next(readings) if i % 2 else None)
        for i, p in enumerate(parts) if p
    ]
