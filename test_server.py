#!/usr/bin/env python3
"""
單元測試：驗證 ISBN 正規化與高畫質書封解析演算法
"""

import unittest
from server import normalize_isbn, resolve_highres_cover_url, parse_volume_item


class TestGoogleBooksTW(unittest.TestCase):

    def test_normalize_isbn(self):
        # 測試常見臺灣帶破折號 13 碼 ISBN
        self.assertEqual(normalize_isbn("978-986-175-526-1"), "9789861755261")
        # 測試帶空格
        self.assertEqual(normalize_isbn(" 978 986 175 526 1 "), "9789861755261")
        # 測試 10 碼含校驗碼 X
        self.assertEqual(normalize_isbn("986-175-526-X"), "986175526X")
        self.assertEqual(normalize_isbn("986-175-526-x"), "986175526X")
        # 測試空值防禦
        self.assertEqual(normalize_isbn(""), "")

    def test_resolve_highres_cover_url(self):
        raw_url = "http://books.google.com/books/content?id=4u_wDwAAQBAJ&printsec=frontcover&img=1&zoom=1&edge=curl&source=gbs_api"
        resolved = resolve_highres_cover_url(raw_url)
        
        # 斷言 1: 強制升級為 https
        self.assertTrue(resolved.startswith("https://"))
        # 斷言 2: zoom 升級為 0 (原尺寸)
        self.assertIn("&zoom=0", resolved)
        self.assertNotIn("&zoom=1", resolved)
        # 斷言 3: 移除 edge=curl
        self.assertNotIn("&edge=curl", resolved)

    def test_parse_volume_item(self):
        mock_item = {
            "id": "mock_id_123",
            "volumeInfo": {
                "title": "原子習慣",
                "subtitle": "細微改變帶來巨大成就的實證法則",
                "authors": ["James Clear"],
                "publisher": "方智",
                "publishedDate": "2019-06-01",
                "pageCount": 320,
                "language": "zh-TW",
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9789861755261"},
                    {"type": "ISBN_10", "identifier": "9861755269"}
                ],
                "imageLinks": {
                    "thumbnail": "http://books.google.com/books/content?id=test&zoom=1&edge=curl"
                },
                "description": "這是一本非常暢銷的好書"
            }
        }
        parsed = parse_volume_item(mock_item)
        self.assertEqual(parsed["title"], "原子習慣")
        self.assertEqual(parsed["isbn_13"], "9789861755261")
        self.assertEqual(parsed["isbn_10"], "9861755269")
        self.assertEqual(parsed["publisher"], "方智")
        self.assertTrue(parsed["cover_url"].startswith("https://"))
        self.assertIn("&zoom=0", parsed["cover_url"])


if __name__ == "__main__":
    unittest.main()
