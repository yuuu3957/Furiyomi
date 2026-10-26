"""假名相關的純函式：片假名→平假名（ruby 判斷、詞性配色之後加入）。"""

# 片假名 ァ(U+30A1)～ヶ(U+30F6) 與平假名相差固定位移；長音「ー」等不在範圍內，保持原樣
_KATA_START = 0x30A1
_KATA_END = 0x30F6
_KATA_TO_HIRA = 0x60


def katakana_to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(ch) - _KATA_TO_HIRA) if _KATA_START <= ord(ch) <= _KATA_END else ch
        for ch in text
    )
