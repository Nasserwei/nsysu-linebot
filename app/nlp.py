"""
nlp.py — NLP 相似度比對模組

技術架構：
  1. 使用 jieba 進行中文斷詞
  2. 使用 TF-IDF 向量化問題語料
  3. 使用 cosine similarity 計算使用者輸入與知識庫的相似度
  4. 回傳最相似問題對應的答案

設計原則：
  - 在啟動時一次性載入並向量化知識庫（避免每次請求重算）
  - 支援熱重載知識庫（reload() 方法）
  - 低於門檻值時回傳引導訊息
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_PATH = os.path.join("data", "qa_knowledge.json")

# 停用詞（常見無意義中文詞）
STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一個", "上", "也", "很", "到", "說", "要", "去", "你", "會",
    "着", "沒有", "看", "好", "自己", "這", "那", "它", "他", "她", "們",
    "嗎", "呢", "啊", "哦", "哈", "嗯", "嘿", "噢",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 資料結構
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class QAEntry:
    category: str
    questions: list[str]
    answer: str
    # 展開後每個問題對應的 index（供向量化用）
    flat_questions: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    matched_question: str
    answer: str
    similarity: float
    category: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NLP 引擎（單例模式）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class NLPEngine:
    """
    Q&A 相似度比對引擎。
    啟動時自動載入知識庫並建立 TF-IDF 索引。
    """

    def __init__(self, knowledge_base_path: str = KNOWLEDGE_BASE_PATH):
        self._path = knowledge_base_path
        self._entries: list[QAEntry] = []
        # 展開後的問句平鋪列表，供向量化
        self._flat_questions: list[str] = []
        # 每個平鋪問句對應的 entry index
        self._entry_idx_map: list[int] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._tfidf_matrix = None

        self._load_and_build()

    # ── 內部工具 ──────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> str:
        """斷詞並移除停用詞，回傳空格分隔的 token 字串。"""
        tokens = jieba.cut(text, cut_all=False)
        filtered = [t for t in tokens if t.strip() and t not in STOP_WORDS]
        return " ".join(filtered)

    def _load_and_build(self) -> None:
        """載入 JSON 知識庫，建立 TF-IDF 向量索引。"""
        try:
            with open(self._path, encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
        except FileNotFoundError:
            logger.error("知識庫檔案不存在：%s", self._path)
            return
        except json.JSONDecodeError as exc:
            logger.error("知識庫 JSON 格式錯誤：%s", exc)
            return

        self._entries = []
        self._flat_questions = []
        self._entry_idx_map = []

        for i, item in enumerate(raw):
            entry = QAEntry(
                category=item.get("category", "其他"),
                questions=item.get("questions", []),
                answer=item.get("answer", "（無回答）"),
            )
            self._entries.append(entry)
            for q in entry.questions:
                self._flat_questions.append(self._tokenize(q))
                self._entry_idx_map.append(i)

        if not self._flat_questions:
            logger.warning("知識庫為空，NLP 引擎無法正常運作。")
            return

        # 建立 TF-IDF 向量器
        self._vectorizer = TfidfVectorizer(
            analyzer="word",
            token_pattern=r"(?u)\b\w+\b",  # 支援中文 token
            ngram_range=(1, 2),              # unigram + bigram
            max_features=10_000,
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(self._flat_questions)
        logger.info(
            "NLP 引擎就緒：%d 個條目，%d 個問句，%d 個特徵",
            len(self._entries),
            len(self._flat_questions),
            self._tfidf_matrix.shape[1],
        )

    # ── 公開 API ──────────────────────────────────────────────

    def reload(self) -> None:
        """重新載入知識庫（支援不重啟服務的熱更新）。"""
        logger.info("重新載入 NLP 知識庫...")
        self._load_and_build()

    def match(self, user_input: str) -> Optional[MatchResult]:
        """
        找出與使用者輸入最相似的知識庫問題並回傳答案。

        Args:
            user_input: 使用者輸入文字

        Returns:
            MatchResult 若找到且相似度超過門檻，否則 None
        """
        if self._vectorizer is None or self._tfidf_matrix is None:
            logger.warning("NLP 引擎未初始化，無法比對。")
            return None

        tokenized_input = self._tokenize(user_input)
        if not tokenized_input.strip():
            return None

        try:
            input_vec = self._vectorizer.transform([tokenized_input])
            scores = cosine_similarity(input_vec, self._tfidf_matrix).flatten()
        except Exception as exc:
            logger.error("向量化或相似度計算失敗：%s", exc)
            return None

        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])

        logger.debug(
            "輸入：%r → 最佳匹配分數 %.4f（問句：%r）",
            user_input[:30],
            best_score,
            self._flat_questions[best_idx][:40],
        )

        if best_score < settings.nlp_similarity_threshold:
            logger.info("相似度 %.4f 低於門檻 %.4f，不回覆。", best_score, settings.nlp_similarity_threshold)
            return None

        entry_idx = self._entry_idx_map[best_idx]
        entry = self._entries[entry_idx]
        # 找回原始（未斷詞）的問句
        original_q_idx = sum(
            len(e.questions) for e in self._entries[:entry_idx]
        )
        flat_offset = best_idx - sum(
            len(self._entries[j].questions) for j in range(entry_idx)
        )
        matched_q = entry.questions[flat_offset] if flat_offset < len(entry.questions) else "（未知問句）"

        return MatchResult(
            matched_question=matched_q,
            answer=entry.answer,
            similarity=best_score,
            category=entry.category,
        )

    def get_categories(self) -> list[str]:
        """回傳所有知識庫分類名稱（去重）。"""
        seen: set[str] = set()
        cats: list[str] = []
        for e in self._entries:
            if e.category not in seen:
                seen.add(e.category)
                cats.append(e.category)
        return cats

    def get_sample_questions(self, category: str | None = None, limit: int = 5) -> list[str]:
        """
        回傳示範問句（用於 LIFF 或 quick reply）。
        若指定 category 則只回傳該分類的問句。
        """
        samples: list[str] = []
        for entry in self._entries:
            if category and entry.category != category:
                continue
            samples.extend(entry.questions[:2])  # 每個條目取前 2 個示範問句
            if len(samples) >= limit:
                break
        return samples[:limit]


# ── 全域單例（應用啟動時初始化一次）────────────────────────────
nlp_engine = NLPEngine()


# ── 對外便捷函式 ───────────────────────────────────────────────

def get_answer(user_input: str) -> tuple[str, float]:
    """
    供 line_handler 直接呼叫的函式。

    Returns:
        (answer_text, similarity_score)
        若無匹配則回傳引導訊息與 0.0
    """
    result = nlp_engine.match(user_input)
    if result is None:
        fallback = (
            "🤔 抱歉，我還不太確定你在問什麼～\n\n"
            "你可以試試輸入以下關鍵字：\n"
            "🐒 猴子  🍖 燒肉  🌶️ 麻辣  💻 GitHub\n"
            "🎤 講座  🌆 高雄  🏠 宿舍  📐 微積分\n\n"
            "或點選下方選單查詢「選課資訊」📚"
        )
        return fallback, 0.0

    return result.answer, result.similarity
