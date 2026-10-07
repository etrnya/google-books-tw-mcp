#!/usr/bin/env python3
"""
Google Books TW MCP Server
專為臺灣繁體出版品、ISBN 自動清洗、高畫質書封解析打造的 MCP 伺服器
"""

import os
import re
from typing import Any, Optional
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 載入本地 .env 設定 (若存在)
load_dotenv()

# 初始化 FastMCP 伺服器
mcp = FastMCP("google-books-tw-mcp")

GOOGLE_BOOKS_API_BASE = "https://www.googleapis.com/books/v1/volumes"


def get_api_key() -> Optional[str]:
    """獲取 Google Books API 金鑰 (優先讀取環境變數)"""
    return os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip() or None


def normalize_isbn(raw_isbn: str) -> str:
    """清理 ISBN 字串中的破折號與多餘空白，轉大寫"""
    if not raw_isbn:
        return ""
    return re.sub(r"[^0-9X]", "", raw_isbn.strip().upper())


def resolve_highres_cover_url(raw_url: Optional[str]) -> Optional[str]:
    """
    將 Google Books 縮圖網址升級為高解析度原尺寸書封：
    1. 強制升級為 https:// 避免瀏覽器混合內容阻擋
    2. 將 &zoom=1 (小縮圖) 轉為 &zoom=0 (原尺寸大圖)
    3. 移除 &edge=curl 捲角效果，還原平整書封
    """
    if not raw_url:
        return None
    
    # 確保使用 https
    url = raw_url.replace("http://", "https://")
    
    # 提升解析度參數
    url = re.sub(r"&zoom=\d+", "&zoom=0", url)
    
    # 移除書角捲邊效果
    url = url.replace("&edge=curl", "")
    
    return url


def parse_volume_item(item: dict[str, Any]) -> dict[str, Any]:
    """將 Google Books 原始龐大 JSON 解析為繁中精煉資料結構"""
    vol_info = item.get("volumeInfo", {})
    
    # 提取 ISBN-13 與 ISBN-10
    isbn_13 = None
    isbn_10 = None
    identifiers = vol_info.get("industryIdentifiers", [])
    for ident in identifiers:
        itype = ident.get("type", "")
        ival = normalize_isbn(ident.get("identifier", ""))
        if itype == "ISBN_13":
            isbn_13 = ival
        elif itype == "ISBN_10":
            isbn_10 = ival
        elif len(ival) == 13 and not isbn_13:
            isbn_13 = ival
        elif len(ival) == 10 and not isbn_10:
            isbn_10 = ival

    # 提取書封縮圖
    image_links = vol_info.get("imageLinks", {})
    raw_cover = (
        image_links.get("extraLarge")
        or image_links.get("large")
        or image_links.get("medium")
        or image_links.get("thumbnail")
        or image_links.get("smallThumbnail")
    )
    highres_cover = resolve_highres_cover_url(raw_cover)

    # 內容摘要長度控制 (避免佔用過多 Context)
    description = vol_info.get("description")
    if description and len(description) > 300:
        description = description[:300] + "..."

    return {
        "google_books_id": item.get("id", ""),
        "title": vol_info.get("title", ""),
        "subtitle": vol_info.get("subtitle"),
        "authors": vol_info.get("authors", []),
        "publisher": vol_info.get("publisher"),
        "published_date": vol_info.get("publishedDate"),
        "isbn_13": isbn_13,
        "isbn_10": isbn_10,
        "page_count": vol_info.get("pageCount"),
        "language": vol_info.get("language", "zh-TW"),
        "cover_url": highres_cover,
        "description": description,
    }


