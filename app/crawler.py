"""
crawler.py — 中山大學資管系官網爬蟲模組
目標網站：https://web.mis.nsysu.edu.tw/
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import settings
from app.database import upsert_announcement

logger = logging.getLogger(__name__)

_http = requests.Session()
_http.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
})

BASE_URL = "https://web.mis.nsysu.edu.tw"


@dataclass
class NewsItem:
    title: str
    url: str
    published_at: str | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 解析策略（由上到下依序嘗試）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_strategy_v1(soup: BeautifulSoup) -> list[NewsItem]:
    """策略1：Bootstrap list-group 結構"""
    items: list[NewsItem] = []
    for tag in soup.select("a.list-group-item[href]"):
        href = tag["href"]
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        date_tag = tag.select_one("span.date, .news-date, time, span.list-date")
        published_at = date_tag.get_text(strip=True) if date_tag else None
        if date_tag:
            date_tag.decompose()
        title = re.sub(r"\s+", " ", tag.get_text(separator=" ", strip=True))
        if title and len(title) > 3:
            items.append(NewsItem(title=title, url=href, published_at=published_at))
    return items


def _parse_strategy_v2(soup: BeautifulSoup) -> list[NewsItem]:
    """策略2：table 結構"""
    items: list[NewsItem] = []
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        link = None
        date_text = None
        for cell in cells:
            a = cell.find("a", href=True)
            if a:
                link = a
                break
        for cell in cells:
            text = cell.get_text(strip=True)
            if re.search(r"\d{3,4}[-/]\d{1,2}[-/]\d{1,2}", text):
                date_text = text
                break
        if link:
            href = link["href"]
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            title = link.get_text(strip=True)
            if title and len(title) > 3:
                items.append(NewsItem(title=title, url=href, published_at=date_text))
    return items


def _parse_strategy_v3(soup: BeautifulSoup) -> list[NewsItem]:
    """策略3：中山大學常見的 dd/dt 結構或 li 結構"""
    items: list[NewsItem] = []
    seen: set[str] = set()

    # 嘗試 dl/dd 結構（中山大學常用）
    for dd in soup.select("dd, li"):
        a = dd.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        if href in seen:
            continue
        seen.add(href)
        title = a.get_text(strip=True)
        # 找同層的日期
        date_tag = dd.find(string=re.compile(r"\d{3,4}[-/\.]\d{1,2}[-/\.]\d{1,2}"))
        published_at = date_tag.strip() if date_tag else None
        if title and len(title) > 5:
            items.append(NewsItem(title=title, url=href, published_at=published_at))
    return items


def _parse_strategy_v4(soup: BeautifulSoup) -> list[NewsItem]:
    """策略4：廣義掃描所有內部連結，過濾出公告類連結"""
    items: list[NewsItem] = []
    seen: set[str] = set()
    # 排除的關鍵字（導覽列、頁尾等無關連結）
    exclude = {"回首頁", "首頁", "登入", "english", "sitemap", "top", "更多", "more"}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)

        if not title or len(title) < 5:
            continue
        if title.lower() in exclude:
            continue
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        # 只要是同網域的連結
        if "mis.nsysu.edu.tw" not in href and "nsysu.edu.tw" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)
        items.append(NewsItem(title=title, url=href))

    return items


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 公開 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_news(url: str | None = None, timeout: int = 20) -> list[NewsItem]:
    """抓取系所公告頁面，依序嘗試四種解析策略。"""
    target_url = url or settings.nsysu_mis_url
    logger.info("爬蟲啟動，目標：%s", target_url)

    try:
        resp = _http.get(target_url, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        logger.info("HTTP 成功：status=%d len=%d", resp.status_code, len(resp.text))
    except requests.RequestException as exc:
        logger.error("HTTP 請求失敗：%s", exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    for strategy in (_parse_strategy_v1, _parse_strategy_v2,
                     _parse_strategy_v3, _parse_strategy_v4):
        results = strategy(soup)
        if results:
            logger.info("策略 %s 找到 %d 筆", strategy.__name__, len(results))
            return results[:30]  # 最多取 30 筆

    logger.warning("所有解析策略均未找到公告，請確認網站結構。")
    return []


def crawl_and_save(db: Session) -> tuple[int, int]:
    """執行爬蟲並存入資料庫，回傳 (total, new_count)。"""
    items = fetch_news()
    if not items:
        return 0, 0

    new_count = 0
    for item in items:
        _, is_new = upsert_announcement(
            db, title=item.title, url=item.url, published_at=item.published_at,
        )
        if is_new:
            new_count += 1
            logger.info("新公告：%s", item.title[:50])

    logger.info("爬蟲完成：共 %d 筆，新增 %d 筆", len(items), new_count)
    return len(items), new_count
