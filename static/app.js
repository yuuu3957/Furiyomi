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
const collectArea = document.getElementById("collect-area");
const collectBtn = document.getElementById("collect-btn");
const collectMessage = document.getElementById("collect-message");
const tabs = document.querySelectorAll(".tabs [data-view]");
const vocabSearch = document.getElementById("vocab-search");
const vocabPos = document.getElementById("vocab-pos");
const vocabCount = document.getElementById("vocab-count");
const vocabMessage = document.getElementById("vocab-message");
const vocabBody = document.getElementById("vocab-body");
const vocabEmpty = document.getElementById("vocab-empty");
const statsMessage = document.getElementById("stats-message");
const posChart = document.getElementById("pos-chart");
const posEmpty = document.getElementById("pos-empty");
const dailyChart = document.getElementById("daily-chart");
const dailyTable = document.getElementById("daily-table");

let pages = [];      // 切好的頁面文字
let pageTokens = []; // 已分析過的頁面，切回來不必重送
let pageIndex = 0;
let tokens = [];
let tokenEls = [];
let sentenceIds = [];
let anchor = null;  // Shift 選取的起點（Token 索引）
let current = null; // 目前詳情面板顯示的選取內容
// 這次瀏覽看過的 AI 解釋，再點同一個字時直接顯示；跨次保存的快取在後端 SQLite。只存成功的結果
const aiCache = new Map();
// 已收藏的原形 → 收藏過的句子；這一句收藏過才顯示「已在單字庫」，換一句可以再加為新的例句
const collected = new Map();
const expandedExamples = new Set(); // 單字庫頁展開詳情的例句，重新讀取列表後維持展開
let vocabRequest = 0;        // 搜尋時只顯示最後一次請求的結果
let searchTimer = null;

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
    // 收藏用的原形讀音：第一個 Token 本身就是原形時直接用；否則留空，由後端推算
    lemmaReading: first.surface === first.lemma ? first.reading : "",
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
  aiArea.hidden = collectArea.hidden = !info || NO_AI_POS.has(info.posClass);
  if (!info) return;
  setField("d-surface", info.surface);
  setField("d-reading", info.reading);
  setField("d-lemma", info.lemma);
  setField("d-pos", info.pos);
  showAiMessage("");
  showAiResult(aiCache.get(aiKey(info)) ?? null);
  showCollectMessage("");
  updateCollectBtn();
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

// 閱讀頁與單字庫頁共用；成功的結果存進 aiCache，回傳 { result, error }
async function requestExplanation({ lemma, surface, pos, sentence }) {
  try {
    const res = await fetch("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lemma, surface, pos, sentence }),
    });
    const data = await res.json();
    if (!res.ok) return { result: null, error: data.error?.message ?? "AI 解釋失敗，請稍後再試。" };
    aiCache.set(aiKey({ lemma, surface, sentence }), data);
    return { result: data, error: "" };
  } catch {
    return { result: null, error: "無法連線到伺服器。" };
  }
}

async function explain() {
  const info = current;
  const key = aiKey(info);
  aiBtn.disabled = true;
  aiBtn.textContent = "AI 解釋中…";
  showAiMessage("");
  const { result, error } = await requestExplanation(info);
  // 等待期間使用者可能已經點了別的字，結果已存入快取，這裡不更新畫面
  if (!current || aiKey(current) !== key) return;
  showAiResult(result);
  showAiMessage(error);
}

function showCollectMessage(text) {
  collectMessage.textContent = text;
  collectMessage.hidden = !text;
}

function updateCollectBtn() {
  if (!current) return;
  const sentences = collected.get(current.lemma);
  const done = !!sentences?.has(current.sentence);
  collectBtn.disabled = done;
  collectBtn.textContent = done ? "已在單字庫" : "加入單字庫";
}

function rememberCollected(item) {
  collected.set(item.lemma, new Set(item.examples.map((ex) => ex.context_sentence)));
}

async function loadCollected() {
  try {
    const res = await fetch("/api/vocab");
    if (!res.ok) return;
    const data = await res.json();
    collected.clear();
    data.items.forEach(rememberCollected);
    updateCollectBtn();
  } catch {
    // 讀不到時按鈕維持「加入單字庫」，重複收藏會由後端回報
  }
}