@mcp.tool()
async def search_books(query: str, max_results: int = 5) -> dict[str, Any]:
    """
    搜尋臺灣出版品書籍。
    
    支援繁體中文書名、作者或關鍵字檢索，自動過濾並回傳精煉中繼資料與高解析度封面。
    
    參數:
      query: 搜尋關鍵字 (例如: "原子習慣" 或 "詹姆斯·克利爾")
      max_results: 最大回傳筆數 (預設 5 筆，最多 10 筆)
    """
    api_key = get_api_key()
    params: dict[str, Any] = {
        "q": query.strip(),
        "maxResults": min(max(1, max_results), 10),
        "printType": "books",
    }
    if api_key:
        params["key"] = api_key

    headers = {"User-Agent": "google-books-tw-mcp/1.0.0"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_BOOKS_API_BASE, params=params, headers=headers)
            
            if resp.status_code == 429:
                return {
                    "success": False,
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "已達到 Google Books API 頻率限制 (429)。建議配置 GOOGLE_BOOKS_API_KEY 以獲得每天 1,000 次穩定額度。",
                    "books": []
                }
            
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            
            books = [parse_volume_item(item) for item in items]
            return {
                "success": True,
                "total_items": data.get("totalItems", len(books)),
                "returned_count": len(books),
                "books": books,
                "has_api_key": bool(api_key)
            }
    except Exception as e:
        return {
            "success": False,
            "error": "REQUEST_FAILED",
            "message": str(e),
            "books": []
        }


@mcp.tool()
async def get_book_by_isbn(isbn: str) -> dict[str, Any]:
    """
    透過 ISBN 精確查詢特定書籍版本。
    
    自動過濾破折號與空格，精準定位繁體書籍出版資訊與官方封面圖。
    
    參數:
      isbn: 13 碼或 10 碼國際標準書號 (例如: "978-986-175-526-1" 或 "9789861755261")
    """
    cleaned_isbn = normalize_isbn(isbn)
    if not cleaned_isbn:
        return {
            "success": False,
            "error": "INVALID_ISBN",
            "message": "提供的 ISBN 格式不正確或為空值",
            "book": None
        }

    api_key = get_api_key()
    params: dict[str, Any] = {
        "q": f"isbn:{cleaned_isbn}",
        "maxResults": 1,
    }
    if api_key:
        params["key"] = api_key

    headers = {"User-Agent": "google-books-tw-mcp/1.0.0"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_BOOKS_API_BASE, params=params, headers=headers)
            
            if resp.status_code == 429:
                return {
                    "success": False,
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "已達到 Google Books API 頻率限制 (429)。請配置 GOOGLE_BOOKS_API_KEY 以獲得穩定配額。",
                    "book": None
                }
                
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            
            if not items:
                return {
                    "success": True,
                    "found": False,
                    "message": f"在 Google Books 資料庫中未找到 ISBN {cleaned_isbn} 的書籍紀錄",
                    "book": None
                }

            book = parse_volume_item(items[0])
            return {
                "success": True,
                "found": True,
                "book": book,
                "has_api_key": bool(api_key)
            }
    except Exception as e:
        return {
            "success": False,
            "error": "REQUEST_FAILED",
            "message": str(e),
            "book": None
        }


@mcp.tool()
async def get_book_cover(isbn_or_query: str) -> dict[str, Any]:
    """
    專門獲取書籍之高解析度封面網址。
    
    可用於 Notion 書櫃、電子書城、前端展示之高清書封直接填入。
    
    參數:
      isbn_or_query: ISBN 條碼或完整書名
    """
    target = isbn_or_query.strip()
    cleaned_isbn = normalize_isbn(target)
    
    # 若為純數字則以 ISBN 優先查詢
    query = f"isbn:{cleaned_isbn}" if (cleaned_isbn and len(cleaned_isbn) in (10, 13)) else target

    api_key = get_api_key()
    params: dict[str, Any] = {"q": query, "maxResults": 1}
    if api_key:
        params["key"] = api_key

    headers = {"User-Agent": "google-books-tw-mcp/1.0.0"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_BOOKS_API_BASE, params=params, headers=headers)
            if resp.status_code == 429:
                return {
                    "success": False,
                    "error": "RATE_LIMIT_EXCEEDED",
                    "cover_url": None,
                    "message": "API 頻率限制，請配置金鑰。"
                }
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                return {
                    "success": True,
                    "cover_url": None,
                    "message": "未找到匹配書籍"
                }
            
            book = parse_volume_item(items[0])
            return {
                "success": True,
                "title": book["title"],
                "isbn_13": book["isbn_13"],
                "cover_url": book["cover_url"],
                "message": "成功取得高畫質封面網址" if book["cover_url"] else "該書目暫無官方封面圖"
            }
    except Exception as e:
        return {
            "success": False,
            "error": "REQUEST_FAILED",
            "cover_url": None,
            "message": str(e)
        }


def main():
    """MCP 伺服器主入口點 (標準 stdio 通信模式)"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
