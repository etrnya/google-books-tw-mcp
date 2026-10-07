# 📚 Google Books TW MCP Server (臺灣繁體書目專用 MCP 伺服器)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-green.svg)](https://modelcontextprotocol.io/)
[![Taiwan Books](https://img.shields.io/badge/Target-Taiwan%20Traditional%20Chinese-red.svg)](https://github.com/etrnya/google-books-tw-mcp)

專為 **臺灣繁體中文出版品市場**、**ISBN 破折號自動清洗** 與 **高解析度書封解析** 打造的開源 Model Context Protocol (MCP) 伺服器。

相容於 **Claude Desktop**、**Google Antigravity**、**Cursor**、**Windsurf** 等所有支援 MCP 的現代 AI 開發與對話客戶端。

---

## ✨ 核心特色與亮點 (Key Features)

一般開源的 Google Books MCP 大多針對英文出版品設計，在查詢臺灣書籍時常面臨縮圖解析度過低、被 Google 429 頻率限制阻擋、或回傳過於冗長的原始 JSON。

`google-books-tw-mcp` 針對繁體中文場景提供專屬優化：

1. 🖼️ **高解析度書封自動還原 (High-Res Cover Resolver)**：
   - 自動將 Google Books 的小縮圖（`zoom=1`，約 128px）升級為原尺寸高畫質書封（`zoom=0`）。
   - 自動修正 `http` 為安全 `https`，徹底解決 Notion 或現代瀏覽器混合內容 (Mixed Content) 破圖問題。
   - 自動剔除虛擬書角捲邊效果 (`&edge=curl`)，還原真實平整封面。
2. 🏷️ **ISBN 智慧自動清洗 (ISBN Normalization)**：
   - 自動去除條碼字串中的破折號 (`-`) 與空格（例如將 `978-986-175-526-1` 自動清洗為 `9789861755261`）。
   - 支援 10 碼與 13 碼雙向精確比對。
3. 🇹🇼 **繁中出版品精煉結構 (Clean Schema)**：
   - 自動提煉臺灣讀者最關心的欄位：正式書名、副標題、作者列表、正式出版社、出版日期、ISBN-13/10、頁數、高畫質書封與簡介。
   - 過濾掉上萬字元的無用底層英文雜訊，大幅節省 AI 的 Context Window。
4. ⚡ **原生支援 API Key，徹底免疫 429 阻擋**：
   - 支援環境變數或本地 `.env` 傳入 Google Books API Key，享有 Google 官方每天 **1,000 次免費查詢額度**，不再因公共 IP 限制而中斷。
5. 🛡️ **最高標準憑證安全衛生 (Zero-Leak Hygiene)**：
   - 嚴格遵守「憑證不入聊天紀錄、不入程式碼、不入 Git」，金鑰完全由本地環境安全託管。

---

## 🛠️ 提供的 MCP 工具 (Available Tools)

| 工具名稱 | 參數 (Parameters) | 功能說明 |
| :--- | :--- | :--- |
| **`search_books`** | `query`: 關鍵字<br>`max_results`: 最大筆數 (預設 5) | 以繁體中文書名、作者或關鍵字模糊搜尋，回傳精簡中繼資料陣列。 |
| **`get_book_by_isbn`** | `isbn`: 10 碼或 13 碼 ISBN | 自動清理破折號後精準定位特定出版版本，取得權威出版資訊。 |
| **`get_book_cover`** | `isbn_or_query`: ISBN 條碼或書名 | 專門提取最高解析度、安全 `https` 之書封圖網址，適合 Notion 或書架展示。 |

---

## 🚀 快速安裝與配置 (Installation & Setup)

### 1. 複製專案庫並安裝依賴
```bash
git clone https://github.com/etrnya/google-books-tw-mcp.git
cd google-books-tw-mcp

# 安裝依賴 (建議使用 Python 3.10 以上)
pip install -r requirements.txt
```

### 2. 配置 Google Books API Key (強烈建議)
1. 前往 [Google Cloud Console](https://console.cloud.google.com/) 啟用 **Books API**。
2. 在「憑證」建立一組免費的 **API 金鑰 (API Key)**（每天 1,000 次免費額度）。
3. 複製模板並建立本地 `.env` 檔案：
   ```bash
   cp .env.example .env
   ```
4. 在 `.env` 中填入你的金鑰：
   ```env
   GOOGLE_BOOKS_API_KEY=AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

---

## 💻 客戶端配置指南 (Client Configuration)

### 🅰️ 在 Google Antigravity / Claude Code 中配置
開啟你的 MCP 設定檔（例如 `C:\Users\<username>\.gemini\config\mcp_config.json` 或 `mcp_config.json`）：

```json
{
  "mcpServers": {
    "google-books-tw": {
      "command": "python",
      "args": [
        "C:\\Users\\<username>\\.gemini\\antigravity\\scratch\\google-books-tw-mcp\\server.py"
      ],
      "env": {
        "GOOGLE_BOOKS_API_KEY": "AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
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
      ],
      "env": {
        "GOOGLE_BOOKS_API_KEY": "AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

---

## 🧪 執行單元測試 (Unit Testing)

本專案自帶完整的測試套件，涵蓋臺灣 ISBN 破折號清洗與高畫質圖片升級解析演算法：

```bash
python test_server.py
```

測試通過輸出：
```text
...
----------------------------------------------------------------------
Ran 3 tests in 0.000s

OK
```

---

## 📂 專案檔案結構 (Project Structure)

```text
google-books-tw-mcp/
├── .agents/
│   └── AGENTS.md        # AI 專屬防坑規則與安全約束
├── .env.example         # 安全金鑰模板 (已加入 .gitignore)
├── .gitignore           # 嚴格排除憑證與快取
├── GLOSSARY.md          # 字典先行核心術語定義
├── LICENSE              # MIT 開源授權條款
├── pyproject.toml       # Python 現代專案標準規範
├── README.md            # 本文件
├── requirements.txt     # 輕量依賴清單
├── server.py            # 核心 FastMCP 伺服器
└── test_server.py       # 單元測試腳本
```

---

## 📄 授權條款 (License)

本專案採用 [MIT License](LICENSE) 授權釋出，歡迎社群自由使用、改作與貢獻！
