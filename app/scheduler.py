"""
scheduler.py — APScheduler 定時爬蟲排程

在 FastAPI 啟動時（lifespan）自動啟動定時任務：
  1. 每 N 分鐘爬取系所公告（N 由 .env CRAWLER_INTERVAL_MINUTES 設定）
  2. 爬完後廣播新公告給所有作用中用戶

設計重點：
  - 使用 BackgroundScheduler（獨立執行緒，不阻塞 ASGI 主執行緒）
  - 每次任務建立獨立 DB Session，用完即關閉
  - 捕獲所有例外確保排程不因單次失敗而停止
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)

# 全域排程器實例
_scheduler = BackgroundScheduler(timezone="Asia/Taipei")


def _crawl_and_broadcast_job() -> None:
    """
    定時任務主體：
      1. 執行爬蟲，將新公告存入 DB
      2. 廣播未推送的公告
    """
    db = SessionLocal()
    try:
        # ── Step 1：爬蟲 ──────────────────────────────────────
        from app.crawler import crawl_and_save

        total, new_count = crawl_and_save(db)
        logger.info("[排程] 爬蟲完成：共 %d 筆，新增 %d 筆", total, new_count)

        # ── Step 2：廣播 ──────────────────────────────────────
        if new_count > 0:
            from app.line_handler import broadcast_new_announcements

            pushed = broadcast_new_announcements(db)
            logger.info("[排程] 廣播完成：推播 %d 則公告", pushed)
        else:
            logger.debug("[排程] 無新公告，跳過廣播。")

    except Exception as exc:
        logger.exception("[排程] 任務執行失敗：%s", exc)
    finally:
        db.close()


def start_scheduler() -> None:
    """啟動排程器（在 FastAPI lifespan 的 startup 階段呼叫）。"""
    if _scheduler.running:
        logger.warning("排程器已在執行中，跳過重複啟動。")
        return

    interval_minutes = settings.crawler_interval_minutes
    _scheduler.add_job(
        func=_crawl_and_broadcast_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="crawl_and_broadcast",
        name="系所公告爬蟲與廣播",
        replace_existing=True,
        misfire_grace_time=60,  # 若錯過執行，60 秒內仍可補跑
    )
    _scheduler.start()
    logger.info(
        "排程器已啟動：每 %d 分鐘執行一次爬蟲與廣播", interval_minutes
    )


def stop_scheduler() -> None:
    """停止排程器（在 FastAPI lifespan 的 shutdown 階段呼叫）。"""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("排程器已停止。")


def trigger_now() -> None:
    """手動立即觸發一次爬蟲任務（供除錯或 API 端點呼叫）。"""
    logger.info("手動觸發爬蟲任務...")
    _crawl_and_broadcast_job()
