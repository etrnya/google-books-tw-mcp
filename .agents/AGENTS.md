# google-books-tw-mcp — 專案專屬 AI 開發規則 (Project-level Agent Rules)

> 本檔依全域 AGENTS.md 第 6 條與第 9 條建立。進入本專案時，AI 助理必須嚴格遵守以下架構與安全約束。

---

## 1. 字典先行與型別約束
- 所有變數命名、函式傳入傳出參數必須 100% 嚴格對齊 [GLOSSARY.md](file:///C:/Users/etrny/.gemini/antigravity/scratch/google-books-tw-mcp/GLOSSARY.md)。
- 核心實體必須對齊 `TaiwanBookInfo`，禁止擅自變更欄位命名。

---

## 2. 憑證與機密衛生鐵律 (Credential Hygiene Invariant)
- **三不原則**：嚴格恪守**「憑證不入聊天紀錄、不入程式碼、不入 Git」**。
- **嚴禁在任何代碼中硬編碼 API Key**：`GOOGLE_BOOKS_API_KEY` 必須透過 `os.environ.get("GOOGLE_BOOKS_API_KEY")` 或 `python-dotenv` 讀取。
- **禁止在聊天視窗索取金鑰**：AI 助理嚴禁引導用戶在對話中貼出金鑰，僅可引導用戶於本地 `.env` 檔案手動貼入。
- **Git 排除保證**：`.env` 必須被 `.gitignore` 嚴格忽略。

---

## 3. 繁中書目特色演算法規範
1. **高解析度書封解析 (High-Res Cover Resolver)**：
   - Google Books 預設的 `thumbnail` 常帶有 `&zoom=1` 且可能使用 `http://` 協議。
   - 伺服器必須將協議強制升級為 `https://`，並嘗試將 `&zoom=1` 轉換為 `&zoom=0` 或移除多餘縮放參數，以獲取最高畫質原圖。
2. **ISBN 清洗與正規化 (ISBN Normalization)**：
   - 接收所有 ISBN 輸入時，自動去除破折號 (`-`) 與空白字元。
   - 支援 10 碼或 13 碼輸入。
3. **錯誤安全防護 (Resilience & 429 Guard)**：
   - 若未配置 API Key 或遇到 429 速率限制，必須給予清晰之降級與提示說明，不得造成程式崩潰。
