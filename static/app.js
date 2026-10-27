// 前端只負責顯示：斷詞、讀音、ruby 切分都由後端 /api/analyze 決定

const MAX_LENGTH = 2000;

const input = document.getElementById("text-input");
const charCount = document.getElementById("char-count");
const analyzeBtn = document.getElementById("analyze-btn");
const message = document.getElementById("message");
const article = document.getElementById("article");

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
function renderToken(token) {
  const span = document.createElement("span");
  span.className = "token";
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

function renderArticle(tokens) {
  article.replaceChildren(...tokens.map(renderToken));
  article.hidden = false;
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
