"""
tests/test_messages.py — LINE 訊息建構器單元測試

測試內容：
  - 歡迎訊息結構正確性
  - Carousel Template 欄位數量
  - Flex Message 結構
  - Quick Reply 選項數量
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBuildWelcomeMessage(unittest.TestCase):

    def test_returns_list(self):
        from app.messages import build_welcome_message
        result = build_welcome_message("測試用戶")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_contains_display_name(self):
        from app.messages import build_welcome_message
        from linebot.v3.messaging import TextMessage
        msgs = build_welcome_message("小明")
        text_msgs = [m for m in msgs if isinstance(m, TextMessage)]
        self.assertTrue(any("小明" in m.text for m in text_msgs))

    def test_has_quick_reply(self):
        from app.messages import build_welcome_message
        from linebot.v3.messaging import TextMessage
        msgs = build_welcome_message()
        text_msgs = [m for m in msgs if isinstance(m, TextMessage)]
        self.assertTrue(any(m.quick_reply is not None for m in text_msgs))


class TestBuildCourseCarousel(unittest.TestCase):

    def test_returns_template_message(self):
        from app.messages import build_course_carousel
        from linebot.v3.messaging import TemplateMessage
        msg = build_course_carousel()
        self.assertIsInstance(msg, TemplateMessage)

    def test_has_four_columns(self):
        from app.messages import build_course_carousel
        msg = build_course_carousel()
        columns = msg.template.columns
        self.assertEqual(len(columns), 4)

    def test_column_titles(self):
        from app.messages import build_course_carousel
        msg = build_course_carousel()
        titles = [col.title for col in msg.template.columns]
        self.assertTrue(any("必修" in t for t in titles))
        self.assertTrue(any("選修" in t for t in titles))
        self.assertTrue(any("通識" in t for t in titles))
        self.assertTrue(any("雙主修" in t for t in titles))


class TestBuildCourseDetailFlex(unittest.TestCase):

    def test_required_courses(self):
        from app.messages import build_course_detail_flex
        from linebot.v3.messaging import FlexMessage
        msg = build_course_detail_flex("required")
        self.assertIsInstance(msg, FlexMessage)
        self.assertIn("必修", msg.alt_text)

    def test_elective_courses(self):
        from app.messages import build_course_detail_flex
        from linebot.v3.messaging import FlexMessage
        msg = build_course_detail_flex("elective")
        self.assertIsInstance(msg, FlexMessage)

    def test_general_courses(self):
        from app.messages import build_course_detail_flex
        from linebot.v3.messaging import FlexMessage
        msg = build_course_detail_flex("general")
        self.assertIsInstance(msg, FlexMessage)

    def test_double_major(self):
        from app.messages import build_course_detail_flex
        from linebot.v3.messaging import FlexMessage
        msg = build_course_detail_flex("double_major")
        self.assertIsInstance(msg, FlexMessage)

    def test_unknown_type_returns_error_flex(self):
        from app.messages import build_course_detail_flex
        from linebot.v3.messaging import FlexMessage
        msg = build_course_detail_flex("nonexistent_type")
        self.assertIsInstance(msg, FlexMessage)
        self.assertIn("找不到", msg.alt_text)


class TestBuildAnnouncementFlex(unittest.TestCase):

    def test_basic_announcement(self):
        from app.messages import build_announcement_flex
        from linebot.v3.messaging import FlexMessage
        msg = build_announcement_flex(
            title="測試公告標題",
            url="https://mis.nsysu.edu.tw/news/1",
            published_at="2024-09-01",
        )
        self.assertIsInstance(msg, FlexMessage)
        self.assertIn("測試公告標題", msg.alt_text)

    def test_announcement_without_date(self):
        from app.messages import build_announcement_flex
        from linebot.v3.messaging import FlexMessage
        msg = build_announcement_flex(
            title="無日期公告",
            url="https://mis.nsysu.edu.tw/news/2",
        )
        self.assertIsInstance(msg, FlexMessage)

    def test_multi_announcement_flex(self):
        from app.messages import build_multi_announcement_flex
        from linebot.v3.messaging import FlexMessage
        anns = [
            {"title": f"公告 {i}", "url": f"https://mis.nsysu.edu.tw/news/{i}", "published_at": None}
            for i in range(3)
        ]
        msg = build_multi_announcement_flex(anns)
        self.assertIsInstance(msg, FlexMessage)


class TestBuildQuickReplyMenu(unittest.TestCase):

    def test_has_items(self):
        from app.messages import build_quick_reply_menu
        from linebot.v3.messaging import QuickReply
        qr = build_quick_reply_menu()
        self.assertIsInstance(qr, QuickReply)
        self.assertGreater(len(qr.items), 0)

    def test_has_course_option(self):
        from app.messages import build_quick_reply_menu
        qr = build_quick_reply_menu()
        labels = [item.action.label for item in qr.items]
        self.assertTrue(any("選課" in label for label in labels))


if __name__ == "__main__":
    unittest.main(verbosity=2)
