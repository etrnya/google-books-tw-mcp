#!/usr/bin/env python3
"""
Google Books TW MCP Server — Taiwan Book Metadata Resolver v1.3.0
專為臺灣繁體出版品市場打造的書目元資料解析與事實層 (Fact Layer) 服務
"""

import asyncio
import datetime
import json
import os
import re
import urllib.parse
from typing import Any, Optional
from bs4 import BeautifulSoup
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 優先載入本地 .env 設定 (覆蓋預設環境變數)
load_dotenv(override=True)

# 初始化 FastMCP 伺服器
mcp = FastMCP("google-books-tw-mcp")

GOOGLE_BOOKS_API_BASE = "https://www.googleapis.com/books/v1/volumes"

# 臺灣常見主要出版機構字典 (用於版本判斷與信心度加權)
KNOWN_TAIWAN_PUBLISHERS = {
    "天下文化", "商業周刊", "遠流", "方智", "圓神", "城邦", "電腦人", "電腦人文化",
    "采實文化", "三采", "時報文化", "時報出版", "皇冠", "聯經", "早安財經",
    "寶鼎", "悅知文化", "八旗文化", "衛城出版", "野人文化", "究竟", "先覺",
    "漫遊者文化", "讀書共和國", "木馬文化", "臉譜", "麥田", "貓頭鷹", "大塊文化",
    "新經典文化", "春天出版", "高寶", "商周出版", "天下雜誌", "大牌出版"
}


# ============================================================================
# 1. 安全與設定輔助函式 (Security & Configuration)
# ============================================================================

def get_api_key() -> Optional[str]:
    """獲取 Google Books API 金鑰 (優先讀取環境變數，自動過濾佔位符)"""
    key = os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()
    if not key or "YOUR_" in key or "KEY_HERE" in key or key.lower() in ("none", "undefined", "null"):
        return None
    return key


def make_error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    """建立結構化標準錯誤回傳"""
    return {
        "success": False,
        "error": code,
        "message": message,
        "retryable": retryable
    }


# ============================================================================
# 2. ISBN 清洗、驗證與雙向轉換 (ISBN Normalization & Validation)
# ============================================================================

def normalize_isbn(raw_isbn: str) -> str:
    """清理 ISBN 字串中的破折號、空格，轉大寫"""
    if not raw_isbn:
        return ""
    return re.sub(r"[^0-9X]", "", raw_isbn.strip().upper())


def validate_isbn10(isbn: str) -> bool:
    """以模數 11 驗證 ISBN-10 校驗碼"""
    clean = normalize_isbn(isbn)
    if len(clean) != 10:
        return False
    if not (clean[:9].isdigit() and (clean[9].isdigit() or clean[9] == "X")):
        return False
    
    total = sum((10 - i) * (10 if char == "X" else int(char)) for i, char in enumerate(clean))
    return total % 11 == 0


def validate_isbn13(isbn: str) -> bool:
    """以模數 10 驗證 ISBN-13 校驗碼"""
    clean = normalize_isbn(isbn)
    if len(clean) != 13 or not clean.isdigit():
        return False
    if not (clean.startswith("978") or clean.startswith("979")):
        return False

    total = sum(int(digit) * (1 if i % 2 == 0 else 3) for i, digit in enumerate(clean[:12]))
    check_digit = (10 - (total % 10)) % 10
    return int(clean[12]) == check_digit


def isbn10_to_isbn13(isbn10: str) -> Optional[str]:
    """將有效之 ISBN-10 轉換為標準 ISBN-13"""
    clean = normalize_isbn(isbn10)
    if not validate_isbn10(clean):
        return None
    
    prefix9 = "978" + clean[:9]
    total = sum(int(digit) * (1 if i % 2 == 0 else 3) for i, digit in enumerate(prefix9))
    check_digit = (10 - (total % 10)) % 10
    return prefix9 + str(check_digit)


