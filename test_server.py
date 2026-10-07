#!/usr/bin/env python3
"""
單元測試：驗證 Google Books TW MCP (Taiwan Book Metadata Resolver v1.1.0)
測試項目包括：
1. ISBN 正規化、10碼模數11驗證、13碼模數10驗證、10轉13雙向轉換
2. 高畫質書封解析演算法 (https, zoom=0, 捲邊移除)
3. 結構化事實層 (Fact Layer) 與身分識別碼 (Identity Keys) 提取
4. 信心度評分演算法 (Confidence Engine) 與臺灣出版社識別
5. 標準化錯誤回傳結構 (make_error)
"""

import unittest
from server import (
    normalize_isbn,
    validate_isbn10,
    validate_isbn13,
    isbn10_to_isbn13,
    parse_and_validate_isbn,
    resolve_highres_cover,
    build_book_fact,
    make_error,
)


class TestGoogleBooksTWResolver(unittest.TestCase):

    # ========================================================================
    # 1. ISBN 清洗與正規化測試
    # ========================================================================
    def test_normalize_isbn(self):
        # 破折號清除
        self.assertEqual(normalize_isbn("978-986-5751-48-7"), "9789865751487")
        # 空格清除
        self.assertEqual(normalize_isbn(" 978 986 5751 48 7 "), "9789865751487")
        # 10 碼 X 大小寫轉換
        self.assertEqual(normalize_isbn("0-8044-2957-x"), "080442957X")
        # 空字串防禦
        self.assertEqual(normalize_isbn(""), "")
        self.assertEqual(normalize_isbn(None), "")

    # ========================================================================
    # 2. ISBN 校驗碼驗證測試 (Mod 11 & Mod 10)
    # ========================================================================
    def test_validate_isbn13(self):
        # 合法臺灣 13 碼書號
        self.assertTrue(validate_isbn13("978-986-5751-48-7"))  # 超效率數位筆記術
        self.assertTrue(validate_isbn13("9789861755267"))      # 原子習慣

        # 錯誤的校驗碼 (末碼應為 7，給 1 應判定無效)
        self.assertFalse(validate_isbn13("978-986-175-526-1"))

        # 13 碼含 X (ISBN-13 僅能為 0-9 數字，X 僅合法於 10 碼)
        self.assertFalse(validate_isbn13("978-986-175-526-X"))

        # 非 978/979 開頭
        self.assertFalse(validate_isbn13("9771234567890"))

        # 長度不足或過長
        self.assertFalse(validate_isbn13("978986175"))
        self.assertFalse(validate_isbn13("978986175526700"))

    def test_validate_isbn10(self):
        # 合法含 X 的 10 碼書號 (Mod 11)
        self.assertTrue(validate_isbn10("0-8044-2957-X"))
        self.assertTrue(validate_isbn10("080442957x"))

        # 合法純數字 10 碼書號
        self.assertTrue(validate_isbn10("9861755268"))

        # 錯誤校驗碼
        self.assertFalse(validate_isbn10("0-8044-2957-1"))
        self.assertFalse(validate_isbn10("9861755269"))

        # 長度錯誤
        self.assertFalse(validate_isbn10("12345"))

    def test_isbn10_to_isbn13(self):
        # 10 碼有效轉 13 碼
        self.assertEqual(isbn10_to_isbn13("080442957X"), "9780804429573")
        self.assertEqual(isbn10_to_isbn13("9861755268"), "9789861755267")

        # 無效 10 碼返回 None
        self.assertIsNone(isbn10_to_isbn13("1234567890"))

    def test_parse_and_validate_isbn(self):
        # 13 碼檢驗封裝
        res13 = parse_and_validate_isbn("978-986-5751-48-7")
        self.assertEqual(res13["type"], "ISBN-13")
        self.assertTrue(res13["is_valid"])
        self.assertEqual(res13["canonical_13"], "9789865751487")

        # 10 碼檢驗封裝 (自動換算為 canonical_13)
        res10 = parse_and_validate_isbn("0-8044-2957-X")
        self.assertEqual(res10["type"], "ISBN-10")
        self.assertTrue(res10["is_valid"])
        self.assertEqual(res10["canonical_13"], "9780804429573")

        # 長度不符
        res_inv = parse_and_validate_isbn("12345")
        self.assertEqual(res_inv["type"], "INVALID_LENGTH")
        self.assertFalse(res_inv["is_valid"])
        self.assertIsNone(res_inv["canonical_13"])

    # ========================================================================
    # 3. 高畫質書封解析演算法測試
    # ========================================================================
    def test_resolve_highres_cover(self):
        raw_url = "http://books.google.com/books/content?id=mock_id&printsec=frontcover&img=1&zoom=1&edge=curl&source=gbs_api"
        cover_fact = resolve_highres_cover(raw_url)

        # 斷言 1: 強制升級 https
        self.assertTrue(cover_fact["url"].startswith("https://"))
        # 斷言 2: zoom 升級為 0
        self.assertIn("&zoom=0", cover_fact["url"])
        self.assertNotIn("&zoom=1", cover_fact["url"])
        # 斷言 3: 捲邊 edge=curl 移除
        self.assertNotIn("&edge=curl", cover_fact["url"])
        # 斷言 4: 解析提示與來源
        self.assertEqual(cover_fact["resolution_hint"], "high")
        self.assertEqual(cover_fact["source"], "google_books")

        # 空書封防禦
        empty_fact = resolve_highres_cover(None)
        self.assertIsNone(empty_fact["url"])
        self.assertEqual(empty_fact["resolution_hint"], "none")

    # ========================================================================
    # 4. 事實層 (Fact Layer) 與信心度評分測試
    # ========================================================================
    def test_build_book_fact(self):
        mock_item = {
            "id": "item_mock_123",
            "volumeInfo": {
                "title": "原子習慣",
                "subtitle": "細微改變帶來巨大成就的實證法則",
                "authors": ["James Clear"],
                "publisher": "方智",
                "publishedDate": "2019-06-01",
                "pageCount": 320,
                "language": "zh-TW",
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9789861755267"},
                    {"type": "ISBN_10", "identifier": "9861755268"}
                ],
                "imageLinks": {
                    "thumbnail": "http://books.google.com/books/content?id=test&zoom=1&edge=curl"
                },
                "description": "A" * 350  # 測試超過 300 字精簡
            }
        }

        # 測試精確 ISBN 查詢情境
        fact = build_book_fact(mock_item, query_used="9789861755267", is_isbn_query=True)

        # 1. 身分識別層驗證
        self.assertEqual(fact["identity"]["isbn_13"], "9789861755267")
        self.assertEqual(fact["identity"]["isbn_10"], "9861755268")
        self.assertEqual(fact["identity"]["google_books_id"], "item_mock_123")

        # 2. 書目基本資訊驗證
        self.assertEqual(fact["work"]["title"], "原子習慣")
        self.assertEqual(fact["work"]["authors"], ["James Clear"])
        self.assertEqual(fact["work"]["language"], "zh-TW")

        # 3. 出版版本資訊驗證
        self.assertEqual(fact["edition"]["publisher"], "方智")
        self.assertEqual(fact["edition"]["published_date"], "2019-06-01")

        # 4. 書封事實驗證
        self.assertTrue(fact["cover"]["url"].startswith("https://"))
        self.assertIn("&zoom=0", fact["cover"]["url"])

        # 5. 內容精簡驗證
        self.assertTrue(len(fact["description"]) <= 305)
        self.assertTrue(fact["description"].endswith("..."))

        # 6. 信心度評分引擎驗證 (精確 ISBN 命中 + 臺灣出版社 + 繁中相容 + 書封解析)
        self.assertGreaterEqual(fact["source"]["confidence"], 0.90)
        reasons = fact["source"]["confidence_reasons"]
        self.assertIn("exact_isbn_checksum_passed", reasons)
        self.assertTrue(any("taiwan_publisher_recognized" in r for r in reasons))

    # ========================================================================
    # 5. 標準化錯誤回傳測試
    # ========================================================================
    def test_make_error(self):
        err = make_error("RATE_LIMITED", "頻率超標", retryable=True)
        self.assertFalse(err["success"])
        self.assertEqual(err["error"], "RATE_LIMITED")
        self.assertTrue(err["retryable"])

        err_fatal = make_error("INVALID_ISBN", "書號格式不符", retryable=False)
        self.assertFalse(err_fatal["retryable"])


if __name__ == "__main__":
    unittest.main()
