# Furiyomi（ふりよみ）

> 開發中：本 README 描述的是預計完成的功能，實際進度請看 Git log。

貼上日文文章（或上傳 PDF），自動在漢字上標註假名；點選任一單字，即可查看詞彙資訊與 AI 中文解釋。

名稱取自「振り仮名」＋「読み」。

## 適合誰

以閱讀為主、程度約 N4～N2、習慣看繁體中文解釋的日文學習者。

## 功能

### 閱讀
- **假名標註**：貼上文章（上限 2,000 字）後，漢字上方會標出平假名；純假名、標點、英數不標註。
- **顯示／隱藏假名**：可以一鍵切換，用來自我測驗。
- **詞性上色**：用顏色區分名詞、動詞、形容詞等。
- **點字看詳情**：點一下單字，右側面板會顯示表記、讀音、原形、詞性、活用形。
  - 例：「食べました」→ 原形「食べる」、讀音「たべました」
- **AI 解釋**：針對該單字在這句話中的用法，產生繁體中文意思、用法說明和例句。
- **PDF 上傳**：支援文字型的橫書 PDF，可以分段閱讀。

### 加值功能（視進度完成）
- 單字庫：收藏、搜尋、依詞性篩選、刪除
- 統計頁：單字數、查詢次數、詞性分布
- CSV 匯出：可以匯入 Anki
- MCP 工具：`analyze_japanese(text)`

## 設計理念

斷詞、讀音、原形、詞性這些有標準答案的事，交給 [SudachiPy](https://github.com/WorksApplications/SudachiPy) 處理，結果穩定、不花錢、不會出錯。只有「這個字在這句話裡是什麼意思」這種需要語意理解的部分，才交給 LLM。

## 技術

| 層 | 使用 |
|---|---|
| 後端 | Python、FastAPI、Pydantic |
| 斷詞 | SudachiPy |
| 前端 | HTML + 原生 JavaScript + CSS（`<ruby>` 標籤） |
| 資料庫 | SQLite |
| 測試 | pytest、FastAPI TestClient |

## 專案結構

```
furiyomi/
├── main.py           # FastAPI 入口
├── api/routes.py     # API 路由與輸入驗證
├── core/             # 所有邏輯（斷詞、假名、PDF、LLM、單字庫、統計）
├── static/           # 前端頁面
├── tests/            # 測試
└── mcp_server.py     # MCP 伺服器
```

## 安裝與執行

需要 Python 3.10 以上。

```bash
# 建立虛擬環境
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 安裝套件
pip install -r requirements.txt

# 設定 API 金鑰：在專案根目錄建立 .env（不會被 commit）
# 金鑰名稱待 LLM 服務確定後補上

# 啟動
uvicorn main:app --reload
```

啟動後用瀏覽器開啟 <http://127.0.0.1:8000>。

## 測試

```bash
pytest
```

測試不會連上網路；LLM 的呼叫都用 mock 取代。

## API

| 方法與路徑 | 功能 |
|---|---|
| `POST /api/analyze` | 斷詞，回傳 token 列表 |
| `POST /api/explain` | AI 解釋單字 |
| `POST /api/pdf/extract` | 上傳 PDF，回傳分段文字 |
| `GET /api/vocab` | 查詢單字庫 |
| `POST /api/vocab` | 收藏單字 |
| `DELETE /api/vocab/{id}` | 刪除單字 |
| `GET /api/vocab/export` | 匯出 CSV |
| `GET /api/stats` | 統計資料 |

錯誤一律回傳 `{"error": {"code": ..., "message": ...}}`。

## 不在範圍內

使用者帳號、網址匯入、複習測驗、語音朗讀、手機版優化。
