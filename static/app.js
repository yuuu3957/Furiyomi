// 前端只負責顯示：斷詞、讀音、ruby 切分、詞性配色都由後端 /api/analyze 決定

const MAX_LENGTH = 2000;
// 與後端 tokenizer 的切句規則一致：Token 以這些字元結尾就是句子的最後一個 Token
const SENTENCE_END = /[。！？!?\n]$/;

const input = document.getElementById("text-input");
const charCount = document.getElementById("char-count");
const analyzeBtn = document.getElementById("analyze-btn");
const message = document.getElementById("message");
const reader = document.getElementById("reader");
const article = document.getElementById("article");
const rubyToggle = document.getElementById("ruby-toggle");
const detailEmpty = document.getElementById("detail-empty");
const detailBody = document.getElementById("detail-body");

let tokens = [];
let tokenEls = [];
let sentenceIds = [];
let anchor = null;  // Shift 選取的起點（Token 索引）

function showMessage(text) {
  message.textContent = text;
  message.hidden = !text;
}

function updateCharCount() {
  const len = input.value.length;
  charCount.textContent = `${len} / ${MAX_LENGTH}`;
  charCount.classList.toggle("over", len > MAX_LENGTH);
}

// 用 textContent 建立節點，文章內容不會被當成 HTML 解析
function renderToken(token, index) {
  const span = document.createElement("span");
  span.className = `token pos-${token.pos_class}`;
  // 空白、換行不能點
  if (token.surface.trim()) {
    span.classList.add("clickable");
    span.dataset.index = index;
  }
  for (const seg of token.ruby) {
    if (seg.rt === null) {
      span.append(seg.text);
      continue;
    }
    const ruby = document.createElement("ruby");
    const rt = document.createElement("rt");
    rt.textContent = seg.rt;
    ruby.append(seg.text, rt);
    span.append(ruby);
  }
  return span;
}

function computeSentenceIds(tokens) {
  let id = 0;
  return tokens.map((t) => {
    const current = id;
    if (SENTENCE_END.test(t.surface)) id++;
    return current;
  });
}

function renderArticle(newTokens) {
  tokens = newTokens;
  sentenceIds = computeSentenceIds(tokens);
  tokenEls = tokens.map(renderToken);
  article.replaceChildren(...tokenEls);
  anchor = null;
  showDetail(null);
  reader.hidden = false;
}

// 整段的表記、讀音直接相接；原形、詞性沿用第一個 Token。活用形只對單一 Token 有意義
function describeSelection(start, end) {
  const picked = tokens.slice(start, end + 1);
  const first = picked[0];
  return {
    surface: picked.map((t) => t.surface).join(""),
    reading: picked.map((t) => t.reading).join(""),
    lemma: first.lemma,
    pos: first.pos,
    conj_form: picked.length === 1 ? first.conj_form : null,
  };
}

function setField(id, value) {
  document.getElementById(id).textContent = value || "—";
}

function showDetail(info) {
  detailEmpty.hidden = !!info;
  detailBody.hidden = !info;
  if (!info) return;
  setField("d-surface", info.surface);
  setField("d-reading", info.reading);
  setField("d-lemma", info.lemma);
  setField("d-pos", info.pos);
  const single = info.conj_form !== null;
  document.getElementById("d-conj-label").hidden = !single;
  document.getElementById("d-conj").hidden = !single;
  if (single) setField("d-conj", info.conj_form);
}

function select(start, end) {
  tokenEls.forEach((el, i) => el.classList.toggle("selected", i >= start && i <= end));
  showDetail(describeSelection(start, end));
}

function onArticleClick(e) {
  const el = e.target.closest(".token.clickable");
  if (!el) return;
  const index = Number(el.dataset.index);
  // Shift 選取不可跨句；跨句時改成重新選一個
  if (e.shiftKey && anchor !== null && sentenceIds[anchor] === sentenceIds[index]) {
    select(Math.min(anchor, index), Math.max(anchor, index));
    return;
  }
  anchor = index;
  select(index, index);
}

async function analyze() {
  const text = input.value;
  // 與後端相同的檢查先在前端擋下，不必送出請求
  if (!text.trim()) return showMessage("請輸入文章。");
  if (text.length > MAX_LENGTH) return showMessage(`文章超過 ${MAX_LENGTH} 字（目前 ${text.length} 字）。`);

  showMessage("");
  analyzeBtn.disabled = true;
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) return showMessage(data.error?.message ?? "發生錯誤，請稍後再試。");
    renderArticle(data.tokens);
  } catch {
    showMessage("無法連線到伺服器。");
  } finally {
    analyzeBtn.disabled = false;
  }
}

input.addEventListener("input", updateCharCount);
analyzeBtn.addEventListener("click", analyze);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) analyze();
});
article.addEventListener("click", onArticleClick);
// Shift+點擊預設會反白文字，擋掉以免干擾選取
article.addEventListener("mousedown", (e) => {
  if (e.shiftKey) e.preventDefault();
});
rubyToggle.addEventListener("change", () => {
  article.classList.toggle("hide-ruby", !rubyToggle.checked);
});
