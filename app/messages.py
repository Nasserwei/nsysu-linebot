"""
messages.py — LINE Flex Message 與 Carousel Template 產生器

提供以下訊息建構函式：
  - build_course_carousel()        : 選課查詢 Carousel Template
  - build_announcement_flex()      : 公告推送 Flex Message
  - build_course_detail_flex()     : 課程詳細資訊 Flex Message
  - build_welcome_message()        : 新用戶歡迎訊息
  - build_quick_reply_menu()       : Quick Reply 快速選單
"""
from __future__ import annotations

from linebot.v3.messaging import (
    CarouselColumn,
    CarouselTemplate,
    FlexBubble,
    FlexBox,
    FlexButton,
    FlexImage,
    FlexMessage,
    FlexSeparator,
    FlexText,
    MessageAction,
    PostbackAction,
    QuickReply,
    QuickReplyItem,
    TemplateMessage,
    TextMessage,
    URIAction,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 歡迎訊息
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_welcome_message(display_name: str = "新同學") -> list:
    """新用戶加入時的歡迎訊息（文字 + Quick Reply）。"""
    welcome_text = (
        f"🎓 嗨～{display_name}，歡迎加入「中山大學資管系新生小幫手」！\n\n"
        "我可以幫你：\n"
        "📢 接收系所最新公告\n"
        "🤖 解答新生常見問題\n"
        "📚 查詢選課規定與學分\n"
        "🐒 校園生態 / 🍖 美食 / 💻 數位優惠\n\n"
        "直接輸入你想問的問題，或點選下方選單開始探索吧！"
    )

    quick_reply = QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 選課資訊", text="選課資訊")),
            QuickReplyItem(action=MessageAction(label="📢 最新公告", text="最新公告")),
            QuickReplyItem(action=MessageAction(label="🐒 校園生態", text="猴子怎麼辦")),
            QuickReplyItem(action=MessageAction(label="🍖 美食推薦", text="附近哪裡有燒肉")),
            QuickReplyItem(action=MessageAction(label="💻 數位優惠", text="GitHub Copilot 學生免費")),
            QuickReplyItem(action=MessageAction(label="🌆 高雄旅遊", text="高雄好玩的地方")),
        ]
    )

    return [TextMessage(text=welcome_text, quick_reply=quick_reply)]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 選課查詢 Carousel Template
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_course_carousel() -> TemplateMessage:
    """
    選課規定查詢 Carousel：
    卡片1 必修課程、卡片2 選修規定、卡片3 通識課程、卡片4 雙主修/輔系
    """
    # 使用穩定可靠的圖片（1024x512 以上，HTTPS，無需登入）
    IMG_REQUIRED  = "https://images.unsplash.com/photo-1524178232363-1fb2b075b655?w=1024&q=80"  # 課堂/筆記
    IMG_ELECTIVE  = "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=1024&q=80"  # 書本/選擇
    IMG_GENERAL   = "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1024&q=80"  # 校園/廣場
    IMG_DOUBLE    = "https://images.unsplash.com/photo-1543269664-56d93c1b41a6?w=1024&q=80"    # 雙路/岔路

    columns = [
        CarouselColumn(
            thumbnail_image_url=IMG_REQUIRED,
            image_aspect_ratio="rectangle",
            image_size="cover",
            title="📖 必修課程",
            text="查看資管系大學部必修科目與修課規定",
            actions=[
                PostbackAction(
                    label="查詢必修清單",
                    data="action=course&type=required",
                    display_text="📖 必修課程清單",
                ),
                URIAction(
                    label="前往選課系統",
                    uri="https://selcrs.nsysu.edu.tw/",
                ),
            ],
        ),
        CarouselColumn(
            thumbnail_image_url=IMG_ELECTIVE,
            image_aspect_ratio="rectangle",
            image_size="cover",
            title="📝 選修規定",
            text="選修學分配置、系選修與校選修說明",
            actions=[
                PostbackAction(
                    label="查詢選修規定",
                    data="action=course&type=elective",
                    display_text="📝 選修學分規定",
                ),
                URIAction(
                    label="查看課程地圖",
                    uri="https://web.mis.nsysu.edu.tw/p/412-1232-455.php?Lang=zh-tw",
                ),
            ],
        ),
        CarouselColumn(
            thumbnail_image_url=IMG_GENERAL,
            image_aspect_ratio="rectangle",
            image_size="cover",
            title="🌐 通識課程",
            text="通識學分要求、分類說明與熱門課程推薦",
            actions=[
                PostbackAction(
                    label="通識學分規定",
                    data="action=course&type=general",
                    display_text="🌐 通識課程說明",
                ),
                URIAction(
                    label="通識課程查詢",
                    uri="https://www3.nsysu.edu.tw/financial/map/ge.pdf",
                ),
            ],
        ),
        CarouselColumn(
            thumbnail_image_url=IMG_DOUBLE,
            image_aspect_ratio="rectangle",
            image_size="cover",
            title="🎯 雙主修 / 輔系",
            text="申請資格、時程與跨系選課說明",
            actions=[
                PostbackAction(
                    label="了解雙主修",
                    data="action=course&type=double_major",
                    display_text="🎯 雙主修/輔系資訊",
                ),
                URIAction(
                    label="教務處網站",
                    uri="https://oaa.nsysu.edu.tw/p/412-1003-19384.php?Lang=zh-tw",
                ),
            ],
        ),
    ]

    return TemplateMessage(
        alt_text="📚 選課資訊查詢選單",
        template=CarouselTemplate(columns=columns),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 課程詳細說明 Flex Message
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 課程資料庫（靜態資料，可未來改為 DB 存取）
_COURSE_DATA = {
    "required": {
        "title": "📖 必修課程規定",
        "items": [
            ("大一必修", "微積分、計算機概論、程式設計（I）（II）"),
            ("大二必修", "資料結構、作業系統、資料庫管理、統計學"),
            ("大三必修", "軟體工程、網路概論、管理資訊系統"),
            ("畢業學分", "128 學分（含必修約 60 學分）"),
            ("備注", "每學期選課上限 25 學分，下限 12 學分"),
        ],
        "link": "https://selcrs.nsysu.edu.tw/",
    },
    "elective": {
        "title": "📝 選修學分規定",
        "items": [
            ("系選修", "至少修習 30 學分"),
            ("校選修", "至少修習 12 學分（跨院系課程）"),
            ("自由選修", "剩餘學分可自由選修校內任何課程"),
            ("英語授課", "建議修習至少 1 門英語授課課程"),
            ("抵免規定", "轉系生可申請課程抵免，需提出申請表"),
        ],
        "link": "https://web.mis.nsysu.edu.tw/p/412-1232-455.php?Lang=zh-tw",
    },
    "general": {
        "title": "🌐 通識課程說明",
        "items": [
            ("通識學分", "總計需修習 18 學分通識課程"),
            ("人文領域", "至少 3 學分（文學、歷史、哲學等）"),
            ("社會領域", "至少 3 學分（社會、政治、法律等）"),
            ("自然科學", "至少 3 學分（物理、化學、生命科學等）"),
            ("跨域整合", "至少 3 學分（跨領域整合型課程）"),
            ("體育課", "大一大二體育課為必修，不計入通識學分"),
        ],
        "link": "https://www3.nsysu.edu.tw/financial/map/ge.pdf",
    },
    "double_major": {
        "title": "🎯 雙主修 / 輔系資訊",
        "items": [
            ("申請資格", "大二起可申請，GPA 需達 2.0 以上"),
            ("雙主修", "需再修習該系必修約 40–50 學分"),
            ("輔系", "需再修習該系指定課程約 18–20 學分"),
            ("申請時間", "每年 3 月（下學期）開放申請"),
            ("熱門選擇", "財管系、資工系、企管系"),
        ],
        "link": "https://oaa.nsysu.edu.tw/p/412-1003-19384.php?Lang=zh-tw",
    },
}


def build_course_detail_flex(course_type: str) -> FlexMessage:
    """根據課程類型建立詳細說明的 Flex Message Bubble。"""
    data = _COURSE_DATA.get(course_type)
    if not data:
        return FlexMessage(
            alt_text="找不到課程資料",
            contents=FlexBubble(
                body=FlexBox(
                    layout="vertical",
                    contents=[FlexText(text="❌ 找不到對應的課程資料", wrap=True)],
                )
            ),
        )

    # Header
    header = FlexBox(
        layout="vertical",
        background_color="#1E3A5F",
        padding_all="20px",
        contents=[
            FlexText(
                text=data["title"],
                color="#FFFFFF",
                size="lg",
                weight="bold",
                wrap=True,
            )
        ],
    )

    # Body — 每個條目用分隔線區隔
    body_contents = []
    for i, (label, value) in enumerate(data["items"]):
        if i > 0:
            body_contents.append(FlexSeparator(margin="md"))
        body_contents.append(
            FlexBox(
                layout="vertical",
                margin="md",
                contents=[
                    FlexText(text=label, size="sm", color="#888888", weight="bold"),
                    FlexText(text=value, size="sm", wrap=True, margin="sm"),
                ],
            )
        )

    body = FlexBox(
        layout="vertical",
        padding_all="16px",
        contents=body_contents,
    )

    # Footer
    footer = FlexBox(
        layout="vertical",
        padding_all="12px",
        contents=[
            FlexButton(
                style="primary",
                color="#1E3A5F",
                action=URIAction(label="📎 查看詳細規定", uri=data["link"]),
            )
        ],
    )

    bubble = FlexBubble(header=header, body=body, footer=footer)
    return FlexMessage(alt_text=data["title"], contents=bubble)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 公告推送 Flex Message
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_announcement_flex(title: str, url: str, published_at: str | None = None) -> FlexMessage:
    """單筆公告的 Flex Message Bubble。"""
    date_str = published_at or "最新消息"

    header = FlexBox(
        layout="vertical",
        background_color="#D94F04",
        padding_all="16px",
        contents=[
            FlexText(
                text="📢 系所最新公告",
                color="#FFFFFF",
                size="md",
                weight="bold",
            ),
            FlexText(
                text=date_str,
                color="#FFD0B0",
                size="xs",
                margin="sm",
            ),
        ],
    )

    body = FlexBox(
        layout="vertical",
        padding_all="16px",
        contents=[
            FlexText(
                text=title,
                size="md",
                weight="bold",
                wrap=True,
                color="#1A1A1A",
            ),
            FlexText(
                text="點擊下方按鈕查看完整公告內容",
                size="xs",
                color="#888888",
                margin="md",
                wrap=True,
            ),
        ],
    )

    footer = FlexBox(
        layout="vertical",
        padding_all="12px",
        contents=[
            FlexButton(
                style="primary",
                color="#D94F04",
                action=URIAction(label="📄 查看公告", uri=url),
            )
        ],
    )

    bubble = FlexBubble(header=header, body=body, footer=footer)
    return FlexMessage(alt_text=f"📢 {title}", contents=bubble)


def build_multi_announcement_flex(announcements: list[dict]) -> FlexMessage:
    """
    多則公告彙整成一個 Flex Carousel（最多 10 則）。
    announcements: [{"title": ..., "url": ..., "published_at": ...}, ...]
    """
    from linebot.v3.messaging import FlexCarousel

    bubbles = []
    for ann in announcements[:10]:
        bubble = _build_single_announcement_bubble(
            title=ann["title"],
            url=ann["url"],
            published_at=ann.get("published_at"),
        )
        bubbles.append(bubble)

    return FlexMessage(
        alt_text=f"📢 系所公告（共 {len(bubbles)} 則）",
        contents=FlexCarousel(contents=bubbles),
    )


def _build_single_announcement_bubble(title: str, url: str, published_at: str | None) -> FlexBubble:
    """供 Carousel 使用的單泡泡版本（無 header 顏色標題）。"""
    date_str = published_at or ""
    contents = [
        FlexText(text="📢 系所公告", size="xs", color="#D94F04", weight="bold"),
        FlexText(text=title, size="sm", weight="bold", wrap=True, margin="md"),
    ]
    if date_str:
        contents.append(
            FlexText(text=date_str, size="xs", color="#888888", margin="sm")
        )

    return FlexBubble(
        body=FlexBox(layout="vertical", padding_all="16px", contents=contents),
        footer=FlexBox(
            layout="vertical",
            padding_all="12px",
            contents=[
                FlexButton(
                    style="link",
                    color="#D94F04",
                    action=URIAction(label="查看詳情 →", uri=url),
                )
            ],
        ),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Quick Reply 選單
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_quick_reply_menu() -> QuickReply:
    """通用的 Quick Reply 選單（附在任何訊息後方）。"""
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label="📚 選課資訊", text="選課資訊")),
            QuickReplyItem(action=MessageAction(label="📢 最新公告", text="最新公告")),
            QuickReplyItem(action=MessageAction(label="🌤️ 高雄天氣", text="天氣")),
            QuickReplyItem(action=MessageAction(label="📊 GPA計算", text="GPA")),
            QuickReplyItem(action=MessageAction(label="🔗 常用連結", text="連結")),
            QuickReplyItem(action=MessageAction(label="🐒 校園生態", text="猴子")),
            QuickReplyItem(action=MessageAction(label="🍖 燒肉推薦", text="燒肉")),
            QuickReplyItem(action=MessageAction(label="💻 GitHub學生", text="GitHub")),
        ]
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 高雄天氣 Flex Message
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_weather_flex(
    station: str,
    weather: str,
    temp: str,
    humid: str,
    wind: str,
) -> FlexMessage:
    """高雄即時天氣 Flex Bubble。"""
    header = FlexBox(
        layout="vertical",
        background_color="#1A73E8",
        padding_all="16px",
        contents=[
            FlexText(text="🌤️ 高雄即時天氣", color="#FFFFFF", size="md", weight="bold"),
            FlexText(text=station, color="#C8E0FF", size="xs", margin="sm"),
        ],
    )

    def _row(label: str, value: str) -> FlexBox:
        return FlexBox(
            layout="horizontal",
            margin="md",
            contents=[
                FlexText(text=label, size="sm", color="#888888", flex=2),
                FlexText(text=str(value), size="sm", weight="bold", flex=3, wrap=True),
            ],
        )

    body = FlexBox(
        layout="vertical",
        padding_all="16px",
        contents=[
            _row("天氣狀況", weather),
            FlexSeparator(margin="md"),
            _row("氣溫 (°C)", str(temp)),
            FlexSeparator(margin="md"),
            _row("濕度 / 降雨", str(humid)),
            FlexSeparator(margin="md"),
            _row("風速 (m/s)", str(wind)),
        ],
    )

    footer = FlexBox(
        layout="vertical",
        padding_all="12px",
        contents=[
            FlexButton(
                style="link",
                color="#1A73E8",
                action=URIAction(
                    label="查看完整預報 →",
                    uri="https://www.cwa.gov.tw/V8/C/W/County/County.html?CID=66",
                ),
            )
        ],
    )

    return FlexMessage(
        alt_text=f"🌤️ 高雄天氣：{weather} {temp}°C",
        contents=FlexBubble(header=header, body=body, footer=footer),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. GPA 計算機說明 Flex Message
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_gpa_flex() -> FlexMessage:
    """GPA 計算機使用說明 Flex Bubble。"""
    header = FlexBox(
        layout="vertical",
        background_color="#2E7D32",
        padding_all="16px",
        contents=[
            FlexText(text="📊 GPA 計算機", color="#FFFFFF", size="md", weight="bold"),
            FlexText(text="中山大學 4.3 級距制", color="#C8E8C9", size="xs", margin="sm"),
        ],
    )

    grade_rows = [
        ("A+  90–100", "4.3"),
        ("A   85–89",  "4.0"),
        ("B+  80–84",  "3.3"),
        ("B   75–79",  "3.0"),
        ("C+  70–74",  "2.3"),
        ("C   65–69",  "2.0"),
        ("D   60–64",  "1.0"),
        ("F   < 60",   "0.0"),
    ]

    grade_contents = []
    for label, pts in grade_rows:
        grade_contents.append(FlexBox(
            layout="horizontal",
            contents=[
                FlexText(text=label, size="xs", color="#555555", flex=3, wrap=True),
                FlexText(text=pts, size="xs", color="#2E7D32", weight="bold", flex=1, align="end"),
            ],
        ))

    body = FlexBox(
        layout="vertical",
        padding_all="16px",
        contents=[
            FlexText(text="📌 輸入格式（每科一行）：", size="sm", weight="bold"),
            FlexText(
                text="GPA 科目名稱 學分 分數",
                size="sm", color="#1A73E8", margin="sm",
                wrap=True,
            ),
            FlexText(
                text="範例：\nGPA 微積分 3 85\nGPA 程式設計 3 92\nGPA 計算機概論 2 78",
                size="xs", color="#666666", margin="md", wrap=True,
            ),
            FlexSeparator(margin="lg"),
            FlexText(text="📋 成績對照表", size="sm", weight="bold", margin="lg"),
            *grade_contents,
        ],
    )

    footer = FlexBox(
        layout="vertical",
        padding_all="12px",
        contents=[
            FlexButton(
                style="primary",
                color="#2E7D32",
                action=PostbackAction(
                    label="開始計算 GPA",
                    data="action=gpa_calc",
                    display_text="我要計算 GPA",
                ),
            )
        ],
    )

    return FlexMessage(
        alt_text="📊 GPA 計算機",
        contents=FlexBubble(header=header, body=body, footer=footer),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. 學校常用連結 Flex Message
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_school_links_flex() -> FlexMessage:
    """中山大學常用連結 Flex Bubble。"""
    header = FlexBox(
        layout="vertical",
        background_color="#003D6B",
        padding_all="16px",
        contents=[
            FlexText(text="🔗 中山大學常用連結", color="#FFFFFF", size="md", weight="bold"),
            FlexText(text="新生必存清單", color="#A8C8E8", size="xs", margin="sm"),
        ],
    )

    links = [
        ("🏫", "學校首頁",    "https://www.nsysu.edu.tw/"),
        ("📚", "選課系統",    "https://selcrs.nsysu.edu.tw/"),
        ("🗂️", "校務資訊系統","https://portal.nsysu.edu.tw/"),
        ("📋", "資管系官網",  "https://mis.nsysu.edu.tw/"),
        ("📖", "課程地圖",    "https://web.mis.nsysu.edu.tw/p/412-1232-455.php?Lang=zh-tw"),
        ("🌐", "通識課程",    "https://www3.nsysu.edu.tw/financial/map/ge.pdf"),
        ("🎯", "雙主修/輔系", "https://oaa.nsysu.edu.tw/p/412-1003-19384.php?Lang=zh-tw"),
        ("🏠", "宿舍組",      "https://dorm.nsysu.edu.tw/"),
        ("📚", "圖書館",      "https://lib.nsysu.edu.tw/"),
    ]

    body_contents = []
    for i, (icon, name, url) in enumerate(links):
        if i > 0:
            body_contents.append(FlexSeparator(margin="sm"))
        body_contents.append(
            FlexButton(
                style="link",
                height="sm",
                action=URIAction(label=f"{icon} {name}", uri=url),
            )
        )

    body = FlexBox(layout="vertical", padding_all="8px", contents=body_contents)

    return FlexMessage(
        alt_text="🔗 中山大學常用連結",
        contents=FlexBubble(header=header, body=body),
    )