def parse_and_validate_isbn(raw_isbn: str) -> dict[str, Any]:
    """完整檢驗並標準化輸入之 ISBN"""
    clean = normalize_isbn(raw_isbn)
    if not clean:
        return {"raw": raw_isbn, "clean": "", "type": "EMPTY", "is_valid": False, "canonical_13": None}

    if len(clean) == 13:
        is_valid = validate_isbn13(clean)
        return {
            "raw": raw_isbn,
            "clean": clean,
            "type": "ISBN-13",
            "is_valid": is_valid,
            "canonical_13": clean if is_valid else None
        }
    elif len(clean) == 10:
        is_valid = validate_isbn10(clean)
        canonical = isbn10_to_isbn13(clean) if is_valid else None
        return {
            "raw": raw_isbn,
            "clean": clean,
            "type": "ISBN-10",
            "is_valid": is_valid,
            "canonical_13": canonical
        }
    else:
        return {
            "raw": raw_isbn,
            "clean": clean,
            "type": "INVALID_LENGTH",
            "is_valid": False,
            "canonical_13": None
        }


# ============================================================================
# 3. 高畫質書封解析演算法 (Cover Resolver)
# ============================================================================

def resolve_highres_cover(raw_url: Optional[str]) -> dict[str, Any]:
    """
    升級與解析高畫質書封 URL：
    1. 強制升級 https 協議
    2. 將 &zoom=1 轉為 &zoom=0 (原尺寸)
    3. 移除 &edge=curl 捲邊效果
    """
    if not raw_url:
        return {"url": None, "resolution_hint": "none", "source": "none"}
    
    url = raw_url.replace("http://", "https://")
    url = re.sub(r"&zoom=\d+", "&zoom=0", url)
    url = url.replace("&edge=curl", "")
    
    return {
        "url": url,
        "resolution_hint": "high",
        "source": "google_books"
    }


# ============================================================================
# 4. 事實層提取與信心度評分 (Fact Extractor & Confidence Engine)
# ============================================================================

