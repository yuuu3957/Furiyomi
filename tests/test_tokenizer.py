import pytest

from core.tokenizer import lemma_reading, split_sentences, tokenize


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
    ("信じられない。", "信じ", "信じる", "しんじ"),          # Sudachi 原形給文語「信ずる」
    ("寒さを感じた。", "感じ", "感じる", "かんじ"),
    ("撮影は禁じられた。", "禁じ", "禁じる", "きんじ"),
])
def test_conjugation_restored(text, surface, lemma, reading):
    t = find(tokenize(text), surface)
    assert (t.lemma, t.reading) == (lemma, reading)


def test_literary_zuru_kept_when_written_so():
    assert find(tokenize("神を信ずる。"), "信ずる").lemma == "信ずる"


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


@pytest.mark.parametrize("text, reading", [
    ("15", "じゅうご"),
    ("2026", "にせんにじゅうろく"),
    ("1,000", "せん"),
    ("１５", "じゅうご"),        # 全形數字
    ("1本", "いっぽん"),
    ("6本", "ろっぽん"),
    ("10分", "じゅっぷん"),
    ("3日", "みっか"),
    ("20日", "はつか"),
    ("4時", "よじ"),
    ("4月", "しがつ"),
    ("1匹", "いっぴき"),
    ("100円", "ひゃくえん"),
    ("1つ", "ひとつ"),
])
def test_number_and_counter_reading(text, reading):
    # 數字和量詞合成一個 Token，讀音含音變
    tokens = tokenize(text)
    assert len(tokens) == 1
    assert (tokens[0].surface, tokens[0].reading, tokens[0].pos) == (text, reading, "名詞")


def test_number_in_sentence():
    tokens = tokenize("約3時間かかった。第1回は10人以上来た。")
    assert find(tokens, "3時間").reading == "さんじかん"
    assert find(tokens, "第").pos == "接頭辞"       # 接頭辭不合併
    assert find(tokens, "1回").reading == "いっかい"
    assert find(tokens, "10人").reading == "じゅうにん"
    assert find(tokens, "以上").reading == "いじょう"


def test_number_reading_known_error():
    # 已知限制：pyopenjtalk 字典把 10日 記成「とうか」（正確為とおか）
    assert find(tokenize("10日"), "10日").reading == "とうか"


@pytest.mark.parametrize("text", [
    "昨日、寿司を食べました。\n\n  今日は雨です！",
    "iPhone 15を買った！ABC",
    "はい。はい。",
    "2026年10月1日に3本買った。",
])
def test_surfaces_reconstruct_original(text):
    assert "".join(surfaces(text)) == text


def test_sentence_attached_to_tokens():
    tokens = tokenize("雨が降った。傘を買う。")
    assert find(tokens, "降っ").sentence == "雨が降った。"
    assert find(tokens, "傘").sentence == "傘を買う。"


def test_split_sentences_keeps_delimiters():
    assert split_sentences("あ。い！\nう") == ["あ。", "い！", "\n", "う"]


@pytest.mark.parametrize("lemma, reading", [
    ("食べる", "たべる"), ("乗り換える", "のりかえる"), ("可愛い", "かわいい"), ("する", "する"), ("", ""),
])
def test_lemma_reading(lemma, reading):
    assert lemma_reading(lemma) == reading
