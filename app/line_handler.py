"""
line_handler.py — LINE Webhook 事件路由與處理

處理的事件類型：
  - FollowEvent    : 用戶加入（存入 DB + 歡迎訊息）
  - UnfollowEvent  : 用戶封鎖（標記 DB）
  - MessageEvent   : 文字訊息（NLP Q&A）
  - PostbackEvent  : 互動按鈕回傳（選課 Postback）
"""
from __future__ import annotations

import logging

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    FollowEvent,
    MessageEvent,
    PostbackEvent,
    TextMessageContent,
    UnfollowEvent,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    deactivate_user,
    get_active_user_ids,
    get_unpushed_announcements,
    mark_announcement_pushed,
    save_qa_feedback,
    upsert_user,
)
from app.messages import (
    build_announcement_flex,
    build_course_carousel,
    build_course_detail_flex,
    build_multi_announcement_flex,
    build_quick_reply_menu,
    build_welcome_message,
)
from app.nlp import get_answer

logger = logging.getLogger(__name__)

# ── LINE SDK 設定 ─────────────────────────────────────────────
_configuration = Configuration(access_token=settings.line_channel_access_token)


def _get_line_api() -> MessagingApi:
    """建立 LINE Messaging API 客戶端。"""
    return MessagingApi(ApiClient(_configuration))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 事件處理器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def handle_follow(event: FollowEvent, db: Session) -> None:
    """用戶加入 Bot 時：存 DB + 回傳歡迎訊息。"""
    user_id = event.source.user_id
    display_name = _fetch_display_name(user_id)
    upsert_user(db, line_user_id=user_id, display_name=display_name)

    api = _get_line_api()
    messages = build_welcome_message(display_name=display_name or "新同學")

    api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=messages,
        )
    )
    logger.info("新用戶加入：%s (%s)", user_id, display_name)


def handle_unfollow(event: UnfollowEvent, db: Session) -> None:
    """用戶封鎖時：標記為非作用中。"""
    user_id = event.source.user_id
    deactivate_user(db, line_user_id=user_id)
    logger.info("用戶封鎖：%s", user_id)


def handle_message(event: MessageEvent, db: Session) -> None:
    """處理文字訊息：路由至特定功能或 NLP Q&A。"""
    if not isinstance(event.message, TextMessageContent):
        return

    user_id = event.source.user_id
    text = event.message.text.strip()

    logger.info("收到訊息：user=%s text=%r", user_id, text[:50])

    # ── 關鍵字路由 ────────────────────────────────────────────
    reply_messages = _route_text(text, user_id, db)

    api = _get_line_api()
    api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=reply_messages,
        )
    )


def handle_postback(event: PostbackEvent, db: Session) -> None:
    """處理按鈕 Postback：解析 action 並回傳對應 Flex Message。"""
    data = event.postback.data  # e.g. "action=course&type=required"
    params = dict(item.split("=") for item in data.split("&") if "=" in item)

    action = params.get("action", "")
    api = _get_line_api()

    if action == "course":
        course_type = params.get("type", "required")
        flex_msg = build_course_detail_flex(course_type)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[flex_msg],
            )
        )
        logger.info("Postback course 類型：%s", course_type)
    else:
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="❓ 未知的操作，請重試。")],
            )
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 廣播公告（排程器呼叫）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def broadcast_new_announcements(db: Session) -> int:
    """
    找出未推送公告，廣播給所有作用中用戶。
    回傳廣播筆數。
    """
    if not settings.enable_broadcast:
        return 0

    announcements = get_unpushed_announcements(db)
    if not announcements:
        return 0

    user_ids = get_active_user_ids(db)
    if not user_ids:
        logger.info("無作用中用戶，跳過廣播。")
        # 仍然標記為已推送，避免下次重試
        for ann in announcements:
            mark_announcement_pushed(db, ann.id)
        return 0

    api = _get_line_api()
    pushed_count = 0

    for ann in announcements:
        flex_msg = build_announcement_flex(
            title=ann.title,
            url=ann.url,
            published_at=ann.published_at,
        )
        # LINE Multicast API：一次最多 500 人
        for i in range(0, len(user_ids), 500):
            chunk = user_ids[i : i + 500]
            try:
                from linebot.v3.messaging import MulticastMessage, MulticastRequest
                api.multicast(
                    MulticastRequest(
                        to=chunk,
                        messages=[flex_msg],
                    )
                )
            except Exception as exc:
                logger.error("廣播失敗（公告 id=%d）：%s", ann.id, exc)
                continue

        mark_announcement_pushed(db, ann.id)
        pushed_count += 1
        logger.info("廣播完成：%s（推送給 %d 人）", ann.title[:40], len(user_ids))

    return pushed_count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 內部輔助函式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 關鍵字路由表（關鍵字 → 處理函式名稱）
