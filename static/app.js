// 前端只負責顯示：斷詞、讀音、ruby 切分、詞性配色都由後端 /api/analyze 決定

const MAX_LENGTH = 20000; // 整篇上限；後端切成每頁 2,000 字內
// 助詞、標點可以點，但不提供 AI 解釋（pos_class 來自後端）
const NO_AI_POS = new Set(["particle", "symbol"]);
// 與後端 tokenizer 的切句規則一致：Token 以這些字元結尾就是句子的最後一個 Token
const SENTENCE_END = /[。！？!?\n]$/;

const input = document.getElementById("text-input");
const charCount = document.getElementById("char-count");
const analyzeBtn = document.getElementById("analyze-btn");
const pdfBtn = document.getElementById("pdf-btn");
const pdfInput = document.getElementById("pdf-input");
const message = document.getElementById("message");
const reader = document.getElementById("reader");
const article = document.getElementById("article");
const rubyToggle = document.getElementById("ruby-toggle");
const colorToggle = document.getElementById("color-toggle");
const detailEmpty = document.getElementById("detail-empty");
const detailBody = document.getElementById("detail-body");
const aiArea = document.getElementById("ai-area");
const aiBtn = document.getElementById("ai-btn");
const aiMessage = document.getElementById("ai-message");
const aiResult = document.getElementById("ai-result");
const pager = document.getElementById("pager");
const prevBtn = document.getElementById("prev-btn");
const nextBtn = document.getElementById("next-btn");
const pageInfo = document.getElementById("page-info");

let pages = [];      // 切好的頁面文字
let pageTokens = []; // 已分析過的頁面，切回來不必重送
let pageIndex = 0;
let tokens = [];
let tokenEls = [];
let sentenceIds = [];
let anchor = null;  // Shift 選取的起點（Token 索引）
let current = null; // 目前詳情面板顯示的選取內容
// AI 解釋的快取（P3 做了 SQLite 後改由後端快取）；只存成功的結果
const aiCache = new Map();

function showMessage(text) {
  message.textContent = text;
  message.hidden = !text;
}

function updateCharCount() {
  const len = input.value.length;
  charCount.textContent = `${len.toLocaleString()} / ${MAX_LENGTH.toLocaleString()}`;
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
}

function showArticleMessage(text, className = "message") {
  const p = document.createElement("p");
  p.className = className;
  p.textContent = text;
  renderArticle([]);
  article.replaceChildren(p);
}

function updatePager() {
  pager.hidden = pages.length <= 1;
  pageInfo.textContent = `${pageIndex + 1} / ${pages.length}`;
  prevBtn.disabled = pageIndex === 0;
  nextBtn.disabled = pageIndex === pages.length - 1;
}

async function loadPage(index) {
  pageIndex = index;
  updatePager();
  reader.hidden = false;
  if (pageTokens[index]) return renderArticle(pageTokens[index]);

  prevBtn.disabled = nextBtn.disabled = true;
  showArticleMessage("分析中…", "loading");
  let error = "";
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: pages[index] }),
    });
    const data = await res.json();
    if (res.ok) pageTokens[index] = data.tokens;
    else error = data.error?.message ?? "發生錯誤，請稍後再試。";
  } catch {
    error = "無法連線到伺服器。";
  }
  // 等待期間使用者可能已經換頁
  if (index !== pageIndex) return;
  updatePager();
  if (error) showArticleMessage(error);
  else renderArticle(pageTokens[index]);
}

// 貼上文字與 PDF 都從這裡開始：拿到切好的頁面後顯示第一頁
function openDocument(newPages) {
  pages = newPages;
  pageTokens = [];
  loadPage(0);
}

function goToPage(index) {
  loadPage(index);
  reader.scrollIntoView({ behavior: "smooth" });
}

// 整段的表記、讀音直接相接；原形、詞性沿用第一個 Token
function describeSelection(start, end) {
  const picked = tokens.slice(start, end + 1);
  const first = picked[0];
  return {
    surface: picked.map((t) => t.surface).join(""),
    reading: picked.map((t) => t.reading).join(""),
    lemma: first.lemma,
    pos: first.pos,
    posClass: first.pos_class,
    sentence: first.sentence,
  };
}

