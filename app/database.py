"""
database.py — SQLAlchemy 資料庫模型與連線管理

資料表：
  - announcements : 爬取的公告（去重用）
  - users          : 加入 Bot 的 LINE 用戶（廣播用）
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# ── 確保 data/ 目錄存在 ────────────────────────────────────────
os.makedirs("data", exist_ok=True)

# ── 引擎與 Session 工廠 ────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite 需要此設定
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── ORM Base ──────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 資料表模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Announcement(Base):
    """系所公告，url 作為唯一鍵避免重複推送。"""

    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(512), nullable=False)
    url = Column(String(1024), unique=True, nullable=False, index=True)
    published_at = Column(String(64), nullable=True)          # 原始日期字串
    is_pushed = Column(Boolean, default=False, nullable=False) # 是否已廣播
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Announcement id={self.id} title={self.title[:30]!r}>"


class User(Base):
    """加入 Bot 的 LINE 使用者，follow 事件寫入，unfollow 事件標記刪除。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    line_user_id = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User line_id={self.line_user_id} active={self.is_active}>"


class QAFeedback(Base):
    """記錄使用者問了什麼、系統回了什麼（可供後續 Fine-tuning）。"""

    __tablename__ = "qa_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    line_user_id = Column(String(64), nullable=False, index=True)
    user_question = Column(Text, nullable=False)
    matched_question = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    similarity_score = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default=func.now())


# ── 初始化資料表 ───────────────────────────────────────────────
def init_db() -> None:
    """建立所有資料表（若不存在）。"""
    Base.metadata.create_all(bind=engine)


# ── FastAPI dependency ─────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends 用的 Session 產生器。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRUD 工具函式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def upsert_announcement(db: Session, title: str, url: str, published_at: str | None) -> tuple[Announcement, bool]:
    """
    新增公告；若 url 已存在則略過。
    回傳 (Announcement 物件, is_new)
    """
    existing = db.query(Announcement).filter(Announcement.url == url).first()
    if existing:
        return existing, False

    ann = Announcement(title=title, url=url, published_at=published_at)
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return ann, True


def get_unpushed_announcements(db: Session) -> list[Announcement]:
    """取得尚未廣播的公告清單。"""
    return db.query(Announcement).filter(Announcement.is_pushed == False).all()  # noqa: E712


def mark_announcement_pushed(db: Session, ann_id: int) -> None:
    """將公告標記為已廣播。"""
    db.query(Announcement).filter(Announcement.id == ann_id).update(
        {"is_pushed": True}
    )
    db.commit()


def upsert_user(db: Session, line_user_id: str, display_name: str | None = None) -> User:
    """新增或更新使用者記錄。"""
    user = db.query(User).filter(User.line_user_id == line_user_id).first()
    if user:
        user.is_active = True
        if display_name:
            user.display_name = display_name
        db.commit()
        db.refresh(user)
        return user

    user = User(line_user_id=line_user_id, display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, line_user_id: str) -> None:
    """使用者封鎖或退出時，標記為非作用中。"""
    db.query(User).filter(User.line_user_id == line_user_id).update(
        {"is_active": False}
    )
    db.commit()


def get_active_user_ids(db: Session) -> list[str]:
    """取得所有作用中使用者的 LINE user_id 清單（廣播用）。"""
    rows = db.query(User.line_user_id).filter(User.is_active == True).all()  # noqa: E712
    return [r[0] for r in rows]


def save_qa_feedback(
    db: Session,
    line_user_id: str,
    user_question: str,
    matched_question: str | None,
    answer: str | None,
    similarity_score: float | None,
) -> None:
    """儲存一筆 Q&A 互動記錄。"""
    fb = QAFeedback(
        line_user_id=line_user_id,
        user_question=user_question,
        matched_question=matched_question,
        answer=answer,
        similarity_score=str(round(similarity_score, 4)) if similarity_score else None,
    )
    db.add(fb)
    db.commit()
