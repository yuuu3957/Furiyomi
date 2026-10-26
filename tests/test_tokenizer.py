import pytest

from core.tokenizer import split_sentences, tokenize


def find(tokens, surface):
    return next(t for t in tokens if t.surface == surface)


def surfaces(text):
    return [t.surface for t in tokenize(text)]


def test_acceptance_example():
    # 不合併：食べました 拆成 食べ／まし／た，接起來就是使用者選取整段的結果
    tokens = tokenize("昨日、寿司を食べました。")
    tabe = find(tokens, "食べ")
    assert (tabe.lemma, tabe.reading, tabe.pos, tabe.conj_form) == ("食べる", "たべ", "動詞", "連用形")
    assert find(tokens, "まし").lemma == "ます"
    i = tokens.index(tabe)
    span = tokens[i:i + 3]
    assert "".join(t.surface for t in span) == "食べました"
    assert "".join(t.reading for t in span) == "たべました"


@pytest.mark.parametrize("text, surface, lemma, reading", [
    ("先生に褒められた。", "褒め", "褒める", "ほめ"),        # 被動
    ("子供に野菜を食べさせる。", "食べ", "食べる", "たべ"),  # 使役
    ("あの映画は面白かった。", "面白かっ", "面白い", "おもしろかっ"),  # 形容詞過去
])
def test_conjugation_restored(text, surface, lemma, reading):
    t = find(tokenize(text), surface)
    assert (t.lemma, t.reading) == (lemma, reading)


@pytest.mark.parametrize("text, grammar", [
    ("明日は雨が降るらしい。", "らしい"),
    ("雨が降るだろう。", "だろう"),
    ("先生に褒められた。", "られ"),
])
def test_grammar_kept_as_separate_token(text, grammar):
    # 文法助動詞要能單獨點選，不能被前面的動詞吃掉
    assert find(tokenize(text), grammar).pos == "助動詞"


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
    assert find(tokens, "買っ").lemma == "買う"


@pytest.mark.parametrize("text", [
    "昨日、寿司を食べました。\n\n  今日は雨です！",
    "iPhone 15を買った！ABC",
    "はい。はい。",
])
def test_surfaces_reconstruct_original(text):
    assert "".join(surfaces(text)) == text


def test_sentence_attached_to_tokens():
    tokens = tokenize("雨が降った。傘を買う。")
    assert find(tokens, "降っ").sentence == "雨が降った。"
    assert find(tokens, "傘").sentence == "傘を買う。"


def test_split_sentences_keeps_delimiters():
    assert split_sentences("あ。い！\nう") == ["あ。", "い！", "\n", "う"]