function aiKey(info) {
  return JSON.stringify([info.lemma, info.surface, info.sentence]);
}

function setField(id, value) {
  document.getElementById(id).textContent = value || "—";
}

function showDetail(info) {
  current = info;
  detailEmpty.hidden = !!info;
  detailBody.hidden = !info;
  aiArea.hidden = !info || NO_AI_POS.has(info.posClass);
  if (!info) return;
  setField("d-surface", info.surface);
  setField("d-reading", info.reading);
  setField("d-lemma", info.lemma);
  setField("d-pos", info.pos);
  showAiMessage("");
  showAiResult(aiCache.get(aiKey(info)) ?? null);
}

function showAiMessage(text) {
  aiMessage.textContent = text;
  aiMessage.hidden = !text;
}

// 有結果時隱藏按鈕，沒有結果時顯示按鈕
function showAiResult(result) {
  aiResult.hidden = !result;
  aiBtn.hidden = !!result;
  aiBtn.disabled = false;
  aiBtn.textContent = "AI 解釋";
  if (!result) return;
  setField("ai-meaning", result.meaning_zh);
  setField("ai-usage", result.usage_note);
  setField("ai-example-ja", result.example_ja);
  setField("ai-example-zh", result.example_zh);
}

async function explain() {
  const info = current;
  const key = aiKey(info);
  aiBtn.disabled = true;
  aiBtn.textContent = "AI 解釋中…";
  showAiMessage("");
  let result = null;
  let error = "";
  try {
    const res = await fetch("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lemma: info.lemma, surface: info.surface, pos: info.pos, sentence: info.sentence }),
    });
    const data = await res.json();
    if (res.ok) {
      result = data;
      aiCache.set(key, result);
    } else {
      error = data.error?.message ?? "AI 解釋失敗，請稍後再試。";
    }
  } catch {
    error = "無法連線到伺服器。";
  }
  // 等待期間使用者可能已經點了別的字，結果已存入快取，這裡不更新畫面
  if (!current || aiKey(current) !== key) return;
  showAiResult(result);
  showAiMessage(error);
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
  if (text.length > MAX_LENGTH) {
    return showMessage(`文章超過 ${MAX_LENGTH.toLocaleString()} 字（目前 ${text.length.toLocaleString()} 字）。`);
  }

  showMessage("");
  analyzeBtn.disabled = true;
  try {
    const res = await fetch("/api/paginate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) return showMessage(data.error?.message ?? "發生錯誤，請稍後再試。");
    openDocument(data.pages);
  } catch {
    showMessage("無法連線到伺服器。");
  } finally {
    analyzeBtn.disabled = false;
  }
}

async function uploadPdf() {
  const file = pdfInput.files[0];
  pdfInput.value = ""; // 清掉，同一個檔案才能再選一次
  if (!file) return;

  showMessage("");
  pdfBtn.classList.add("busy");
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch("/api/pdf/extract", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) return showMessage(data.error?.message ?? "PDF 讀取失敗，請稍後再試。");
    openDocument(data.pages);
  } catch {
    showMessage("無法連線到伺服器。");
  } finally {
    pdfBtn.classList.remove("busy");
  }
}

input.addEventListener("input", updateCharCount);
pdfInput.addEventListener("change", uploadPdf);
analyzeBtn.addEventListener("click", analyze);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) analyze();
});
article.addEventListener("click", onArticleClick);
aiBtn.addEventListener("click", explain);
prevBtn.addEventListener("click", () => goToPage(pageIndex - 1));
nextBtn.addEventListener("click", () => goToPage(pageIndex + 1));
// Shift+點擊預設會反白文字，擋掉以免干擾選取
article.addEventListener("mousedown", (e) => {
  if (e.shiftKey) e.preventDefault();
});
rubyToggle.addEventListener("change", () => {
  article.classList.toggle("hide-ruby", !rubyToggle.checked);
});
colorToggle.addEventListener("change", () => {
  reader.classList.toggle("no-pos-color", !colorToggle.checked);
});
