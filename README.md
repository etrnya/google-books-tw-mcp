# 📚 Taiwan Book Metadata Resolver (臺灣繁體書目元資料解析 MCP 伺服器)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-green.svg)](https://modelcontextprotocol.io/)
[![Version](https://img.shields.io/badge/Release-v1.1.0-blue.svg)](https://github.com/etrnya/google-books-tw-mcp)
[![Taiwan Books](https://img.shields.io/badge/Target-Taiwan%20Traditional%20Chinese-red.svg)](https://github.com/etrnya/google-books-tw-mcp)

專為 **臺灣繁體中文出版品市場**、**ISBN 校驗碼合法性驗證**、**出版版本辨識 (Edition Identity)**、**高解析度書封解析** 與 **AI 事實層 (Fact Layer)** 打造的開源 Model Context Protocol (MCP) 伺服器。

相容於 **Google Antigravity**、**Claude Desktop**、**Cursor**、**Windsurf** 等所有支援 MCP 的現代 AI 開發與對話客戶端，亦可作為個人書籍資產管理（如 Notion 書櫃、Booklist 系統）的底層中繼資料服務。

---

## ✨ 核心特色與架構升級 (Key Features in v1.1.0)

一般的 Google Books 工具僅扮演「API 原始 JSON 包裝器」，直接回傳上萬字元的無用英文雜訊與低解析度縮圖。
`google-books-tw-mcp` 將自身定位為 **Book Metadata Resolver**，在外部資料進入 AI 前先完成標準化、校驗與結構化：

```text
外部 API (Google Books)
        ↓
Normalizer (ISBN 清洗 / 破折號清除 / 格式大寫)
        ↓
Validator (ISBN-10 模數 11 校驗 / ISBN-13 模數 10 校驗 / 10轉13 雙向換算)
        ↓
Cover Resolver (強制 https / zoom=0 原尺寸 / 捲邊移除)
        ↓
Edition & Confidence Engine (臺灣主要出版社加權 / 繁中語言辨識 / 信心度打分)
        ↓
Resolved Book Fact (身分識別碼 identity / 作品 work / 版本 edition / 來源 source)
        ↓
MCP Tools API → AI Agent / Booklist 查重決策系統
```

### 1. 🛡️ 嚴謹的 ISBN 校驗與雙向轉換 (ISBN Validation & Conversion)
- 自動清洗破折號與空格（例如 `978-986-175-526-7` → `9789861755267`）。
- 實作 **ISBN-10 (模數 11)** 與 **ISBN-13 (模數 10)** 數學校驗碼驗證，主動拒絕無效偽條碼。
- 支援有效之 **ISBN-10 自動精算轉換為標準 ISBN-13**。

### 2. 🖼️ 高解析度書封自動還原 (High-Res Cover Resolver)
- 自動將 Google Books 的小縮圖（`zoom=1`，約 128px）升級為原尺寸高畫質書封（`zoom=0`）。
- 強制升級為安全 `https://` 協議，徹底解決 Notion 或現代前端的 Mixed Content 破圖問題。
- 自動剔除虛擬書角捲邊效果 (`&edge=curl`)，還原真實平整封面。

### 3. 🇹🇼 出版版本辨識與事實層 (Edition Identity & Fact Layer)
- 輸出標準化事實結構：
  - `identity`: 身分識別鍵（`isbn_13`, `isbn_10`, `google_books_id`）。
  - `work`: 抽象作品層（`title`, `subtitle`, `authors`, `language`）。
  - `edition`: 具體出版版本（`publisher`, `published_date`, `page_count`）。
  - `cover`: 解析後的書封資料與解析度提示。
  - `source`: 資料來源、信心度評分 (`confidence` 0.0~0.99) 與評分依據清單。

### 4. ⚡ 臺灣主要出版社加權與信心度評分 (Confidence Engine)
- 內建臺灣代表性出版社字典（天下文化、商周、遠流、方智、圓神、城邦、時報、聯經、早安財經等）。
- 精確 ISBN 命中 + 臺灣出版商 + 繁中相容性綜合打分，供上層系統（如 Booklist）自動決定採納或需要人工覆核。

### 5. 🛑 標準化錯誤處理與重試協定 (Standardized Error Protocol)
- 針對 `RATE_LIMITED` (429)、`UPSTREAM_5XX`、`UPSTREAM_TIMEOUT` 提供明確的結構化錯誤碼，並標註 `retryable: true/false`，讓 AI Agent 具備自我修復與重試能力。

### 6. 🔒 嚴格遵守憑證衛生鐵律 (Credential Hygiene)
- 恪守「憑證不入聊天紀錄、不入程式碼、不入 Git」。伺服器優先透過本地 `.env` 自動注入金鑰，設定檔不再暴露明文金鑰。

---

## 🛠️ 提供的 MCP 工具 (Available Tools)

| 工具名稱 | 參數 (Parameters) | 功能說明 |
| :--- | :--- | :--- |
| **`resolve_book`**<br>*(推薦核心工具)* | `query_or_isbn`: 條碼或書名 | **一站式核心工具**。自動完成 ISBN 清洗驗證、版本定位、封面升級、信心度計算，回傳標準 Fact Layer。 |
| **`search_books`** | `query`: 關鍵字<br>`search_type`: auto / title / author / isbn<br>`language`: 預設 "zh-TW"<br>`max_results`: 最大回傳筆數 (1~10) | 針對繁體中文語境多維度搜尋書籍候選清單，適合模糊比對與選書推薦。 |
| **`get_book_by_isbn`** | `isbn`: 10 碼或 13 碼 ISBN | 透過 ISBN 條碼精確查詢出版品（內部對齊 `resolve_book`）。 |
| **`get_book_cover`** | `isbn_or_query`: ISBN 條碼或書名 | 專門提取高解析度、安全 `https` 之書封圖網址與原尺寸元資料。 |

---

## 📋 核心事實層資料範例 (Fact Layer Output Example)

呼叫 `resolve_book("978-986-175-526-7")` 回傳之結構化 JSON：

```json
{
  "success": true,
  "found": true,
  "book": {
    "identity": {
      "isbn_13": "9789861755267",
      "isbn_10": "9861755268",
      "google_books_id": "4u_wDwAAQBAJ"
    },
    "work": {
      "title": "原子習慣",
      "subtitle": "細微改變帶來巨大成就的實證法則",
      "authors": ["James Clear"],
      "language": "zh-TW"
    },
    "edition": {
      "publisher": "方智",
      "published_date": "2019-06-01",
      "page_count": 320,
      "print_type": "BOOK"
    },
    "cover": {
      "url": "https://books.google.com/books/content?id=4u_wDwAAQBAJ&printsec=frontcover&img=1&zoom=0&source=gbs_api",
      "resolution_hint": "high",
      "source": "google_books"
    },
    "description": "善用「複利」效應，讓小小的原子習慣利滾利，滾出生命的大不同！...",
    "source": {
      "provider": "google_books",
      "confidence": 0.98,
      "confidence_reasons": [
        "exact_isbn_checksum_passed",
        "taiwan_publisher_recognized:方智",
        "traditional_chinese_compatible",
        "cover_image_resolved"
      ],
      "retrieved_at": "2026-10-07T05:20:00Z"
    }
  }
}
```

---

## 🚀 快速安裝與配置 (Installation & Setup)

### 1. 複製專案庫並安裝依賴
```bash
git clone https://github.com/etrnya/google-books-tw-mcp.git
cd google-books-tw-mcp

# 安裝依賴 (建議使用 Python 3.10 以上)
pip install -r requirements.txt
```

### 2. 本地配置 Google Books API Key (.env 方式，最安全)
1. 前往 [Google Cloud Console](https://console.cloud.google.com/) 啟用 **Books API**。
2. 在「憑證」建立一組免費的 **API 金鑰 (API Key)**（每天享有 1,000 次免費額度）。
3. 複製模板並建立本地 `.env` 檔案（`.env` 已在 `.gitignore` 中，絕不洩漏）：
   ```bash
   cp .env.example .env
   ```
4. 使用你慣用的編輯器開啟 `.env` 填入金鑰：
   ```env
   GOOGLE_BOOKS_API_KEY=AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

---

## 💻 客戶端配置指南 (Client Configuration)

因為 `server.py` 原生內建 `load_dotenv()`，**強烈建議不要在 MCP 設定檔中填寫明文金鑰**，僅需直接指向 `server.py`：

### 🅰️ 在 Google Antigravity / Claude Code 中配置
開啟你的 MCP 設定檔（例如 `C:\Users\<username>\.gemini\config\mcp_config.json`）：

```json
{
  "mcpServers": {
    "google-books-tw": {
      "command": "python",
      "args": [
        "C:\\Users\\<username>\\.gemini\\antigravity\\scratch\\google-books-tw-mcp\\server.py"
      ]
    }
  }
}
```

### 🅱️ 在 Claude Desktop 中配置
開啟 Claude Desktop 設定檔（`%APPDATA%\Claude\claude_desktop_config.json` 或 `~/Library/Application Support/Claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "google-books-tw": {
      "command": "python",
      "args": [
        "/path/to/google-books-tw-mcp/server.py"
      ]
    }
  }
}
```

---

## 🧪 執行單元測試 (Unit Testing)

本專案提供嚴謹的單元測試，涵蓋 ISBN 模數 10/11 校驗、轉換、書封解析、事實層結構與信心度打分：

```bash
python test_server.py
```

測試通過輸出：
```text
........
----------------------------------------------------------------------
Ran 8 tests in 0.001s

OK
```

---

## 📂 專案檔案結構 (Project Structure)

```text
google-books-tw-mcp/
├── .agents/
│   └── AGENTS.md        # AI 專屬架構防坑規則與憑證衛生約束
├── .env.example         # 安全金鑰模板 (已加入 .gitignore)
├── .gitignore           # 嚴格排除憑證與快取
├── GLOSSARY.md          # 字典先行核心術語定義 (含 Fact Layer 定義)
├── LICENSE              # MIT 開源授權條款
├── pyproject.toml       # Python 現代專案標準規範
├── README.md            # 本文件
├── requirements.txt     # 輕量依賴清單 (FastMCP, httpx, python-dotenv)
├── server.py            # 核心 FastMCP 伺服器 (Resolver & Fact Engine)
└── test_server.py       # 8 項完整單元測試套件
```

---

## 📄 授權條款 (License)

本專案採用 [MIT License](LICENSE) 授權釋出，歡迎社群自由使用、改作與貢獻！
