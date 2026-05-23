"""
crawler.py — 中山大學資管系官網爬蟲模組

目標：抓取系所最新消息標題與連結，寫入資料庫並回傳新增數量。

官網結構（以 BeautifulSoup 解析）：
  https://mis.nsysu.edu.tw/news
  → 新聞列表 <div class="news-list"> 或 <ul class="list-group">
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import settings
from app.database import upsert_announcement

logger = logging.getLogger(__name__)

# ── HTTP Session（共用連線池，加入合理 User-Agent）─────────────
_http = requests.Session()
_http.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (compatible; NSYSU-MIS-Bot/1.0; "
            "+https://mis.nsysu.edu.tw)"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
)

BASE_URL = "https://mis.nsysu.edu.tw"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 資料容器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class NewsItem:
    title: str
    url: str
    published_at: str | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 解析策略（由上到下依序嘗試，確保健壯性）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_strategy_v1(soup: BeautifulSoup) -> list[NewsItem]:
    """
    策略 1：常見的 Bootstrap list-group 結構
    <a class="list-group-item" href="/news/123">
      <span class="date">2024-08-01</span>【公告】標題文字
    </a>
    """
    items: list[NewsItem] = []
    for tag in soup.select("a.list-group-item[href]"):
        href = tag["href"]
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)

        date_tag = tag.select_one("span.date, .news-date, time")
        published_at = date_tag.get_text(strip=True) if date_tag else None
        if date_tag:
            date_tag.decompose()

        title = tag.get_text(separator=" ", strip=True)
        title = re.sub(r"\s+", " ", title)
        if title:
            items.append(NewsItem(title=title, url=href, published_at=published_at))
    return items


def _parse_strategy_v2(soup: BeautifulSoup) -> list[NewsItem]:
    """
    策略 2：table 結構
    <table>
      <tr>
        <td>2024-08-01</td>
        <td><a href="/news/123">標題</a></td>
      </tr>
    """
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
        # 嘗試找日期（格式 YYYY-MM-DD 或 YYY/MM/DD）
        for cell in cells:
            text = cell.get_text(strip=True)
            if re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", text):
                date_text = text
                break

        if link:
            href = link["href"]
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            title = link.get_text(strip=True)
            if title:
                items.append(NewsItem(title=title, url=href, published_at=date_text))
    return items


def _parse_strategy_v3(soup: BeautifulSoup) -> list[NewsItem]:
    """
    策略 3：廣義掃描 —— 找所有帶 /news/ 或 /announcement/ 的內部連結。
    作為最後備用，避免因版面改版導致爬蟲完全失效。
    """
    items: list[NewsItem] = []
    seen: set[str] = set()
    pattern = re.compile(r"/(news|announcement|bulletin)/", re.IGNORECASE)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not pattern.search(href):
            continue
        if not href.startswith("http"):
            href = urljoin(BASE_URL, href)
        if href in seen:
            continue
        seen.add(href)
        title = a.get_text(strip=True)
        if title and len(title) > 3:
            items.append(NewsItem(title=title, url=href))
    return items


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 公開 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_news(url: str | None = None, timeout: int = 15) -> list[NewsItem]:
    """
    抓取系所公告頁面，回傳 NewsItem 清單。
    會依序嘗試三種解析策略，取最多結果的那個。
    """
    target_url = url or settings.nsysu_mis_url
    logger.info("爬蟲啟動，目標：%s", target_url)

    try:
        resp = _http.get(target_url, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except requests.RequestException as exc:
        logger.error("HTTP 請求失敗：%s", exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # 依序嘗試策略
    for strategy in (_parse_strategy_v1, _parse_strategy_v2, _parse_strategy_v3):
        results = strategy(soup)
        if results:
            logger.info("解析策略 %s 找到 %d 筆公告", strategy.__name__, len(results))
            return results

    logger.warning("所有解析策略均未找到公告，請確認網站結構是否異動。")
    return []


def crawl_and_save(db: Session) -> tuple[int, int]:
    """
    執行爬蟲並將結果存入資料庫。

    Returns:
        (total_fetched, new_count)
        total_fetched: 本次爬到的公告總數
        new_count:     實際新增（未重複）的公告數
    """
    items = fetch_news()
    if not items:
        return 0, 0

    new_count = 0
    for item in items:
        _, is_new = upsert_announcement(
            db,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
        )
        if is_new:
            new_count += 1
            logger.info("新公告已儲存：%s", item.title[:50])

    logger.info(
        "爬蟲完成 — 共 %d 筆，新增 %d 筆，重複跳過 %d 筆",
        len(items),
        new_count,
        len(items) - new_count,
    )
    return len(items), new_count
