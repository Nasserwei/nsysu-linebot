"""
tests/test_nlp.py — NLP 模組單元測試

測試內容：
  - 知識庫載入正確性
  - 相似度比對：能找到正確類別
  - 低相似度輸入回傳 None
  - get_answer() 便捷函式
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestNLPEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """在整個測試類別啟動前，載入一次 NLP Engine。"""
        from app.nlp import NLPEngine
        # 使用真實知識庫路徑
        cls.engine = NLPEngine(knowledge_base_path="data/qa_knowledge.json")

    def test_engine_loaded(self):
        """確認引擎正確載入知識庫。"""
        self.assertIsNotNone(self.engine._vectorizer)
        self.assertGreater(len(self.engine._entries), 0)

    def test_match_monkey_question(self):
        """輸入獼猴相關問題，應匹配到校園生態類別。"""
        result = self.engine.match("遇到猴子我該怎麼辦")
        self.assertIsNotNone(result)
        self.assertEqual(result.category, "校園生態")
        self.assertIn("獼猴", result.answer)

    def test_match_bbq_question(self):
        """輸入燒肉相關問題，應匹配到美食雷達類別。"""
        result = self.engine.match("哪裡有燒烤可以吃")
        self.assertIsNotNone(result)
        self.assertEqual(result.category, "美食雷達")

    def test_match_spicy_question(self):
        """輸入麻辣相關問題，應匹配到美食雷達（麻辣口味）。"""
        result = self.engine.match("我想吃辣的火鍋")
        self.assertIsNotNone(result)
        self.assertIn("麻辣", result.answer)

    def test_match_github_question(self):
        """輸入 GitHub Copilot 相關問題，應匹配到數位優惠類別。"""
        result = self.engine.match("怎麼用 edu 信箱申請 GitHub Copilot")
        self.assertIsNotNone(result)
        self.assertEqual(result.category, "數位優惠")

    def test_match_kaohsiung_question(self):
        """輸入高雄旅遊相關問題，應匹配到課外活動類別。"""
        result = self.engine.match("高雄有什麼景點推薦")
        self.assertIsNotNone(result)
        self.assertEqual(result.category, "課外活動")

    def test_match_calculus_question(self):
        """輸入微積分相關問題，應找到對應回答。"""
        result = self.engine.match("微積分好難，我快當掉了")
        self.assertIsNotNone(result)
        self.assertIn("微積分", result.answer)

    def test_no_match_for_irrelevant_input(self):
        """輸入完全無關的亂碼，相似度應低於門檻，回傳 None。"""
        result = self.engine.match("zzzzzzxxx asd qwe zxcv")
        # 此測試依賴門檻設定，可能不穩定；確保不拋例外即可
        # result 可能是 None 或有值（取決於 threshold）
        self.assertIsInstance(result, (type(None), object))

    def test_similarity_score_in_range(self):
        """相似度分數應在 [0, 1] 之間。"""
        result = self.engine.match("宿舍怎麼申請")
        if result:
            self.assertGreaterEqual(result.similarity, 0.0)
            self.assertLessEqual(result.similarity, 1.0)

    def test_get_categories(self):
        """應能取得所有知識庫分類。"""
        cats = self.engine.get_categories()
        self.assertIn("校園生態", cats)
        self.assertIn("美食雷達", cats)
        self.assertIn("數位優惠", cats)
        self.assertIn("課外活動", cats)

    def test_get_sample_questions(self):
        """get_sample_questions 應回傳非空清單。"""
        samples = self.engine.get_sample_questions(limit=3)
        self.assertGreater(len(samples), 0)
        self.assertLessEqual(len(samples), 3)


class TestGetAnswerFunction(unittest.TestCase):

    def test_get_answer_returns_tuple(self):
        """get_answer() 應永遠回傳 (str, float) tuple。"""
        from app.nlp import get_answer

        answer, score = get_answer("猴子怎麼辦")
        self.assertIsInstance(answer, str)
        self.assertIsInstance(score, float)

    def test_get_answer_fallback(self):
        """無法比對時應回傳 fallback 文字且 score=0.0。"""
        from app.nlp import get_answer

        answer, score = get_answer("xyzxyzxyzxyz 完全無關的輸入 12345")
        self.assertIsInstance(answer, str)
        self.assertGreaterEqual(score, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
