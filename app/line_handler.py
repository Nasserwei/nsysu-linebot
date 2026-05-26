"""
line_handler.py — LINE Webhook 事件路由與處理

處理的事件類型：
  - FollowEvent    : 用戶加入（存入 DB + 歡迎訊息）
  - UnfollowEvent  : 用戶封鎖（標記 DB）
  - MessageEvent   : 文字訊息（NLP Q&A）
  - PostbackEvent  : 互動按鈕回傳（選課 / GPA Postback）
"""
from __future__ import annotations

import logging
import re

import httpx
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
    build_gpa_flex,
    build_multi_announcement_flex,
    build_quick_reply_menu,
    build_school_links_flex,
    build_weather_flex,
    build_welcome_message,
)
from app.nlp import get_answer

logger = logging.getLogger(__name__)

_configuration = Configuration(access_token=settings.line_channel_access_token)


def _get_line_api() -> MessagingApi:
    return MessagingApi(ApiClient(_configuration))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 事件處理器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def handle_follow(event: FollowEvent, db: Session) -> None:
    user_id = event.source.user_id
    display_name = _fetch_display_name(user_id)
    upsert_user(db, line_user_id=user_id, display_name=display_name)
    api = _get_line_api()
    messages = build_welcome_message(display_name=display_name or "新同學")
    api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))
    logger.info("新用戶加入：%s (%s)", user_id, display_name)


def handle_unfollow(event: UnfollowEvent, db: Session) -> None:
    deactivate_user(db, line_user_id=event.source.user_id)


def handle_message(event: MessageEvent, db: Session) -> None:
    if not isinstance(event.message, TextMessageContent):
        return
    user_id = event.source.user_id
    text = event.message.text.strip()
    logger.info("收到訊息：user=%s text=%r", user_id, text[:50])
    reply_messages = _route_text(text, user_id, db)
    api = _get_line_api()
    api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=reply_messages))


