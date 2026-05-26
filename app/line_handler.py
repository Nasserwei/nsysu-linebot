"""
line_handler.py — LINE Webhook 事件路由與處理
完全使用關鍵字比對，不依賴 NLP，確保穩定回覆。
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
    Announcement,
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
                logger.error("廣播失敗：%s", exc)
        mark_announcement_pushed(db, ann.id)
        pushed_count += 1
    return pushed_count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 關鍵字對應回覆內容（純文字，不依賴 NLP）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ANSWERS = {
    "monkey": (
        "🐒 中山大學校園確實有台灣獼猴出沒！\n\n"
        "【安全守則】\n"
        "① 不要直視猴子眼睛（視為挑釁）\n"
        "② 切勿餵食！會增加攻擊性\n"
        "③ 背包、食物請拿好不要外露\n"
        "④ 被靠近時保持冷靜、緩慢後退，勿奔跑\n"
        "⑤ 遇到帶幼猴的母猴更要保持距離\n\n"
        "【生態小知識】\n"
        "🌿 台灣獼猴是台灣特有種，全台唯一野生靈長類\n"
        "📍 常出沒於西子灣步道、圖書館後山\n\n"
        "⚠️ 發生攻擊事件請聯繫校安中心：(07)525-2000"
    ),
    "bbq": (
        "🔥 中山大學周邊燒肉／BBQ 推薦：\n\n"
        "① 🥩 牛角日式燒肉（夢時代店）\n"
        "   和牛等級多樣，人均 $500–$900\n\n"
        "② 🍖 燒肉眾 精緻炭火燒肉（鼓山店）\n"
        "   炭火現烤，人均 $400–$700\n\n"
        "③ 🌟 八色韓式烤肉（左營店）\n"
        "   八種口味豬五花，人均 $350–$600\n\n"
        "🚌 從中山大學搭公車至哈瑪星站轉乘約15–30分鐘"
    ),
    "spicy": (
        "🌶️ 麻辣控看過來！周邊麻辣特選：\n\n"
        "① 鬍鬚張麻辣鴨血豆腐\n"
        "   麻辣湯底濃郁，鴨血豆腐必點\n\n"
        "② 辣一鍋\n"
        "   麻辣湯底層次豐富，可選辣度\n\n"
        "③ 川老爺麻辣火鍋\n"
        "   老成都風味，牛油鍋底超香\n\n"
        "💡 高雄飲食偏甜，要真辣記得告知店員！"
    ),
    "food": (
        "🍽️ 中山大學周邊美食完整指南\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "【🌅 早餐推薦】\n"
        "🥚 哈瑪星古早味蛋餅 ── 超厚蛋餅，在地30年老店\n"
        "🍚 美濃客家粄條 ── 湯頭清甜，份量實在 $60起\n"
        "🥪 莉莉早餐 ── 鼓山區學生最愛，三明治$35起\n"
        "🫔 麥當勞/麥味登 ── 校門口5分鐘，快速選擇\n\n"
        "【☀️ 午餐推薦】\n"
        "🍱 校內學生餐廳 ── 便當$70起，最近新裝潢！\n"
        "🐟 鼓山魚市場海鮮小炒 ── 新鮮直送，合菜$200起\n"
        "🍜 西子灣排骨飯 ── 必吃炸排骨，$100有找\n"
        "🥩 鹽埕埔牛肉湯 ── 清燉牛肉湯，老饕最愛 $120\n"
        "🍣 迴轉壽司（哈瑪星店）── 平價日式，$30/盤起\n\n"
        "【🌙 晚餐推薦】\n"
        "🦞 鹽埕區海產店 ── 活跳跳海鮮，必點炒蛤蜊\n"
        "🍲 鼓山區臭豆腐 ── 台灣必吃，酥脆不油膩\n"
        "🥘 鹽埕埔滷肉飯 ── 在地50年老店，$40一碗\n"
        "🍛 咖哩專門店（五福路）── 日式咖哩飯，$120起\n"
        "🫕 薑母鴨/羊肉爐 ── 秋冬必吃，哈瑪星周邊多間\n\n"
        "【🧋 飲料店推薦】\n"
        "🟢 迷客夏 ── 校門口3分鐘，鮮奶茶系列必點\n"
        "🔴 清心福全 ── 平價首選，$35起\n"
        "🟡 五桐號 ── 燕麥拿鐵超人氣，$65起\n"
        "🟠 大苑子 ── 水果茶系列，$60起\n"
        "⚫ 路易莎咖啡 ── 讀書好去處，咖啡$55起\n\n"
        "【🌊 鹽埕區必吃】\n"
        "🦑 大溝頂鹽埕市場 ── 銅板美食天堂！\n"
        "  • 鹽埕肉圓 $30 • 豬血湯 $30\n"
        "  • 愛玉冰 $35 • 肉燥飯 $40\n"
        "🍢 鹽埕埔無名臭豆腐 ── 排隊必吃！\n"
        "☕ 駁二周邊咖啡廳 ── 文青必去，拍照打卡\n\n"
        "【⛵ 鼓山區必吃】\n"
        "🐡 哈瑪星海產粥 ── 深夜食堂，$80起\n"
        "🥟 鼓山渡船頭水餃 ── 手工現包，$60/10顆\n"
        "🍤 西子灣炸物攤 ── 下課宵夜首選\n"
        "🐚 旗津老街海鮮 ── 渡輪10分鐘，烤小卷必吃！\n\n"
        "💡 Google Maps 搜尋「鹽埕區美食」或「哈瑪星美食」\n"
        "有更多隱藏版選擇等你發掘！"
    ),
    "github": (
        "💻 GitHub Copilot 學生免費申請：\n\n"
        "【申請步驟】\n"
        "1️⃣ 準備中山大學 edu.tw 信箱\n"
        "   （學號@student.nsysu.edu.tw）\n"
        "2️⃣ 前往 github.com/education/students\n"
        "3️⃣ 點擊「Join GitHub Education」\n"
        "4️⃣ 選「School email address」驗證\n"
        "5️⃣ 上傳學生證或選課截圖\n"
        "6️⃣ 等待審核（1–5個工作天）\n\n"
        "✅ 通過後獲得：\n"
        "• GitHub Copilot 免費\n"
        "• JetBrains 全家桶\n"
        "• Azure 學生額度 $100\n"
        "• Canva Pro 等數十種福利"
    ),
    "chatgpt": (
        "🤖 ChatGPT 學生方案資訊：\n\n"
        "OpenAI 目前無官方學生折扣，Plus 每月 $20 美元。\n\n"
        "【省錢替代方案】\n"
        "✅ ChatGPT 免費版（GPT-4o mini）日常夠用\n"
        "✅ Microsoft Copilot（學校 Office 365 免費）\n"
        "✅ Google Gemini（有學生方案）\n"
        "✅ Notion AI（學生方案免費）\n\n"
        "💡 先用 GitHub Education 工具組合\n"
        "通常就能滿足大部分學習需求！"
    ),
    "gemini": (
        "🌟 Google Gemini 學生方案：\n\n"
        "【Gemini for Education】\n"
        "學校 Google Workspace 帳號可免費使用\n"
        "Gemini in Google Docs/Gmail 等工具\n\n"
        "【免費工具推薦】\n"
        "✅ Google Colab ── 免費 GPU/TPU，AI作業必備\n"
        "✅ Google Cloud for Students ── 有免費額度\n"
        "✅ Gemini API ── 有免費使用額度\n\n"
        "📌 資管系推薦：Google Colab + Gemini API\n"
        "做機器學習作業超方便！"
    ),
    "student_benefit": (
        "🎓 學生數位福利大全：\n\n"
        "【完全免費】\n"
        "✅ GitHub Copilot + Pro（申請 GitHub Education）\n"
        "✅ JetBrains 全家桶（PyCharm, IntelliJ...）\n"
        "✅ Microsoft Azure（$100 美元額度）\n"
        "✅ Figma Education\n"
        "✅ Canva for Education\n\n"
        "【學校授權】\n"
        "🔧 Microsoft Office 365\n"
        "🔧 MATLAB、SPSS 等學術軟體\n\n"
        "【優惠折扣】\n"
        "💰 Notion Plus 免費\n"
        "💰 Spotify、Apple Music 半價\n"
        "💰 YouTube Premium 折扣"
    ),
    "lecture": (
        "🎤 中山大學講座與活動資訊：\n\n"
        "【查詢管道】\n"
        "① 資管系官網：web.mis.nsysu.edu.tw/\n"
        "② 中山大學學務處：osa.nsysu.edu.tw\n"
        "③ 關注「中山大學」LINE 官方帳號\n\n"
        "【常見講座類型】\n"
        "🖥️ 產業趨勢（AI、資安、雲端）\n"
        "📊 資料科學與機器學習工作坊\n"
        "🚀 新創創業講座\n"
        "🔐 資安 CTF 競賽培訓\n\n"
        "💡 加入系學會 LINE 群第一時間收通知！"
    ),
    "kaohsiung": (
        "🌆 高雄旅遊推薦：\n\n"
        "【從中山大學出發（近）】\n"
        "⛵ 旗津老街 ── 渡輪10分鐘，烤小卷必吃\n"
        "🌊 西子灣夕陽 ── 學校就有！全台最美夕陽\n"
        "🏯 打狗英國領事館 ── 步行可達\n\n"
        "【捷運可達】\n"
        "🚇 六合夜市 ── 美麗島站\n"
        "🎨 駁二藝術特區 ── 假日市集\n"
        "🌈 美麗島站 ── 全球最美捷運站\n\n"
        "【週末一日遊】\n"
        "🌺 壽山生態步道\n"
        "🎢 夢時代購物中心\n\n"
        "🚇 辦高雄捷運月票（學生優惠）或用 YouBike！"
    ),
    "club": (
        "🎉 中山大學社團推薦：\n\n"
        "【技術相關】\n"
        "💻 程式設計研究社 ── ICPC競賽\n"
        "🔐 資安研究社 ── CTF競賽\n"
        "📊 大數據研究社 ── ML實作\n"
        "🤖 AI 研究社\n\n"
        "【生活興趣】\n"
        "🎸 熱音社、吉他社\n"
        "🏀 籃球、羽球、游泳校隊\n"
        "📸 攝影社 ── 拍西子灣夕陽！\n\n"
        "【一定要加】\n"
        "🎓 資管系系學會 ── 迎新、烤肉、系際杯\n\n"
        "💡 大一先參加迎新博覽會再決定！"
    ),
    "dorm": (
        "🏠 中山大學宿舍資訊：\n\n"
        "【申請方式】\n"
        "新生放榜後由學校統一分配\n"
        "🔗 宿舍組：housing-osa.nsysu.edu.tw\n\n"
        "【費用（參考）】\n"
        "• 4人房：約 $5,000–$8,000 / 學期\n"
        "• 2人房：約 $8,000–$12,000 / 學期\n\n"
        "【門禁】🕚 23:00–06:00\n\n"
        "【設施】\n"
        "✅ 每棟 Wi-Fi\n"
        "✅ 洗衣機（投幣式）\n"
        "✅ 自修室、交誼廳\n\n"
        "❓ 聯繫宿舍組：(07)525-2000 分機 2400"
    ),
    "calculus": (
        "📐 微積分求生指南：\n\n"
        "【學習資源】\n"
        "📺 YouTube：\n"
        "• 數學老師沒告訴你的事（繁中）\n"
        "• 3Blue1Brown「Essence of Calculus」\n"
        "• Khan Academy 微積分系列（免費）\n\n"
        "【實戰建議】\n"
        "① 每週跟上進度，不要積欠！\n"
        "② 找學長姐借歷年考古題\n"
        "③ 考前一週密集刷題\n"
        "④ 善用 TA 輔導時間（免費！）\n\n"
        "💡 統計學、線性代數、ML 都用到微積分\n"
        "現在打好基礎很值得！"
    ),
}

# 關鍵字 → 答案 key 對照表
_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["猴子", "獼猴", "猴"], "monkey"),
    (["燒肉", "烤肉", "bbq", "燒烤"], "bbq"),
    (["麻辣", "辣", "火鍋", "麻辣鍋"], "spicy"),
    (["美食", "吃什麼", "餐廳", "吃飯", "美食推薦", "早餐", "午餐", "晚餐", "宵夜", "飲料", "鹽埕", "鼓山", "哈瑪星", "周邊美食", "附近吃", "便宜吃"], "food"),
    (["github", "copilot", "github education"], "github"),
    (["chatgpt", "openai", "chat gpt"], "chatgpt"),
    (["gemini", "google ai"], "gemini"),
    (["學生優惠", "edu信箱", "學生福利", "免費軟體", "學生軟體", "數位優惠", "學生方案", "軟體優惠"], "student_benefit"),
    (["講座", "活動", "演講", "工作坊", "hackathon"], "lecture"),
    (["高雄", "景點", "旅遊", "夜市", "旗津", "西子灣"], "kaohsiung"),
    (["社團", "加社團", "課外活動"], "club"),
    (["宿舍", "住宿", "門禁", "宿舍費"], "dorm"),
    (["微積分", "calculus", "大一數學", "數學好難"], "calculus"),
]

# GPA 格式
_GPA_LINE_RE = re.compile(
    r"^gpa\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 路由主函式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _route_text(text: str, user_id: str, db: Session) -> list:
    lower = text.lower().strip()

    # 0. GPA 計算
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if lines and _GPA_LINE_RE.match(lines[0]):
        return _handle_gpa_calculate(lines)

    # 1. 功能型關鍵字路由
    if any(k in lower for k in ["選課", "課程", "必修", "選修", "通識"]):
        return [build_course_carousel()]
    if any(k in lower for k in ["公告", "最新公告", "系所公告"]):
        return _handle_latest_announcements(db=db)
    if any(k in lower for k in ["天氣", "氣溫", "下雨", "會不會下雨"]):
        return _handle_weather()
    if any(k in lower for k in ["gpa", "成績計算"]):
        return [build_gpa_flex()]
    if any(k in lower for k in ["連結", "官網", "學校首頁", "常用連結"]):
        return [build_school_links_flex()]
    if any(k in lower for k in ["你好", "hi", "hello", "嗨", "哈囉"]):
        return _handle_greeting()
    if any(k in lower for k in ["說明", "幫助", "help", "選單", "功能"]):
        return _handle_help()

    # 2. 知識庫關鍵字比對（純關鍵字，不用 NLP）
    for keywords, answer_key in _KEYWORD_MAP:
        if any(k in lower for k in keywords):
            answer = _ANSWERS[answer_key]
            save_qa_feedback(db=db, line_user_id=user_id, user_question=text,
                             matched_question=answer_key, answer=answer, similarity_score=1.0)
            return [TextMessage(text=answer, quick_reply=build_quick_reply_menu())]

    # 3. Fallback
    fallback = (
        "🤔 抱歉，我還不太確定你在問什麼～\n\n"
        "你可以試試輸入以下關鍵字：\n"
        "🐒 猴子  🍖 燒肉  🌶️ 麻辣\n"
        "💻 GitHub  🎤 講座  🌆 高雄\n"
        "🏠 宿舍  📐 微積分  🌤️ 天氣\n"
        "📊 GPA  🔗 連結  📚 選課資訊"
    )
    return [TextMessage(text=fallback, quick_reply=build_quick_reply_menu())]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 功能處理器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _handle_latest_announcements(db: Session, **_) -> list:
    announcements = (
        db.query(Announcement)
        .order_by(Announcement.created_at.desc())
        .limit(5)
        .all()
    )
    if not announcements:
        return [TextMessage(
            text="目前資料庫尚無公告記錄。\n請前往系網查看：\nhttps://web.mis.nsysu.edu.tw/",
            quick_reply=build_quick_reply_menu(),
        )]
    ann_dicts = [{"title": a.title, "url": a.url, "published_at": a.published_at} for a in announcements]
    return [build_multi_announcement_flex(ann_dicts)]


def _handle_weather() -> list:
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
            return [build_weather_flex(
                station=st["StationName"],
                weather=we.get("Weather", "—"),
                temp=we.get("AirTemperature", "—"),
                humid=we.get("RelativeHumidity", "—"),
                wind=we.get("WindSpeed", "—"),
            )]
    except Exception as exc:
        logger.warning("天氣 API 失敗：%s", exc)

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
        return [build_weather_flex(
            station="高雄市",
            weather=elements.get("Wx", "—"),
            temp=f'{elements.get("MinT","—")}～{elements.get("MaxT","—")}',
            humid=f'降雨機率 {elements.get("PoP","—")}%',
            wind="—",
        )]
    except Exception as exc2:
        logger.warning("天氣 fallback 失敗：%s", exc2)
        return [TextMessage(
            text="🌤️ 目前無法取得天氣資訊，請查詢：\nhttps://www.cwa.gov.tw",
            quick_reply=build_quick_reply_menu(),
        )]


def _handle_gpa_calculate(lines: list[str]) -> list:
    def score_to_grade(s: float) -> float:
        if s >= 90: return 4.3
        if s >= 85: return 4.0
        if s >= 80: return 3.3
        if s >= 75: return 3.0
        if s >= 70: return 2.3
        if s >= 65: return 2.0
        if s >= 60: return 1.0
        return 0.0

    courses, errors = [], []
    for line in lines:
        m = _GPA_LINE_RE.match(line.strip())
        if m:
            name = m.group(1)
            credit = float(m.group(2))
            score = float(m.group(3))
            courses.append((name, credit, score, score_to_grade(score)))
        else:
            errors.append(line)

    if not courses:
        return [TextMessage(text="❌ 格式錯誤，請參考：\nGPA 微積分 3 85\nGPA 程式設計 3 92")]

    total_credits = sum(c[1] for c in courses)
    gpa = sum(c[1] * c[3] for c in courses) / total_credits if total_credits else 0.0

    out = ["📊 GPA 計算結果\n",
           f"{'科目':<10} {'學分':>4} {'分數':>5} {'績點':>5}",
           "─" * 30]
    for name, credit, score, grade in courses:
        out.append(f"{name:<10} {credit:>4.0f} {score:>5.1f} {grade:>5.1f}")
    out.extend(["─" * 30, f"總學分：{total_credits:.0f}", f"✨ GPA：{gpa:.2f}"])

    if gpa >= 3.8: out.append("\n🏆 超優秀！書卷獎等你！")
    elif gpa >= 3.0: out.append("\n👍 表現不錯，繼續保持！")
    elif gpa >= 2.0: out.append("\n💪 還有進步空間，加油！")
    else: out.append("\n😢 善用 TA 和教授 Office Hour！")

    if errors:
        out.append(f"\n⚠️ 以下行格式有誤：\n" + "\n".join(errors))

    return [TextMessage(text="\n".join(out), quick_reply=build_quick_reply_menu())]


def _handle_greeting() -> list:
    return [TextMessage(
        text="嗨嗨！👋 我是中山資管新生小幫手～\n有什麼需要幫忙的嗎？\n\n點選下方選單快速查詢！",
        quick_reply=build_quick_reply_menu(),
    )]


def _handle_help() -> list:
    return [TextMessage(
        text=(
            "🤖 中山資管新生小幫手 — 功能說明\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "📚 選課資訊 → 輸入「選課」\n"
            "📢 最新公告 → 輸入「公告」\n"
            "🌤️ 高雄天氣 → 輸入「天氣」\n"
            "📊 GPA計算  → 輸入「GPA」\n"
            "🔗 常用連結 → 輸入「連結」\n"
            "🐒 猴子守則 → 輸入「猴子」\n"
            "🍖 燒肉推薦 → 輸入「燒肉」\n"
            "🌶️ 麻辣推薦 → 輸入「麻辣」\n"
            "💻 數位優惠 → 輸入「GitHub」\n"
            "🌆 高雄旅遊 → 輸入「高雄」\n"
            "🏠 宿舍資訊 → 輸入「宿舍」\n"
            "📐 微積分   → 輸入「微積分」\n"
            "🎉 社團推薦 → 輸入「社團」\n"
            "━━━━━━━━━━━━━━━━━━━"
        ),
        quick_reply=build_quick_reply_menu(),
    )]


def _fetch_display_name(user_id: str) -> str | None:
    try:
        api = _get_line_api()
        profile = api.get_profile(user_id)
        return profile.display_name
    except Exception as exc:
        logger.warning("取得用戶名稱失敗（%s）：%s", user_id, exc)
        return None
