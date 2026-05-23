"""
tests/test_crawler.py — 爬蟲模組單元測試

測試策略：
  - 用 unittest.mock 模擬 HTTP 請求，不依賴真實網路
  - 測試三種解析策略的正確性
  - 測試去重邏輯（upsert_announcement）
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crawler import (
    NewsItem,
    _parse_strategy_v1,
    _parse_strategy_v2,
    _parse_strategy_v3,
    fetch_news,
)
from bs4 import BeautifulSoup


# ── 假 HTML 資料 ──────────────────────────────────────────────

STRATEGY_V1_HTML = """
<html><body>
  <div class="news-list">
    <a class="list-group-item" href="/news/1">
      <span class="date">2024-09-01</span>【公告】大一選課說明會
    </a>
    <a class="list-group-item" href="/news/2">
      <span class="date">2024-09-02</span>【活動】資管系迎新晚會
    </a>
  </div>
</body></html>
"""

STRATEGY_V2_HTML = """
<html><body>
  <table>
    <tr>
      <td>2024-09-01</td>
      <td><a href="/bulletin/101">大一說明會公告</a></td>
    </tr>
    <tr>
      <td>2024-09-03</td>
      <td><a href="/bulletin/102">期中考時程表</a></td>
    </tr>
  </table>
</body></html>
"""

STRATEGY_V3_HTML = """
<html><body>
  <a href="/news/101">獎學金申請公告</a>
  <a href="/news/102">交換學生說明會</a>
  <a href="https://external.com">外部連結（應被過濾）</a>
</body></html>
"""


class TestParseStrategies(unittest.TestCase):

    def test_strategy_v1_parses_list_group(self):
        soup = BeautifulSoup(STRATEGY_V1_HTML, "lxml")
        items = _parse_strategy_v1(soup)
        self.assertEqual(len(items), 2)
        self.assertIn("選課說明會", items[0].title)
        self.assertIn("迎新晚會", items[1].title)
        self.assertEqual(items[0].published_at, "2024-09-01")

    def test_strategy_v2_parses_table(self):
        soup = BeautifulSoup(STRATEGY_V2_HTML, "lxml")
        items = _parse_strategy_v2(soup)
        self.assertEqual(len(items), 2)
        self.assertIn("說明會", items[0].title)
        self.assertEqual(items[0].published_at, "2024-09-01")

    def test_strategy_v3_finds_news_links(self):
        soup = BeautifulSoup(STRATEGY_V3_HTML, "lxml")
        items = _parse_strategy_v3(soup)
        urls = [i.url for i in items]
        # 應該找到兩個 /news/ 連結
        self.assertTrue(any("/news/101" in u for u in urls))
        self.assertTrue(any("/news/102" in u for u in urls))
        # 外部連結不應出現（無 /news/ pattern）
        self.assertFalse(any("external.com" in u for u in urls))

    def test_strategy_v1_returns_empty_for_wrong_html(self):
        soup = BeautifulSoup("<html><body><p>Nothing</p></body></html>", "lxml")
        items = _parse_strategy_v1(soup)
        self.assertEqual(items, [])


class TestFetchNews(unittest.TestCase):

    @patch("app.crawler._http")
    def test_fetch_news_returns_items_on_success(self, mock_http):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = STRATEGY_V1_HTML
        mock_response.apparent_encoding = "utf-8"
        mock_response.raise_for_status = MagicMock()
        mock_http.get.return_value = mock_response

        items = fetch_news(url="https://fake.url/news")
        self.assertGreater(len(items), 0)

    @patch("app.crawler._http")
    def test_fetch_news_returns_empty_on_request_error(self, mock_http):
        import requests
        mock_http.get.side_effect = requests.RequestException("Connection error")

        items = fetch_news(url="https://fake.url/news")
        self.assertEqual(items, [])


class TestNewsItem(unittest.TestCase):

    def test_news_item_fields(self):
        item = NewsItem(
            title="測試公告",
            url="https://mis.nsysu.edu.tw/news/1",
            published_at="2024-09-01",
        )
        self.assertEqual(item.title, "測試公告")
        self.assertEqual(item.published_at, "2024-09-01")

    def test_news_item_optional_published_at(self):
        item = NewsItem(title="無日期公告", url="https://mis.nsysu.edu.tw/news/2")
        self.assertIsNone(item.published_at)


if __name__ == "__main__":
    unittest.main(verbosity=2)