_KEYWORD_ROUTES: dict[str, str] = {
    "選課資訊": "_handle_course_menu",
    "選課": "_handle_course_menu",
    "課程": "_handle_course_menu",
    "最新公告": "_handle_latest_announcements",
    "公告": "_handle_latest_announcements",
    "系所公告": "_handle_latest_announcements",
    "說明": "_handle_help",
    "幫助": "_handle_help",
    "help": "_handle_help",
    "選單": "_handle_help",
    "你好": "_handle_greeting",
    "hi": "_handle_greeting",
    "hello": "_handle_greeting",
    "嗨": "_handle_greeting",
}


def _route_text(text: str, user_id: str, db: Session) -> list:
    """
    根據關鍵字判斷路由，否則交給 NLP Q&A。
    回傳 LINE Message 物件清單。
    """
    lower = text.lower()

    # 精確關鍵字路由
    for keyword, handler_name in _KEYWORD_ROUTES.items():
        if keyword.lower() in lower:
            handler = globals().get(handler_name)
            if handler:
                return handler(db=db)

    # NLP Q&A
    return _handle_nlp(text=text, user_id=user_id, db=db)


def _handle_course_menu(db: Session = None, **_) -> list:
    """回傳選課 Carousel。"""
    return [build_course_carousel()]


def _handle_latest_announcements(db: Session, **_) -> list:
    """從 DB 取最新 5 筆公告（不論是否推送過）回傳 Flex。"""
    from app.database import Announcement

    with db.bind.connect() as conn:
        announcements = (
            db.query(Announcement)
            .order_by(Announcement.created_at.desc())
            .limit(5)
            .all()
        )

    if not announcements:
        return [
            TextMessage(
                text="目前資料庫尚無公告記錄。\n請稍後再試，或前往系網查看：\nhttps://mis.nsysu.edu.tw/news",
                quick_reply=build_quick_reply_menu(),
            )
        ]

    ann_dicts = [
        {"title": a.title, "url": a.url, "published_at": a.published_at}
        for a in announcements
    ]
    return [build_multi_announcement_flex(ann_dicts)]


def _handle_help(db: Session = None, **_) -> list:
    """回傳功能說明 + Quick Reply。"""
    help_text = (
        "🤖 中山資管新生小幫手 — 功能說明\n\n"
        "你可以問我：\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📚 選課相關\n"
        "  → 輸入「選課資訊」\n\n"
        "📢 最新公告\n"
        "  → 輸入「最新公告」\n\n"
        "🐒 校園生態\n"
        "  → 輸入「猴子怎麼辦」\n\n"
        "🍖 美食推薦\n"
        "  → 輸入「燒肉推薦」或「麻辣推薦」\n\n"
        "💻 數位優惠\n"
        "  → 輸入「GitHub Copilot 怎麼申請」\n\n"
        "🌆 高雄旅遊\n"
        "  → 輸入「高雄好玩的地方」\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "或直接輸入任何問題，我會盡力回答！"
    )
    return [TextMessage(text=help_text, quick_reply=build_quick_reply_menu())]


def _handle_greeting(db: Session = None, **_) -> list:
    """簡短打招呼回應。"""
    return [
        TextMessage(
            text="嗨嗨！👋 我是中山資管新生小幫手～\n有什麼需要幫忙的嗎？\n\n點選下方選單快速查詢！",
            quick_reply=build_quick_reply_menu(),
        )
    ]


def _handle_nlp(text: str, user_id: str, db: Session) -> list:
    """NLP Q&A 處理：比對知識庫並回傳答案。"""
    answer, score = get_answer(text)

    # 儲存互動紀錄
    save_qa_feedback(
        db=db,
        line_user_id=user_id,
        user_question=text,
        matched_question=None,  # 可由 nlp.py 的 MatchResult 取得，此處簡化
        answer=answer,
        similarity_score=score,
    )

    # 若相似度足夠，附上 quick reply 讓用戶繼續探索
    if score > 0.0:
        return [TextMessage(text=answer, quick_reply=build_quick_reply_menu())]
    else:
        return [TextMessage(text=answer)]


def _fetch_display_name(user_id: str) -> str | None:
    """透過 LINE API 取得用戶顯示名稱。"""
    try:
        api = _get_line_api()
        profile = api.get_profile(user_id)
        return profile.display_name
    except Exception as exc:
        logger.warning("取得用戶名稱失敗（%s）：%s", user_id, exc)
        return None