// 同一個詞在不同句子收藏會成為新的例句。已經查過 AI 解釋的話，中文意思與用法一起存；
// 沒查過先存空白，之後按 AI 解釋時後端會補上
async function collect() {
  const info = current;
  const ai = aiCache.get(aiKey(info));
  collectBtn.disabled = true;
  showCollectMessage("");
  let error = "";
  try {
    const res = await fetch("/api/vocab", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lemma: info.lemma,
        reading: info.lemmaReading,
        pos: info.pos,
        surface: info.surface,
        meaning_zh: ai?.meaning_zh ?? "",
        usage_note: ai?.usage_note ?? "",
        example_ja: ai?.example_ja ?? "",
        example_zh: ai?.example_zh ?? "",
        context_sentence: info.sentence,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      rememberCollected(data);
    } else {
      error = data.error?.message ?? "收藏失敗，請稍後再試。";
      if (data.error?.code === "vocab_exists") await loadCollected();
    }
  } catch {
    error = "無法連線到伺服器。";
  }
  // 等待期間使用者可能已經點了別的字
  if (current !== info) return;
  showCollectMessage(error);
  updateCollectBtn();
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

// --- 單字庫頁 ---

function showVocabMessage(text) {
  vocabMessage.textContent = text;
  vocabMessage.hidden = !text;
}

function formatTime(iso) {
  return iso.replace("T", " ").slice(0, 16); // 2026-10-28T09:30:00 → 2026-10-28 09:30
}

function cell(text, className = "", lang = "") {
  const td = document.createElement("td");
  td.textContent = text || "—";
  if (className) td.className = className;
  if (lang) td.lang = lang;
  return td;
}

function deleteButton(className, text, title, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = className;
  btn.textContent = text;
  btn.title = title;
  btn.addEventListener("click", onClick);
  return btn;
}

// 原句中把收藏時選取的表記標出來
function renderSentence(ex) {
  const div = document.createElement("div");
  div.className = "sentence";
  div.lang = "ja";
  const at = ex.surface ? ex.context_sentence.indexOf(ex.surface) : -1;
  if (at < 0) {
    div.textContent = ex.context_sentence || "—";
    return div;
  }
  const mark = document.createElement("mark");
  mark.textContent = ex.surface;
  div.append(ex.context_sentence.slice(0, at), mark, ex.context_sentence.slice(at + ex.surface.length));
  return div;
}

function detailField(dl, label, value, className = "", lang = "") {
  if (!value) return;
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = value;
  if (className) dd.className = className;
  if (lang) dd.lang = lang;
  dl.append(dt, dd);
}

// 展開後的詳情：已查過 AI 解釋就顯示完整內容，還沒查就提供「AI 解釋」按鈕
function renderExampleDetail(item, ex) {
  const div = document.createElement("div");
  div.className = "example-detail";
  if (ex.meaning_zh) {
    const dl = document.createElement("dl");
    detailField(dl, "用法", ex.usage_note);
    detailField(dl, "例句", ex.example_ja, "", "ja");
    detailField(dl, "翻譯", ex.example_zh, "translation");
    if (!dl.children.length) dl.textContent = "沒有其他說明。";
    div.append(dl);
    return div;
  }
  const note = document.createElement("p");
  note.textContent = "還沒有 AI 解釋。";
  div.append(note);
  // 沒有原句（例如從 MCP 收藏）時無法解釋
  if (!ex.context_sentence) return div;

  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "AI 解釋";
  const message = document.createElement("p");
  message.className = "message";
  message.hidden = true;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "AI 解釋中…";
    const { error } = await requestExplanation({
      lemma: item.lemma, surface: ex.surface || item.lemma, pos: item.pos, sentence: ex.context_sentence,
    });
    if (!error) return loadVocab(); // 後端已把解釋補進這個例句
    btn.disabled = false;
    btn.textContent = "AI 解釋";
    message.textContent = error;
    message.hidden = false;
  });
  div.append(btn, message);
  return div;
}