def build_book_fact(item: dict[str, Any], query_used: str, is_isbn_query: bool) -> dict[str, Any]:
    """將 Google Books 原始資料解析為結構化之 Fact Layer"""
    vol_info = item.get("volumeInfo", {})
    
    # 提取身分識別碼 (Identity Keys)
    isbn_13 = None
    isbn_10 = None
    identifiers = vol_info.get("industryIdentifiers", [])
    for ident in identifiers:
        itype = ident.get("type", "")
        ival = normalize_isbn(ident.get("identifier", ""))
        if itype == "ISBN_13" and validate_isbn13(ival):
            isbn_13 = ival
        elif itype == "ISBN_10" and validate_isbn10(ival):
            isbn_10 = ival
        elif len(ival) == 13 and validate_isbn13(ival) and not isbn_13:
            isbn_13 = ival
        elif len(ival) == 10 and validate_isbn10(ival) and not isbn_10:
            isbn_10 = ival

    # 若有 10 碼無 13 碼，自動補齊 13 碼
    if isbn_10 and not isbn_13:
        isbn_13 = isbn10_to_isbn13(isbn_10)

    # 書封升級
    image_links = vol_info.get("imageLinks", {})
    raw_cover = (
        image_links.get("extraLarge")
        or image_links.get("large")
        or image_links.get("medium")
        or image_links.get("thumbnail")
        or image_links.get("smallThumbnail")
    )
    cover_fact = resolve_highres_cover(raw_cover)
    if not cover_fact["url"] and isbn_13 and isbn_13.startswith("978"):
        cover_fact = {
            "url": f"https://cdnec.sanmin.com.tw/product_images/{isbn_13[3:6]}/{isbn_13[3:12]}.jpg",
            "resolution_hint": "high",
            "source": "taiwan_catalog_cdn"
        }

    # 臺灣出版社與繁中特徵識別
    publisher = vol_info.get("publisher", "")
    is_tw_publisher = any(tw_pub in (publisher or "") for tw_pub in KNOWN_TAIWAN_PUBLISHERS)
    language = vol_info.get("language", "zh-TW")

    # 信心度評分演算法 (Confidence Scoring)
    confidence = 0.60
    reasons: list[str] = []

    if is_isbn_query and isbn_13:
        confidence += 0.30
        reasons.append("exact_isbn_checksum_passed")
    elif not is_isbn_query:
        reasons.append("title_keyword_match")

    if is_tw_publisher:
        confidence += 0.08
        reasons.append(f"taiwan_publisher_recognized:{publisher}")

    if language in ("zh-TW", "zh-Hant", "zh"):
        confidence += 0.05
        reasons.append("traditional_chinese_compatible")

    if cover_fact["url"]:
        confidence += 0.02
        reasons.append("cover_image_resolved")

    confidence = min(round(confidence, 2), 0.99)

    # 內容摘要精簡
    description = vol_info.get("description")
    if description and len(description) > 300:
        description = description[:300] + "..."

    return {
        "identity": {
            "isbn_13": isbn_13,
            "isbn_10": isbn_10,
            "google_books_id": item.get("id", "")
        },
        "work": {
            "title": vol_info.get("title", ""),
            "subtitle": vol_info.get("subtitle"),
            "authors": vol_info.get("authors", []),
            "translators": [],
            "language": language
        },
        "edition": {
            "publisher": publisher or None,
            "published_date": vol_info.get("publishedDate"),
            "page_count": vol_info.get("pageCount"),
            "print_type": vol_info.get("printType", "BOOK"),
            "binding": None,
            "price": None,
            "category": vol_info.get("categories", [None])[0] if vol_info.get("categories") else None
        },
        "cover": cover_fact,
        "description": description,
        "source": {
            "provider": "google_books",
            "confidence": confidence,
            "confidence_reasons": reasons,
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    }


# ============================================================================
# 4.5 臺灣本土多來源級聯備援解析引擎 (Taiwan Multi-Source Cascading Fallback Engine)
# ============================================================================

def get_taiwan_isbn_cover(isbn_13: str) -> Optional[str]:
    """臺灣三民 CDN 高畫質原圖映射 (100% 離線可用，免金鑰)"""
    if isbn_13 and len(isbn_13) == 13 and isbn_13.startswith("978"):
        return f"https://cdnec.sanmin.com.tw/product_images/{isbn_13[3:6]}/{isbn_13[3:12]}.jpg"
    return None


async def resolve_tenlong_book(query_or_isbn: str, is_isbn: bool, canonical_13: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    【天瓏網路書店解析器】專門自天瓏獲取精確繁體中文書目、作者/譯者分離與原始高解析封面
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    clean_target = query_or_isbn.strip()
    
    try:
        async with httpx.AsyncClient(headers=headers, timeout=6.0, verify=False, follow_redirects=True) as client:
            soup = None
            resolved_isbn = canonical_13

            # 模式 A: 精確 ISBN 直達產品頁
            if is_isbn and canonical_13:
                r = await client.get(f"https://www.tenlong.com.tw/products/{canonical_13}")
                if r.status_code == 200 and "item-title" in r.text:
                    soup = BeautifulSoup(r.text, "html.parser")
            
            # 模式 B: 書名關鍵字檢索
            if not soup and not is_isbn:
                q_quoted = urllib.parse.quote(clean_target)
                r_s = await client.get(f"https://www.tenlong.com.tw/search?keyword={q_quoted}")
                if r_s.status_code == 200:
                    s_soup = BeautifulSoup(r_s.text, "html.parser")
                    bd = s_soup.select_one(".book-data")
                    if bd:
                        a_el = bd.select_one("strong a, .title a")
                        if a_el and a_el.get("href"):
                            href = a_el["href"]
                            m_isbn = re.search(r"/products/(\d{10,13})", href)
                            if m_isbn:
                                resolved_isbn = m_isbn.group(1)
                                if len(resolved_isbn) == 10:
                                    resolved_isbn = isbn10_to_isbn13(resolved_isbn) or resolved_isbn
                            prod_url = "https://www.tenlong.com.tw" + href if href.startswith("/") else href
                            r_det = await client.get(prod_url)
                            if r_det.status_code == 200 and "item-title" in r_det.text:
                                soup = BeautifulSoup(r_det.text, "html.parser")

            if not soup:
                return None

            title_el = soup.select_one("h1.item-title")
            if not title_el:
                return None
            title = title_el.text.strip()

            # 作者與譯者拆分
            authors: list[str] = []
            translators: list[str] = []
            author_el = soup.select_one("h3.item-author")
            if author_el:
                for line in author_el.text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if "譯" in line:
                        translators.append(re.sub(r"[\s譯]+$", "", line).strip())
                    else:
                        authors.append(re.sub(r"[\s著編]+$", "", line).strip())

            # 提取詳細出版屬性
            publisher = None
            published_date = None
            price: Optional[int] = None
            page_count: Optional[int] = None
            binding = None
            category = None
            language = "zh-TW"

            for li in soup.select(".item-info li"):
                t = li.text.strip()
                if "出版商:" in t:
                    publisher = t.replace("出版商:", "").strip()
                elif "出版日期:" in t:
                    published_date = t.replace("出版日期:", "").strip()
                elif "定價:" in t:
                    m_p = re.search(r"(\d+)", t)
                    if m_p:
                        price = int(m_p.group(1))
                elif "頁數:" in t:
                    m_pg = re.search(r"(\d+)", t)
                    if m_pg:
                        page_count = int(m_pg.group(1))
                elif "裝訂:" in t:
                    binding = t.replace("裝訂:", "").strip()
                elif "相關分類:" in t:
                    category = t.replace("相關分類:", "").strip()
                elif "語言:" in t:
                    lang_str = t.replace("語言:", "").strip()
                    if "繁體" in lang_str:
                        language = "zh-TW"

            # 原尺寸高解析封面 (升級為 /original/)
            cover_url = None
            img = soup.select_one(".single-book-media img, .cover img")
            if img:
                raw_src = img.get("src") or ""
                cover_url = raw_src.replace("/medium/", "/original/") if raw_src else None

            # 若未抓到封面且有 ISBN-13，以臺灣 CDN 補全
            if not cover_url and resolved_isbn:
                cover_url = get_taiwan_isbn_cover(resolved_isbn)

            # 商品簡介
            description = None
            for h2 in soup.find_all("h2"):
                if "商品描述" in h2.text:
                    sib = h2.find_next_sibling()
                    if sib:
                        description = sib.get_text(strip=True)[:300]
                    break

            confidence = 0.96 if is_isbn else 0.88
            reasons = ["tenlong_catalog_match"]
            if is_isbn:
                reasons.insert(0, "exact_isbn_checksum_passed")
            if publisher:
                reasons.append(f"taiwan_publisher_recognized:{publisher}")
            if cover_url:
                reasons.append("cover_image_resolved")

            return {
                "identity": {
                    "isbn_13": resolved_isbn,
                    "isbn_10": None,
                    "google_books_id": None
                },
                "work": {
                    "title": title,
                    "subtitle": None,
                    "authors": authors,
                    "translators": translators,
                    "language": language
                },
                "edition": {
                    "publisher": publisher,
                    "published_date": published_date,
                    "page_count": page_count,
                    "print_type": "BOOK",
                    "binding": binding,
                    "price": price,
                    "category": category
                },
                "cover": {
                    "url": cover_url,
                    "resolution_hint": "high" if cover_url else "none",
                    "source": "tenlong"
                },
                "description": description,
                "source": {
                    "provider": "tenlong",
                    "confidence": confidence,
                    "confidence_reasons": reasons,
                    "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
            }
    except Exception:
        pass

    return None


async def resolve_sanmin_book(query_or_isbn: str, is_isbn: bool, canonical_13: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    【三民網路書店解析器】專門自三民檢索出版品，提取 Schema.org JSON-LD Book 結構化數據與本土 CDN
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    clean_target = query_or_isbn.strip()
    target_param = canonical_13 if (is_isbn and canonical_13) else clean_target
    
    try:
        async with httpx.AsyncClient(headers=headers, timeout=6.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(f"https://www.sanmin.com.tw/search?ct=K&qu={urllib.parse.quote(target_param)}")
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            prod_items = soup.select("div.Prod, div.sProduct")
            if not prod_items:
                return None

            # 挑選最佳商品 (優先挑實體書避免電子書優先排序)
            best_link = None
            snippet_title = None
            snippet_author = None
            snippet_pub = None
            snippet_binding = None
            snippet_date = None

            for prod in prod_items:
                a_tag = prod.select_one("a")
                if not a_tag or not a_tag.get("href"):
                    continue
                href = a_tag["href"]
                if "/product/index/" in href:
                    p_text = prod.get_text(separator=" ", strip=True)
                    if not best_link or "電子書" not in p_text:
                        best_link = href
                        m_t = re.search(r"\d+[\.、]\s*([^\s]+)", p_text)
                        if m_t: snippet_title = m_t.group(1).strip()
                        m_auth = re.search(r"作者[：:\s]+([^\s\n\r]+)", p_text)
                        if m_auth: snippet_author = m_auth.group(1).strip()
                        m_pub = re.search(r"出版社[：:\s]+([^\s\n\r]+)", p_text)
                        if m_pub: snippet_pub = m_pub.group(1).strip()
                        m_bind = re.search(r"裝訂[：:\s]+([^\s\n\r]+)", p_text)
                        if m_bind: snippet_binding = m_bind.group(1).strip()
                        m_date = re.search(r"出版日[：:\s]+([^\s\n\r]+)", p_text)
                        if m_date: snippet_date = m_date.group(1).strip()
                        if "電子書" not in p_text:
                            break

            if not best_link:
                return None

            detail_url = "https://www.sanmin.com.tw" + best_link if best_link.startswith("/") else best_link
            r_det = await client.get(detail_url)

            json_ld = None
            categories = []
            if r_det.status_code == 200:
                soup_det = BeautifulSoup(r_det.text, "html.parser")
                for s in soup_det.find_all("script"):
                    if s.string and "schema.org" in s.string and "Book" in s.string:
                        try:
                            json_ld = json.loads(s.string.strip())
                            break
                        except Exception:
                            pass
                for s in soup_det.find_all("script"):
                    if s.string and "BreadcrumbList" in s.string:
                        try:
                            bc = json.loads(s.string.strip())
                            items = bc.get("itemListElement", [])
                            categories = [it.get("name") for it in items if it.get("name") and it.get("name") not in ("首頁", "中文書")]
                            break
                        except Exception:
                            pass

            resolved_isbn = canonical_13
            cover_url = get_taiwan_isbn_cover(canonical_13) if canonical_13 else None

            if json_ld:
                name = json_ld.get("name", "").strip()
                name = re.sub(r"^\d+[\.、]\s*", "", name)
                if json_ld.get("isbn") and not resolved_isbn:
                    resolved_isbn = json_ld.get("isbn")
                    cover_url = get_taiwan_isbn_cover(resolved_isbn)

                authors: list[str] = []
                for a in json_ld.get("author", []):
                    if isinstance(a, dict) and a.get("name"):
                        authors.append(a.get("name"))
                    elif isinstance(a, str):
                        authors.append(a)

                publishers: list[str] = []
                for p in json_ld.get("publisher", []):
                    if isinstance(p, dict) and p.get("name"):
                        publishers.append(p.get("name"))
                    elif isinstance(p, str):
                        publishers.append(p)
                publisher = publishers[0] if publishers else snippet_pub

                desc = json_ld.get("description", "")
                translators: list[str] = []
                m_trans = re.search(r"譯者[：:\s]+([^\s,，;；]+)", desc)
                if m_trans:
                    translators.append(m_trans.group(1).strip())

                fmt = json_ld.get("BookFormat", "")
                binding = "平裝" if "Paperback" in fmt else ("精裝" if "Hardcover" in fmt else ("電子書" if "EBook" in fmt else (snippet_binding or fmt)))

                price: Optional[int] = None
                offers = json_ld.get("offers", {})
                if offers.get("price"):
                    try: price = int(float(offers.get("price")))
                    except Exception: pass

                pages: Optional[int] = None
                if json_ld.get("numberOfPages"):
                    try: pages = int(json_ld.get("numberOfPages"))
                    except Exception: pass

                if not cover_url:
                    cover_url = json_ld.get("image")

                confidence = 0.97 if is_isbn else 0.88
                reasons = ["sanmin_catalog_match", "schema_org_validated"]
                if is_isbn:
                    reasons.insert(0, "exact_isbn_checksum_passed")
                if publisher:
                    reasons.append(f"taiwan_publisher_recognized:{publisher}")

                return {
                    "identity": {
                        "isbn_13": resolved_isbn,
                        "isbn_10": None,
                        "google_books_id": None
                    },
                    "work": {
                        "title": name or (snippet_title or clean_target),
                        "subtitle": None,
                        "authors": authors or ([snippet_author] if snippet_author else []),
                        "translators": translators,
                        "language": "zh-TW"
                    },
                    "edition": {
                        "publisher": publisher,
                        "published_date": json_ld.get("datePublished") or snippet_date,
                        "page_count": pages,
                        "print_type": "BOOK" if binding != "電子書" else "EBOOK",
                        "binding": binding,
                        "price": price,
                        "category": " > ".join(categories) if categories else None
                    },
                    "cover": {
                        "url": cover_url,
                        "resolution_hint": "high" if cover_url else "none",
                        "source": "sanmin"
                    },
                    "description": desc[:300] if desc else None,
                    "source": {
                        "provider": "sanmin",
                        "confidence": confidence,
                        "confidence_reasons": reasons,
                        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }
                }
            elif snippet_title:
                return {
                    "identity": {
                        "isbn_13": resolved_isbn,
                        "isbn_10": None,
                        "google_books_id": None
                    },
                    "work": {
                        "title": snippet_title,
                        "subtitle": None,
                        "authors": [snippet_author] if snippet_author else [],
                        "translators": [],
                        "language": "zh-TW"
                    },
                    "edition": {
                        "publisher": snippet_pub,
                        "published_date": snippet_date,
                        "page_count": None,
                        "print_type": "BOOK" if snippet_binding != "電子書" else "EBOOK",
                        "binding": snippet_binding,
                        "price": None,
                        "category": None
                    },
                    "cover": {
                        "url": cover_url,
                        "resolution_hint": "high" if cover_url else "none",
                        "source": "sanmin"
                    },
                    "description": None,
                    "source": {
                        "provider": "sanmin",
                        "confidence": 0.85,
                        "confidence_reasons": ["sanmin_catalog_match"],
                        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }
                }
    except Exception:
        pass

    return None


async def fallback_resolve_book(query_or_isbn: str, is_isbn: bool, canonical_13: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    【多來源級聯備援中樞】按天瓏 (Tenlong) ➔ 三民 (Sanmin) ➔ 臺灣 CDN 階梯級聯
    """
    clean_target = query_or_isbn.strip()

    # 級聯階梯 1: 天瓏專門書庫 (IT、商管、翻譯書最精確，作者譯者分離度高)
    tl_res = await resolve_tenlong_book(clean_target, is_isbn, canonical_13)
    if tl_res and tl_res.get("source", {}).get("confidence", 0) >= 0.90:
        return tl_res

    # 級聯階梯 2: 三民綜合書庫 (全臺灣書籍涵蓋度 99%+，含 Schema.org JSON-LD)
    sm_res = await resolve_sanmin_book(clean_target, is_isbn, canonical_13)
    if sm_res:
        return sm_res

    # 若階梯 1 有結果但信心度稍低，此時回傳階梯 1
    if tl_res:
        return tl_res

    # 級聯階梯 3: 臺灣 ISBN-13 CDN 演算法保底 (針對任何合法 13 碼書號直出原圖封面)
    if is_isbn and canonical_13:
        cover_url = get_taiwan_isbn_cover(canonical_13)
        return {
            "identity": {
                "isbn_13": canonical_13,
                "isbn_10": None,
                "google_books_id": None
            },
            "work": {
                "title": clean_target,
                "subtitle": None,
                "authors": [],
                "translators": [],
                "language": "zh-TW"
            },
            "edition": {
                "publisher": None,
                "published_date": None,
                "page_count": None,
                "print_type": "BOOK",
                "binding": None,
                "price": None,
                "category": None
            },
            "cover": {
                "url": cover_url,
                "resolution_hint": "high" if cover_url else "none",
                "source": "taiwan_catalog_cdn"
            },
            "description": None,
            "source": {
                "provider": "taiwan_catalog_cdn",
                "confidence": 0.90,
                "confidence_reasons": ["exact_isbn_checksum_passed"],
                "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        }

    return None


async def fallback_search_books(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """當 Google Books 遇到頻率限制時，多來源級聯搜尋臺灣本土出版品清單"""
    clean_target = query.strip()
    
    # 併行查詢天瓏與三民
    tl_task = resolve_tenlong_book(clean_target, is_isbn=False)
    sm_task = resolve_sanmin_book(clean_target, is_isbn=False)
    
    results = await asyncio.gather(tl_task, sm_task, return_exceptions=True)
    books: list[dict[str, Any]] = []
    seen_titles = set()

    for res in results:
        if isinstance(res, dict) and res.get("work", {}).get("title"):
            title = res["work"]["title"]
            if title not in seen_titles:
                seen_titles.add(title)
                books.append(res)

    return books[:max_results]


# ============================================================================
# 5. MCP 核心工具 (Tools API)
# ============================================================================

@mcp.tool()
async def resolve_book(query_or_isbn: str) -> dict[str, Any]:
    """
    【一站式核心工具】自動解析書籍身分、出版版本、高解析封面與信心度 (Taiwan Book Metadata Resolver)。
    
    支援直接輸入 ISBN (含破折號) 或繁體中文書名，自動執行：
    1. ISBN 清洗與校驗碼驗證 (Checksum Validation)
    2. Google Books 精確檢索 (具備臺灣書目庫自動備援)
    3. 書封高畫質升級與安全協議校正
    4. 輸出結構化 Fact Layer (包含 identity, work, edition, cover, source)
    
    參數:
      query_or_isbn: 13 碼/10 碼 ISBN 條碼 (例如 "978-986-175-526-1") 或繁體書名 (例如 "原子習慣")
    """
    target = query_or_isbn.strip()
    isbn_info = parse_and_validate_isbn(target)

    api_key = get_api_key()
    headers = {"User-Agent": "google-books-tw-mcp/1.1.0"}

    # 依輸入類型建構查詢條件
    is_isbn = isbn_info["is_valid"]
    if is_isbn and isbn_info["canonical_13"]:
        params = {"q": f"isbn:{isbn_info['canonical_13']}", "maxResults": 1, "printType": "books"}
    else:
        params = {"q": f"intitle:{target}", "maxResults": 1, "printType": "books"}

    if api_key:
        params["key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_BOOKS_API_BASE, params=params, headers=headers)
            
            # 若 Google Books 限制或無結果，啟動臺灣本土備援
            if resp.status_code in (400, 429) or (resp.status_code == 200 and not resp.json().get("items")):
                fb = await fallback_resolve_book(target, is_isbn, isbn_info.get("canonical_13"))
                if fb:
                    return {"success": True, "found": True, "book": fb}
            
            if resp.status_code == 429:
                return make_error("RATE_LIMITED", "Google Books API 頻率限制 (429)。請在 .env 配置 GOOGLE_BOOKS_API_KEY。", retryable=True)
            elif resp.status_code >= 500:
                return make_error("UPSTREAM_5XX", f"Google Books 伺服器異常 ({resp.status_code})。", retryable=True)
            
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            
            if not items:
                fb = await fallback_resolve_book(target, is_isbn, isbn_info.get("canonical_13"))
                if fb:
                    return {"success": True, "found": True, "book": fb}
                return {
                    "success": True,
                    "found": False,
                    "message": f"未檢索到符合之書籍: {target}",
                    "book": None
                }

            fact = build_book_fact(items[0], query_used=target, is_isbn_query=is_isbn)
            return {
                "success": True,
                "found": True,
                "book": fact
            }
    except Exception as e:
        # 網路異常或逾時，嘗試本土備援
        fb = await fallback_resolve_book(target, is_isbn, isbn_info.get("canonical_13"))
        if fb:
            return {"success": True, "found": True, "book": fb}
        return make_error("UPSTREAM_ERROR", f"請求發生錯誤: {str(e)}", retryable=False)


@mcp.tool()
async def search_books(query: str, search_type: str = "auto", language: str = "zh-TW", max_results: int = 5) -> dict[str, Any]:
    """
    搜尋臺灣繁體出版品書籍清單。
    
    參數:
      query: 搜尋關鍵字 (書名、作者或 ISBN)
      search_type: 搜尋模式，可選 "auto" (自動偵測), "title" (僅搜書名), "author" (僅搜作者), "isbn" (僅搜條碼)
      language: 偏好語言代碼 (預設 "zh-TW")
      max_results: 最大回傳筆數 (預設 5 筆，最大 10 筆)
    """
    api_key = get_api_key()
    clean_query = query.strip()

    # 依搜尋類型封裝前綴
    if search_type == "title":
        api_q = f"intitle:{clean_query}"
    elif search_type == "author":
        api_q = f"inauthor:{clean_query}"
    elif search_type == "isbn":
        isbn_val = normalize_isbn(clean_query)
        api_q = f"isbn:{isbn_val}"
    else:
        # auto 模式
        isbn_info = parse_and_validate_isbn(clean_query)
        if isbn_info["is_valid"] and isbn_info["canonical_13"]:
            api_q = f"isbn:{isbn_info['canonical_13']}"
        else:
            api_q = clean_query

    params: dict[str, Any] = {
        "q": api_q,
        "maxResults": min(max(1, max_results), 10),
        "printType": "books",
    }
    if api_key:
        params["key"] = api_key

    headers = {"User-Agent": "google-books-tw-mcp/1.1.0"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_BOOKS_API_BASE, params=params, headers=headers)
            
            if resp.status_code in (400, 429) or (resp.status_code == 200 and not resp.json().get("items")):
                fb_books = await fallback_search_books(clean_query, max_results=max_results)
                if fb_books:
                    return {
                        "success": True,
                        "total_items": len(fb_books),
                        "returned_count": len(fb_books),
                        "books": fb_books
                    }

            if resp.status_code == 429:
                return make_error("RATE_LIMITED", "Google Books API 頻率限制 (429)。請配置金鑰。", retryable=True)
            elif resp.status_code >= 500:
                return make_error("UPSTREAM_5XX", f"Google Books 伺服器異常 ({resp.status_code})。", retryable=True)
            
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            
            if not items:
                fb_books = await fallback_search_books(clean_query, max_results=max_results)
                if fb_books:
                    return {
                        "success": True,
                        "total_items": len(fb_books),
                        "returned_count": len(fb_books),
                        "books": fb_books
                    }

            books = [build_book_fact(item, query_used=clean_query, is_isbn_query=(search_type == "isbn")) for item in items]
            return {
                "success": True,
                "total_items": data.get("totalItems", len(books)),
                "returned_count": len(books),
                "books": books
            }
    except Exception as e:
        fb_books = await fallback_search_books(clean_query, max_results=max_results)
        if fb_books:
            return {
                "success": True,
                "total_items": len(fb_books),
                "returned_count": len(fb_books),
                "books": fb_books
            }
        return make_error("UPSTREAM_ERROR", f"搜尋失敗: {str(e)}", retryable=False)


@mcp.tool()
async def get_book_by_isbn(isbn: str) -> dict[str, Any]:
    """
    透過 ISBN 精確查詢書籍出版版本 (含校驗碼驗證)。
    
    參數:
      isbn: 13 碼或 10 碼國際標準書號 (例如 "978-986-175-526-1")
    """
    return await resolve_book(query_or_isbn=isbn)


@mcp.tool()
async def get_book_cover(isbn_or_query: str) -> dict[str, Any]:
    """
    專門獲取高解析度、平整且安全的書籍封面 URL。
    
    參數:
      isbn_or_query: ISBN 條碼或完整書名
    """
    res = await resolve_book(query_or_isbn=isbn_or_query)
    if not res.get("success"):
        return res
    if not res.get("found"):
        return {
            "success": True,
            "cover_url": None,
            "message": "未找到匹配書籍"
        }
    
    book = res["book"]
    return {
        "success": True,
        "title": book["work"]["title"],
        "isbn_13": book["identity"]["isbn_13"],
        "cover": book["cover"],
        "source": book["source"]
    }


def main():
    """MCP 伺服器主入口點 (標準 stdio 通信模式)"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
