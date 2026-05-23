"""
main.py — FastAPI 應用主程式 / LINE Webhook 入口

端點：
  POST /webhook        : LINE Webhook（簽章驗證 + 事件路由）
  GET  /health         : 健康檢查
  POST /admin/crawl    : 手動觸發爬蟲（開發除錯用）
  GET  /admin/stats    : 查看 DB 統計（用戶數、公告數等）
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    FollowEvent,
    MessageEvent,
    PostbackEvent,
    UnfollowEvent,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    Announcement,
    User,
    get_db,
    init_db,
)
from app.line_handler import (
    handle_follow,
    handle_message,
    handle_postback,
    handle_unfollow,
)
from app.scheduler import start_scheduler, stop_scheduler, trigger_now

# ── 日誌設定 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── LINE Webhook Parser ────────────────────────────────────────
parser = WebhookParser(settings.line_channel_secret)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI Lifespan（取代已棄用的 on_event）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────
    logger.info("🚀 中山資管新生小幫手 啟動中...")
    os.makedirs("data", exist_ok=True)
    init_db()
    logger.info("✅ 資料庫初始化完成")
    start_scheduler()
    yield
    # ── Shutdown ──────────────────────────────────────────────
    stop_scheduler()
    logger.info("👋 服務已優雅關閉")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app = FastAPI(
    title="中山大學資管系新生專屬小幫手",
    description="LINE Bot × 爬蟲 × NLP 智慧客服",
    version="1.0.0",
    lifespan=lifespan,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LINE Webhook 端點
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    x_line_signature: str = Header(alias="X-Line-Signature"),
    db: Session = Depends(get_db),
):
    """
    LINE Webhook 主入口。
    1. 驗證簽章（防偽造請求）
    2. 解析事件並分派給對應 handler
    """
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    try:
        events = parser.parse(body_text, x_line_signature)
    except InvalidSignatureError:
        logger.warning("LINE 簽章驗證失敗，疑似偽造請求。")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature",
        )

    for event in events:
        try:
            if isinstance(event, FollowEvent):
                handle_follow(event, db)
            elif isinstance(event, UnfollowEvent):
                handle_unfollow(event, db)
            elif isinstance(event, MessageEvent):
                handle_message(event, db)
            elif isinstance(event, PostbackEvent):
                handle_postback(event, db)
            else:
                logger.debug("未處理的事件類型：%s", type(event).__name__)
        except Exception as exc:
            # 單一事件失敗不影響其他事件或 HTTP 回應
            logger.exception("事件處理失敗（%s）：%s", type(event).__name__, exc)

    return {"status": "ok"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 健康檢查
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/health", tags=["System"])
async def health_check():
    """服務存活確認，適合 GCP / Render / Railway 等平台的 health check。"""
    return {
        "status": "healthy",
        "service": "NSYSU MIS Freshman LINE Bot",
        "version": "1.0.0",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 管理員端點（開發除錯用，正式環境請加上 API Key 保護）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/admin/crawl", tags=["Admin"])
async def manual_crawl(db: Session = Depends(get_db)):
    """手動觸發一次爬蟲並廣播（可用於測試）。"""
    from app.crawler import crawl_and_save
    from app.line_handler import broadcast_new_announcements

    total, new_count = crawl_and_save(db)
    pushed = 0
    if new_count > 0:
        pushed = broadcast_new_announcements(db)

    return {
        "total_fetched": total,
        "new_announcements": new_count,
        "pushed_to_users": pushed,
    }


@app.get("/admin/stats", tags=["Admin"])
async def get_stats(db: Session = Depends(get_db)):
    """回傳資料庫統計資訊。"""
    total_announcements = db.query(Announcement).count()
    pushed_announcements = db.query(Announcement).filter(
        Announcement.is_pushed == True  # noqa: E712
    ).count()
    active_users = db.query(User).filter(User.is_active == True).count()  # noqa: E712
    total_users = db.query(User).count()

    return {
        "announcements": {
            "total": total_announcements,
            "pushed": pushed_announcements,
            "pending": total_announcements - pushed_announcements,
        },
        "users": {
            "total": total_users,
            "active": active_users,
            "blocked": total_users - active_users,
        },
    }


@app.post("/admin/reload-nlp", tags=["Admin"])
async def reload_nlp():
    """重新載入 NLP 知識庫（無需重啟服務）。"""
    from app.nlp import nlp_engine

    nlp_engine.reload()
    return {"status": "NLP 知識庫重新載入成功"}