// 一詞多義：每個例句各自有該句中的中文意思；只有一個例句時刪除整個詞即可，不另外顯示刪除鈕
function renderExamples(item) {
  const ul = document.createElement("ul");
  ul.className = "examples";
  for (const ex of item.examples) {
    const li = document.createElement("li");
    const meaning = document.createElement("span");
    meaning.className = "meaning";
    meaning.textContent = ex.meaning_zh || "（尚未查 AI 解釋）";
    meaning.classList.toggle("missing", !ex.meaning_zh);

    const detail = renderExampleDetail(item, ex);
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "detail-toggle";
    const setOpen = (open) => {
      detail.hidden = !open;
      toggle.textContent = open ? "收合 ▴" : "詳情 ▾";
      toggle.setAttribute("aria-expanded", open);
      if (open) expandedExamples.add(ex.id);
      else expandedExamples.delete(ex.id);
    };
    setOpen(expandedExamples.has(ex.id));
    toggle.addEventListener("click", () => setOpen(detail.hidden));

    li.append(meaning, toggle);
    if (item.examples.length > 1) {
      li.append(deleteButton("example-delete", "×", "刪除這個例句", () => deleteExample(ex)));
    }
    li.append(renderSentence(ex), detail);
    ul.append(li);
  }
  const td = document.createElement("td");
  td.append(ul);
  return td;
}

function renderVocabRow(item) {
  const action = document.createElement("td");
  action.append(deleteButton("delete-btn", "刪除", "刪除這個單字與所有例句", () => deleteVocab(item)));

  const tr = document.createElement("tr");
  tr.append(
    cell(item.lemma, "lemma", "ja"),
    cell(item.reading, "", "ja"),
    cell(item.pos, "", "ja"),
    renderExamples(item),
    cell(formatTime(item.created_at), "time"),
    action,
  );
  return tr;
}

async function loadVocab() {
  const seq = ++vocabRequest;
  const params = new URLSearchParams();
  if (vocabSearch.value.trim()) params.set("keyword", vocabSearch.value.trim());
  if (vocabPos.value) params.set("pos", vocabPos.value);
  let items = [];
  let error = "";
  try {
    const res = await fetch(`/api/vocab?${params}`);
    const data = await res.json();
    if (res.ok) items = data.items;
    else error = data.error?.message ?? "讀取單字庫失敗，請稍後再試。";
  } catch {
    error = "無法連線到伺服器。";
  }
  // 打字搜尋時可能有較新的請求，舊的結果不顯示
  if (seq !== vocabRequest) return;
  showVocabMessage(error);
  vocabBody.replaceChildren(...items.map(renderVocabRow));
  vocabCount.textContent = error ? "" : `${items.length} 個單字`;
  vocabEmpty.hidden = !!error || items.length > 0;
  vocabEmpty.textContent = params.size
    ? "沒有符合條件的單字。"
    : "單字庫還沒有單字。在閱讀頁點選單字後，按「加入單字庫」。";
}

// 刪除後重新讀取列表與收藏狀態
async function sendDelete(url, question) {
  if (!confirm(question)) return;
  try {
    const res = await fetch(url, { method: "DELETE" });
    // 404 代表已經不在了，一樣當作刪除成功
    if (!res.ok && res.status !== 404) {
      const data = await res.json();
      return showVocabMessage(data.error?.message ?? "刪除失敗，請稍後再試。");
    }
  } catch {
    return showVocabMessage("無法連線到伺服器。");
  }
  loadVocab();
  loadCollected();
}

function deleteVocab(item) {
  sendDelete(`/api/vocab/${item.id}`, `是否刪除「${item.lemma}」？`);
}

function deleteExample(ex) {
  sendDelete(`/api/vocab/examples/${ex.id}`, "是否刪除這個例句？");
}

function switchView(name) {
  for (const tab of tabs) {
    const active = tab.dataset.view === name;
    tab.setAttribute("aria-selected", active);
    document.getElementById(`view-${tab.dataset.view}`).hidden = !active;
  }
  if (name === "vocab") loadVocab();
  if (name === "stats") loadStats();
}

// --- 統計頁 ---

const WEEKDAYS = "日一二三四五六";

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}

