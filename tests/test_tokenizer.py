import pytest

from core.tokenizer import split_sentences, tokenize


def find(tokens, surface):
    return next(t for t in tokens if t.surface == surface)


def test_acceptance_example():
    t = find(tokenize("昨日、寿司を食べました。"), "食べました")
    assert t.lemma == "食べる"
    assert t.reading == "たべました"
    assert t.pos == "動詞"
    assert t.conj_form == "連用形"


@pytest.mark.parametrize("text, surface, lemma, reading", [
    ("先生に褒められた。", "褒められた", "褒める", "ほめられた"),          # 被動
    ("子供に野菜を食べさせる。", "食べさせる", "食べる", "たべさせる"),    # 使役
    ("あの映画は面白かった。", "面白かった", "面白い", "おもしろかった"),  # 形容詞過去
    ("昨日は雨でした。", "でした", "です", "でした"),                      # 助動詞連續
])
def test_conjugation_restored(text, surface, lemma, reading):
    t = find(tokenize(text), surface)
    assert (t.lemma, t.reading) == (lemma, reading)


def test_noun_not_merged_with_copula():
    surfaces = [t.surface for t in tokenize("学生です。")]
    assert surfaces == ["学生", "です", "。"]


def test_particles_and_punctuation():
    tokens = tokenize("本を読む。")
    assert find(tokens, "を").pos == "助詞"
    period = find(tokens, "。")
    assert period.pos == "補助記号"
    assert period.reading == "。"
    assert period.conj_form == ""


def test_reading_is_hiragana():
    assert find(tokenize("東京に行く"), "東京").reading == "とうきょう"


def test_empty_string():
    assert tokenize("") == []


def test_mixed_alphanumeric_and_whitespace():
    tokens = tokenize("iPhone 15を買った！")
    space = find(tokens, " ")
    assert space.pos == "空白"
    assert space.reading == " "
    assert find(tokens, "買った").lemma == "買う"


@pytest.mark.parametrize("text", [
    "昨日、寿司を食べました。\n\n  今日は雨です！",
    "iPhone 15を買った！ABC",
    "はい。はい。",
])
def test_surfaces_reconstruct_original(text):
    assert "".join(t.surface for t in tokenize(text)) == text


def test_sentence_attached_to_tokens():
    tokens = tokenize("雨が降った。傘を買う。")
    assert find(tokens, "降った").sentence == "雨が降った。"
    assert find(tokens, "傘").sentence == "傘を買う。"


def test_merge_does_not_cross_sentences():
    # 句尾的「た」不能吸收下一句開頭的詞
    surfaces = [t.surface for t in tokenize("食べた。です")]
    assert surfaces == ["食べた", "。", "です"]


def test_split_sentences_keeps_delimiters():
    assert split_sentences("あ。い！\nう") == ["あ。", "い！", "\n", "う"]
