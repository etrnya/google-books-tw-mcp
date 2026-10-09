# 📖 Google Books TW MCP 專案術語字典 (Glossary) v1.3.0

> 本文件依據全域開發通則「字典先行 (Dictionary First)」原則建立，嚴格定義 `google-books-tw-mcp`（臺灣書目元資料解析伺服器 Taiwan Book Metadata Resolver）之專業術語、資料模型與變數命名規範。所有程式碼與文檔必須 100% 對齊本字典。

---

## 1. 核心業務與模型術語 (Core Domain Terminology)

| 繁體中文術語 | 英文對照 (Term) | 代碼變數 / 識別碼 (Identifier) | 定義與語義解釋 |
| :--- | :--- | :--- | :--- |
| **書目元資料解析器** | Taiwan Book Metadata Resolver | `metadata_resolver` | 本專案核心定位：自外部資料源提煉、清洗、驗證並生成事實層 (Fact Layer) 之結構化服務。 |
| **版本識別身分** | Edition Identity | `edition_identity` / `identity` | 由 `isbn_13`、`isbn_10` 與 `google_books_id` 組成之唯一身分識別集合。 |
| **作品創作層** | Book Work Layer | `work` | 書籍作品本體（書名 `title`、副標題 `subtitle`、作者列表 `authors`、譯者列表 `translators`、語言 `language`）。 |
| **出版版本層** | Book Edition Layer | `edition` | 具體出版交易實體屬性（出版社 `publisher`、出版日期 `published_date`、頁數 `page_count`、裝訂形式 `print_type`、裝訂 `binding`、定價 `price`、主題分類 `category`）。 |
| **書封解析結果** | Cover Resolution | `cover` | 包含 `url`、`resolution_hint` ("high" / "medium")、`source` 之封面結構物件。 |
| **資料溯源與可信度** | Source & Confidence | `source` | 包含資料來源提供者 `provider`（"google_books" / "tenlong" / "sanmin" / "taiwan_catalog_cdn"）、信心度分數 `confidence` (0.0~1.0) 與 `confidence_reasons` 判定依據陣列。 |
| **多來源級聯備援** | Cascading Fallback Engine | `cascading_fallback` | 當主要供應商受限 (429) 或未收錄時，自動按優先順序級聯查詢本土專門書庫 (Tenlong / Sanmin / CDN) 之自癒機制。 |
| **天瓏書目解析器** | Tenlong Catalog Resolver | `tenlong_resolver` | 專門自天瓏網路書店提取精確電腦/商管/翻譯書目、作者譯者拆分與原始高解析度封面之解析模組。 |
| **三民書目解析器** | Sanmin Catalog Resolver | `sanmin_resolver` | 專門自三民網路書店檢索出版品、提取 Schema.org JSON-LD Book 結構化數據與本土 CDN 之解析模組。 |
| **ISBN 數學校驗** | ISBN Mathematical Validation | `isbn_validation` | 依據模數 11（ISBN-10）與模數 10（ISBN-13）演算法計算校驗碼，判定號碼真實性與完整性。 |
| **一站式書目解析工具** | Resolve Book Tool | `resolve_book` | 一鍵輸入 ISBN 或書名，自動完成清洗、校驗、檢索、升級書封與信心評分之核心 MCP 工具。 |

---

## 2. 結構化資料模型 (Data Schema)

### 2.1 書目事實解析實體 (`ResolvedBookFact`)
```python
class ResolvedBookFact:
    success: bool
    identity: {
        "isbn_13": str | None,
        "isbn_10": str | None,
        "google_books_id": str | None
    }
    work: {
        "title": str,
        "subtitle": str | None,
        "authors": list[str],
        "translators": list[str],      # 繁體中文譯者名單
        "language": str
    }
    edition: {
        "publisher": str | None,
        "published_date": str | None,
        "page_count": int | None,
        "print_type": str,             # "BOOK", "MAGAZINE", "EBOOK"
        "binding": str | None,         # 如 "平裝", "精裝", "電子書"
        "price": int | None,           # 新台幣定價 (TWD)
        "category": str | None         # 圖書主題分類
    }
    cover: {
        "url": str | None,
        "resolution_hint": "high" | "medium" | "none",
        "source": str                  # "google_books", "tenlong", "sanmin", "taiwan_catalog_cdn"
    }
    description: str | None
    source: {
        "provider": str,               # "google_books" | "tenlong" | "sanmin" | "taiwan_catalog_cdn"
        "confidence": float,           # 0.0 ~ 1.0
        "confidence_reasons": list[str], # 如 ["exact_isbn_checksum_passed", "taiwan_publisher_recognized:方智", "schema_org_validated"]
        "retrieved_at": str            # ISO 8601 時間戳
    }
```

### 2.2 標準錯誤協定 (`McpErrorResponse`)
```python
class McpErrorResponse:
    success: bool = False
    error: "INVALID_ISBN" | "NOT_FOUND" | "RATE_LIMITED" | "UPSTREAM_TIMEOUT" | "UPSTREAM_5XX" | "INVALID_RESPONSE"
    message: str
    retryable: bool
```