// 2026-10-28 → { short: "10/28", long: "10/28（三）" }；用 UTC 解析，避免時區讓日期差一天
function formatDay(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  const short = `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
  return { short, long: `${short}（${WEEKDAYS[d.getUTCDay()]}）` };
}

// y 軸刻度：取 1、2、5 × 10ⁿ 的整齊間距，大約 4 格
function niceTicks(max) {
  if (max <= 0) return [0, 1, 2, 3, 4];
  const raw = max / 4;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw && s >= 1) ?? 1;
  const ticks = [];
  for (let v = 0; v < max + step; v += step) ticks.push(v);
  return ticks;
}

// 橫條圖：單一系列，數值標在條的末端
function renderPosChart(items) {
  posEmpty.hidden = items.length > 0;
  const max = Math.max(1, ...items.map((i) => i.count));
  posChart.replaceChildren(...items.map((item) => {
    const row = el("div", "hbar-row");
    const label = el("span", "hbar-label", item.pos);
    label.lang = "ja";
    const track = el("div", "hbar-track");
    const bar = el("div", "hbar-bar");
    bar.style.width = `${(item.count / max) * 100}%`;
    track.append(bar, el("span", "hbar-value", item.count));
    row.append(label, track);
    return row;
  }));
}

// 直條圖：每天一欄，整欄都是滑鼠／鍵盤的觸發範圍，提示框顯示日期與次數
function renderDailyChart(days) {
  const ticks = niceTicks(Math.max(...days.map((d) => d.count)));
  const top = ticks[ticks.length - 1];

  const grid = el("div", "col-grid");
  for (const t of ticks) {
    const line = el("div", "col-gridline");
    line.style.bottom = `${(t / top) * 100}%`;
    line.append(el("span", "col-tick", t));
    grid.append(line);
  }

  const tooltip = el("div", "chart-tooltip");
  tooltip.hidden = true;
  const plot = el("div", "col-plot");
  days.forEach((day, i) => {
    const { short, long } = formatDay(day.date);
    const slot = el("div", "col-slot");
    slot.tabIndex = 0;
    slot.setAttribute("aria-label", `${long}：${day.count} 次`);
    const bar = el("div", "col-bar");
    bar.style.height = `${(day.count / top) * 100}%`;
    slot.append(bar);
    const show = () => {
      tooltip.replaceChildren(el("div", "", long), el("strong", "", `${day.count} 次`));
      tooltip.hidden = false;
      tooltip.style.left = `${((i + 0.5) / days.length) * 100}%`;
      tooltip.classList.toggle("align-start", i < 2);
      tooltip.classList.toggle("align-end", i >= days.length - 2);
      slot.classList.add("active");
    };
    const hide = () => {
      tooltip.hidden = true;
      slot.classList.remove("active");
    };
    slot.addEventListener("mouseenter", show);
    slot.addEventListener("focus", show);
    slot.addEventListener("mouseleave", hide);
    slot.addEventListener("blur", hide);
    plot.append(slot);
  });

  // 日期標籤隔一天顯示一次，最後一天（今天）一定顯示
  const axis = el("div", "col-axis");
  days.forEach((day, i) => {
    const show = (days.length - 1 - i) % 2 === 0;
    axis.append(el("span", "", show ? (i === days.length - 1 ? "今天" : formatDay(day.date).short) : ""));
  });

  const area = el("div", "col-area");
  area.append(grid, plot, tooltip);
  dailyChart.replaceChildren(area, axis);

  dailyTable.replaceChildren(...days.map((day) => {
    const tr = document.createElement("tr");
    tr.append(el("td", "", formatDay(day.date).long), el("td", "", day.count));
    return tr;
  }));
}

async function loadStats() {
  let data = null;
  let error = "";
  try {
    const res = await fetch("/api/stats");
    data = await res.json();
    if (!res.ok) error = data.error?.message ?? "讀取統計失敗，請稍後再試。";
  } catch {
    error = "無法連線到伺服器。";
  }
  statsMessage.textContent = error;
  statsMessage.hidden = !error;
  if (error) return;
  setField("stat-vocab-total", data.vocab_total.toLocaleString());
  setField("stat-vocab-week", data.vocab_this_week.toLocaleString());
  setField("stat-lookups", data.lookups_total.toLocaleString());
  renderPosChart(data.pos_distribution);
  renderDailyChart(data.daily_lookups);
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
collectBtn.addEventListener("click", collect);
for (const tab of tabs) tab.addEventListener("click", () => switchView(tab.dataset.view));
vocabSearch.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadVocab, 250);
});
vocabPos.addEventListener("change", loadVocab);
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

loadCollected();