def handle_postback(event: PostbackEvent, db: Session) -> None:
    data = event.postback.data
    params = dict(item.split("=") for item in data.split("&") if "=" in item)
    action = params.get("action", "")
    api = _get_line_api()

    if action == "course":
        course_type = params.get("type", "required")
        flex_msg = build_course_detail_flex(course_type)
        api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[flex_msg]))

    elif action == "gpa_calc":
        # 引導用戶輸入成績
        guide = (
            "📊 GPA 計算機使用方式：\n\n"
            "請依照以下格式輸入成績：\n"
            "GPA 科目名稱 學分 成績\n\n"
            "📌 範例（一次可輸入多科，每科一行）：\n"
            "GPA 微積分 3 85\n"
            "GPA 程式設計 3 92\n"
            "GPA 計算機概論 2 78\n\n"
            "成績對照：A+(90-100)=4.3  A(85-89)=4.0\n"
            "B+(80-84)=3.3  B(75-79)=3.0  C+(70-74)=2.3\n"
            "C(65-69)=2.0  D(60-64)=1.0  F(<60)=0"
        )
        api.reply_message(ReplyMessageRequest(reply_token=event.reply_token,
                          messages=[TextMessage(text=guide)]))
    else:
        api.reply_message(ReplyMessageRequest(reply_token=event.reply_token,
                          messages=[TextMessage(text="❓ 未知的操作，請重試。")]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 廣播公告
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def broadcast_new_announcements(db: Session) -> int:
    if not settings.enable_broadcast:
        return 0
    announcements = get_unpushed_announcements(db)
    if not announcements:
        return 0
    user_ids = get_active_user_ids(db)
    if not user_ids:
        for ann in announcements:
            mark_announcement_pushed(db, ann.id)
        return 0
    api = _get_line_api()
    pushed_count = 0
    for ann in announcements:
        flex_msg = build_announcement_flex(title=ann.title, url=ann.url, published_at=ann.published_at)
        for i in range(0, len(user_ids), 500):
            chunk = user_ids[i: i + 500]
            try:
                from linebot.v3.messaging import MulticastRequest
                api.multicast(MulticastRequest(to=chunk, messages=[flex_msg]))
            except Exception as exc:
                logger.error("廣播失敗（公告 id=%d）：%s", ann.id, exc)
                continue
        mark_announcement_pushed(db, ann.id)
        pushed_count += 1
    return pushed_count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 關鍵字路由表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_KEYWORD_ROUTES: dict[str, str] = {
    "選課資訊": "_handle_course_menu",
    "選課": "_handle_course_menu",
    "課程": "_handle_course_menu",
    "最新公告": "_handle_latest_announcements",
    "公告": "_handle_latest_announcements",
    "系所公告": "_handle_latest_announcements",
    "天氣": "_handle_weather",
    "氣溫": "_handle_weather",
    "下雨": "_handle_weather",
    "gpa": "_handle_gpa",
    "GPA": "_handle_gpa",
    "成績計算": "_handle_gpa",
    "學校首頁": "_handle_school_links",
    "常用連結": "_handle_school_links",
    "連結": "_handle_school_links",
    "官網": "_handle_school_links",
    "說明": "_handle_help",
    "幫助": "_handle_help",
    "help": "_handle_help",
    "選單": "_handle_help",
    "你好": "_handle_greeting",
    "hi": "_handle_greeting",
    "hello": "_handle_greeting",
    "嗨": "_handle_greeting",
}

_KEYWORD_EXPAND: dict[str, str] = {
    "猴子": "遇到猴子怎麼辦",
    "獼猴": "遇到獼猴怎麼辦",
    "猴": "遇到猴子怎麼辦",
    "燒肉": "附近哪裡有燒肉",
    "烤肉": "附近哪裡有燒肉",
    "bbq": "BBQ 吃到飽推薦",
    "燒烤": "附近哪裡有燒肉",
    "麻辣": "麻辣火鍋推薦",
    "辣": "麻辣火鍋推薦",
    "火鍋": "麻辣火鍋推薦",
    "github": "如何申請 GitHub Copilot",
    "copilot": "如何申請 GitHub Copilot",
    "chatgpt": "ChatGPT 學生方案",
    "gemini": "Gemini 學生方案",
    "學生優惠": "學生軟體優惠有哪些",
    "edu信箱": "edu 信箱有什麼用",
    "講座": "有什麼講座",
    "活動": "最近有什麼活動",
    "高雄": "高雄好玩的地方",
    "旅遊": "高雄旅遊景點推薦",
    "景點": "高雄好玩的地方",
    "社團": "社團推薦",
    "宿舍": "宿舍怎麼申請",
    "住宿": "宿舍怎麼申請",
    "門禁": "宿舍門禁幾點",
    "微積分": "微積分好難怎麼念",
    "calculus": "微積分好難怎麼念",
    "數學": "微積分好難怎麼念",
    "美食": "附近吃什麼推薦",
    "吃什麼": "附近吃什麼推薦",
    "餐廳": "推薦餐廳",
}

# GPA 成績輸入格式：「GPA 科目 學分 分數」
_GPA_LINE_RE = re.compile(
    r"^gpa\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 路由主函式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _route_text(text: str, user_id: str, db: Session) -> list:
    lower = text.lower().strip()
    clean = lower.strip("?？!！。，、～~! ")

    # 0. GPA 多行成績輸入偵測（優先判斷）
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if lines and _GPA_LINE_RE.match(lines[0]):
        return _handle_gpa_calculate(lines)

    # 1. 精確關鍵字路由（包含比對）
    for keyword, handler_name in _KEYWORD_ROUTES.items():
        if keyword.lower() in lower:
            handler = globals().get(handler_name)
            if handler:
                return handler(db=db)

    # 2. 短詞展開（包含比對，只要訊息中出現關鍵字就展開）
    expanded_text = text
    for keyword, full_question in _KEYWORD_EXPAND.items():
        if keyword in clean:
            expanded_text = full_question
            break

    # 3. NLP Q&A
    return _handle_nlp(text=expanded_text, user_id=user_id, db=db)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 功能處理器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _handle_course_menu(db: Session = None, **_) -> list:
    return [build_course_carousel()]


def _handle_latest_announcements(db: Session, **_) -> list:
    from app.database import Announcement
    announcements = (
        db.query(Announcement)
        .order_by(Announcement.created_at.desc())
        .limit(5)
        .all()
    )
    if not announcements:
        return [TextMessage(
            text="目前資料庫尚無公告記錄。\n請稍後再試，或前往系網查看：\nhttps://mis.nsysu.edu.tw/news",
            quick_reply=build_quick_reply_menu(),
        )]
    ann_dicts = [{"title": a.title, "url": a.url, "published_at": a.published_at} for a in announcements]
    return [build_multi_announcement_flex(ann_dicts)]


def _handle_weather(db: Session = None, **_) -> list:
    """抓取高雄即時天氣（中央氣象署開放 API，無需 key）。"""
    try:
        url = (
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
            "?Authorization=rdec-key-123-45678-011121314"
            "&StationName=高雄"
            "&WeatherElement=Weather,AirTemperature,RelativeHumidity,WindSpeed"
        )
        resp = httpx.get(url, timeout=8)
        data = resp.json()
        records = data["records"]["Station"]
        if records:
            st = records[0]
            we = st["WeatherElement"]
            name    = st["StationName"]
            weather = we.get("Weather", "—")
            temp    = we.get("AirTemperature", "—")
            humid   = we.get("RelativeHumidity", "—")
            wind    = we.get("WindSpeed", "—")
            return [build_weather_flex(
                station=name, weather=weather,
                temp=temp, humid=humid, wind=wind,
            )]
    except Exception as exc:
        logger.warning("天氣 API 失敗：%s", exc)

    # fallback：改用氣象局觀測資料第二來源
    try:
        url2 = (
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
            "?Authorization=rdec-key-123-45678-011121314"
            "&locationName=高雄市"
        )
        resp2 = httpx.get(url2, timeout=8)
        data2 = resp2.json()
        loc = data2["records"]["location"][0]
        elements = {e["elementName"]: e["time"][0]["parameter"]["parameterName"]
                    for e in loc["weatherElement"]}
        weather = elements.get("Wx", "—")
        rain    = elements.get("PoP", "—")
        minT    = elements.get("MinT", "—")
        maxT    = elements.get("MaxT", "—")
        return [build_weather_flex(
            station="高雄市",
            weather=weather,
            temp=f"{minT}～{maxT}",
            humid=f"降雨機率 {rain}%",
            wind="—",
        )]
    except Exception as exc2:
        logger.warning("天氣 API fallback 失敗：%s", exc2)
        return [TextMessage(
            text="🌤️ 目前無法取得天氣資訊，請直接查詢：\nhttps://www.cwb.gov.tw/V8/C/W/County/County.html?CID=66",
            quick_reply=build_quick_reply_menu(),
        )]


def _handle_gpa(db: Session = None, **_) -> list:
    """回傳 GPA 計算機 Flex Message 說明卡。"""
    return [build_gpa_flex()]


def _handle_gpa_calculate(lines: list[str]) -> list:
    """
    解析多行 GPA 輸入並計算結果。
    格式：GPA 科目名稱 學分 成績分數
    """
    def score_to_grade(s: float) -> float:
        if s >= 90: return 4.3
        if s >= 85: return 4.0
        if s >= 80: return 3.3
        if s >= 75: return 3.0
        if s >= 70: return 2.3
        if s >= 65: return 2.0
        if s >= 60: return 1.0
        return 0.0

    courses = []
    errors = []
    for line in lines:
        m = _GPA_LINE_RE.match(line.strip())
        if m:
            name   = m.group(1)
            credit = float(m.group(2))
            score  = float(m.group(3))
            grade  = score_to_grade(score)
            courses.append((name, credit, score, grade))
        else:
            errors.append(line)

    if not courses:
        return [TextMessage(text="❌ 格式錯誤，請參考範例：\nGPA 微積分 3 85\nGPA 程式設計 3 92")]

    total_credits = sum(c[1] for c in courses)
    weighted_sum  = sum(c[1] * c[3] for c in courses)
    gpa = weighted_sum / total_credits if total_credits > 0 else 0.0

    lines_out = ["📊 GPA 計算結果\n"]
    lines_out.append(f"{'科目':<10} {'學分':>4} {'分數':>5} {'績點':>5}")
    lines_out.append("─" * 30)
    for name, credit, score, grade in courses:
        lines_out.append(f"{name:<10} {credit:>4.0f} {score:>5.1f} {grade:>5.1f}")
    lines_out.append("─" * 30)
    lines_out.append(f"總學分：{total_credits:.0f}")
    lines_out.append(f"✨ GPA：{gpa:.2f}")

    if gpa >= 3.8:
        lines_out.append("\n🏆 超優秀！書卷獎等你！")
    elif gpa >= 3.0:
        lines_out.append("\n👍 表現不錯，繼續保持！")
    elif gpa >= 2.0:
        lines_out.append("\n💪 還有進步空間，加油！")
    else:
        lines_out.append("\n😢 需要加把勁，善用 TA 和教授 Office Hour！")

    if errors:
        lines_out.append(f"\n⚠️ 以下行格式錯誤，已略過：\n" + "\n".join(errors))

    return [TextMessage(text="\n".join(lines_out), quick_reply=build_quick_reply_menu())]


def _handle_school_links(db: Session = None, **_) -> list:
    """回傳學校常用連結 Flex Message。"""
    return [build_school_links_flex()]


def _handle_help(db: Session = None, **_) -> list:
    help_text = (
        "🤖 中山資管新生小幫手 — 功能說明\n\n"
        "你可以問我：\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📚 選課相關 → 輸入「選課資訊」\n"
        "📢 最新公告 → 輸入「最新公告」\n"
        "🌤️ 高雄天氣 → 輸入「天氣」\n"
        "📊 GPA計算 → 輸入「GPA」\n"
        "🔗 常用連結 → 輸入「連結」\n"
        "🐒 校園生態 → 輸入「猴子」\n"
        "🍖 燒肉推薦 → 輸入「燒肉」\n"
        "🌶️ 麻辣推薦 → 輸入「麻辣」\n"
        "💻 數位優惠 → 輸入「GitHub」\n"
        "🌆 高雄旅遊 → 輸入「高雄」\n"
        "🏠 宿舍資訊 → 輸入「宿舍」\n"
        "📐 微積分   → 輸入「微積分」\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "或直接輸入任何問題，我會盡力回答！"
    )
    return [TextMessage(text=help_text, quick_reply=build_quick_reply_menu())]


def _handle_greeting(db: Session = None, **_) -> list:
    return [TextMessage(
        text="嗨嗨！👋 我是中山資管新生小幫手～\n有什麼需要幫忙的嗎？\n\n點選下方選單快速查詢！",
        quick_reply=build_quick_reply_menu(),
    )]


def _handle_nlp(text: str, user_id: str, db: Session) -> list:
    answer, score = get_answer(text)
    save_qa_feedback(db=db, line_user_id=user_id, user_question=text,
                     matched_question=None, answer=answer, similarity_score=score)
    if score > 0.0:
        return [TextMessage(text=answer, quick_reply=build_quick_reply_menu())]
    return [TextMessage(text=answer)]


def _fetch_display_name(user_id: str) -> str | None:
    try:
        api = _get_line_api()
        profile = api.get_profile(user_id)
        return profile.display_name
    except Exception as exc:
        logger.warning("取得用戶名稱失敗（%s）：%s", user_id, exc)
        return None
