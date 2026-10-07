# 📖 Google Books TW MCP 專案術語字典 (Glossary) v1.0.0

> 本文件依據全域開發通則「字典先行 (Dictionary First)」原則建立，嚴格定義 `google-books-tw-mcp`（臺灣繁體出版品 Google Books MCP 伺服器）之專業術語、資料模型與變數命名規範。所有程式碼與文檔必須 100% 對齊本字典。

---

## 1. 核心業務與模型術語 (Core Domain Terminology)

| 繁體中文術語 | 英文對照 (Term) | 代碼變數 / 識別碼 (Identifier) | 定義與語義解釋 |
| :--- | :--- | :--- | :--- |
| **國際標準書號 (13碼)** | International Standard Book Number 13 | `isbn_13` | 13 碼標準書籍識別碼（978 開頭），由數字組成，無破折號。 |
| **國際標準書號 (10碼)** | International Standard Book Number 10 | `isbn_10` | 10 碼舊版書籍識別碼，最後一碼可能為 'X'。 |
| **正規化 ISBN** | Normalized ISBN | `normalized_isbn` | 清除所有破折號 (`-`)、空格後的大寫標準純數字字串。 |
| **高解析度書封網址** | High-Resolution Cover URL | `highres_cover_url` | 經本伺服器特殊演算法還原之官方原尺寸高清書籍封面圖連結（強制 `https` 且 `zoom=0`）。 |
| **書籍出版元資料** | Book Volume Metadata | `book_metadata` / `VolumeMetadata` | 包含標準書名、副標題、作者列表、出版社、出版日期、ISBN、頁數與書封的結構化物件。 |
| **模型上下文協定** | Model Context Protocol | `mcp` | 由 Anthropic 開源之 AI 工具調用標準通信協定。 |
| **繁中書目搜尋工具** | Search Books Tool | `search_books` | 針對臺灣出版品關鍵字（書名、作者、出版社）檢索之 MCP 工具。 |
| **ISBN 精確檢索工具** | Get Book By ISBN Tool | `get_book_by_isbn` | 輸入條碼數字精確定位單一書籍出版版本之 MCP 工具。 |
| **封面提取專用工具** | Get Book Cover Tool | `get_book_cover` | 單獨提取高畫質書封 URL 之輕量 MCP 工具。 |

---

## 2. 結構化資料模型 (Data Schema)

### 2.1 書籍元資料實體 (`TaiwanBookInfo`)
```python
class TaiwanBookInfo:
    title: str                  # 正書名 (如: "原子習慣")
    subtitle: str | None        # 副標題 (如: "細微改變帶來巨大成就的實證法則")
    authors: list[str]          # 作者列表 (如: ["James Clear"])
    publisher: str | None       # 出版社 (如: "方智")
    published_date: str | None  # 出版日期 (如: "2019-06-01")
    isbn_13: str | None         # 標準 13 碼 ISBN
    isbn_10: str | None         # 標準 10 碼 ISBN
    page_count: int | None      # 總頁數
    language: str               # 語言代碼 (如: "zh-TW")
    cover_url: str | None       # 高畫質書封圖網址
    description: str | None     # 書籍內容簡介 (精簡版)
    google_books_id: str        # Google Books 系統專屬 Volume ID
```
