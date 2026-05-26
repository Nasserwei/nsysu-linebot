"""
rich_menu.py — LINE Rich Menu（圖文選單）設定
使用純色色塊，文字用英文/符號避免字型問題。
"""
from __future__ import annotations
import io
import logging
import struct
import zlib

logger = logging.getLogger(__name__)


def _generate_menu_image() -> bytes:
    """
    生成 2500x843 的 Rich Menu 圖片。
    使用純色色塊 + 簡單英數字，避免中文字型缺失問題。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 2500, 843
        img = Image.new("RGB", (W, H), color=(245, 245, 245))
        draw = ImageDraw.Draw(img)

        # 每格設定：(col, row, 行1文字, 行2文字, 背景色)
        cells = [
            (0, 0, "Course",  "選課資訊", (25,  80,  150)),
            (1, 0, "News",    "最新公告", (200, 60,  40 )),
            (2, 0, "Weather", "高雄天氣", (20,  110, 190)),
            (0, 1, "GPA",     "成績計算", (40,  120, 45 )),
            (1, 1, "Food",    "美食推薦", (195, 95,  25 )),
            (2, 1, "Links",   "常用連結", (75,  45,  155)),
        ]

        col_w = W // 3
        row_h = H // 2

        # 嘗試載入字型
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
        font_en, font_zh = None, None
        for fp in font_paths:
            try:
                font_en = ImageFont.truetype(fp, 95)
                font_zh = ImageFont.truetype(fp, 70)
                break
            except Exception:
                continue
        if font_en is None:
            font_en = ImageFont.load_default()
            font_zh = font_en

        for col, row, line1, line2, color in cells:
            x0, y0 = col * col_w, row * row_h
            x1, y1 = x0 + col_w, y0 + row_h

            # 背景
            draw.rectangle([x0, y0, x1, y1], fill=color)
            # 白色邊框
            draw.rectangle([x0, y0, x1-1, y1-1], outline=(255,255,255), width=5)

            cx = (x0 + x1) // 2
            cy = (y0 + y1) // 2

            # 英文大字（上方）
            draw.text((cx, cy - 55), line1, font=font_en,
                      fill=(255, 255, 255), anchor="mm")
            # 中文小字（下方，若字型支援）
            draw.text((cx, cy + 65), line2, font=font_zh,
                      fill=(220, 235, 255), anchor="mm")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        logger.info("圖片生成成功（Pillow）")
        return buf.getvalue()

    except ImportError:
        logger.warning("Pillow 不可用，使用純色 PNG")
        return _colored_png()


def _colored_png() -> bytes:
    """
    不依賴 Pillow，生成一個有6個色塊的 PNG。
    每個色塊對應一個功能區域。
    """
    W, H = 2500, 843

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))

    # 6色塊顏色（RGB）
    colors = [
        (25,  80,  150), (200, 60,  40),  (20,  110, 190),
        (40,  120, 45),  (195, 95,  25),  (75,  45,  155),
    ]
    col_w = W // 3
    row_h = H // 2

    rows_data = b""
    for y in range(H):
        row = b"\x00"  # filter byte
        row_idx = 0 if y < row_h else 1
        for x in range(W):
            col_idx = min(x // col_w, 2)
            c_idx = row_idx * 3 + col_idx
            r, g, b = colors[c_idx]
            # 白色邊框（每格邊緣5px）
            in_border = (
                x % col_w < 5 or x % col_w > col_w - 6 or
                y % row_h < 5 or y % row_h > row_h - 6
            )
            if in_border:
                row += b"\xff\xff\xff"
            else:
                row += bytes([r, g, b])
        rows_data += row

    idat = chunk(b"IDAT", zlib.compress(rows_data, 1))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def create_rich_menu() -> str | None:
    from linebot.v3.messaging import (
        ApiClient, Configuration, MessagingApi, MessagingApiBlob,
        RichMenuArea, RichMenuBounds, RichMenuRequest, RichMenuSize,
        MessageAction,
    )
    from app.config import settings

    cfg = Configuration(access_token=settings.line_channel_access_token)

    # Step 1：建立 Rich Menu
    with ApiClient(cfg) as client:
        api = MessagingApi(client)
        req = RichMenuRequest(
            size=RichMenuSize(width=2500, height=843),
            selected=True,
            name="主選單",
            chat_bar_text="📋 功能選單",
            areas=[
                RichMenuArea(
                    bounds=RichMenuBounds(x=0,    y=0,   width=833, height=421),
                    action=MessageAction(label="選課資訊", text="選課"),
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=833,  y=0,   width=834, height=421),
                    action=MessageAction(label="最新公告", text="公告"),
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1667, y=0,   width=833, height=421),
                    action=MessageAction(label="高雄天氣", text="天氣"),
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=0,    y=421, width=833, height=422),
                    action=MessageAction(label="GPA計算",  text="GPA"),
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=833,  y=421, width=834, height=422),
                    action=MessageAction(label="美食推薦", text="美食推薦"),
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1667, y=421, width=833, height=422),
                    action=MessageAction(label="常用連結", text="連結"),
                ),
            ],
        )
        rich_menu_id = api.create_rich_menu(rich_menu_request=req).rich_menu_id
        logger.info("Step1 建立成功：%s", rich_menu_id)

    # Step 2：上傳圖片
    image_bytes = _generate_menu_image()
    with ApiClient(cfg) as client:
        blob_api = MessagingApiBlob(client)
        blob_api.set_rich_menu_image(
            rich_menu_id=rich_menu_id,
            body=bytearray(image_bytes),
            _headers={"Content-Type": "image/png"},
        )
        logger.info("Step2 圖片上傳成功（%d bytes）", len(image_bytes))

    # Step 3：設為預設
    with ApiClient(cfg) as client:
        api = MessagingApi(client)
        api.set_default_rich_menu(rich_menu_id=rich_menu_id)
        logger.info("Step3 設為預設成功")

    return rich_menu_id


def delete_all_rich_menus() -> None:
    from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
    from app.config import settings

    cfg = Configuration(access_token=settings.line_channel_access_token)
    with ApiClient(cfg) as client:
        api = MessagingApi(client)
        try:
            api.cancel_default_rich_menu()
        except Exception:
            pass
        try:
            menus = api.get_rich_menu_list()
            for menu in menus.richmenus:
                api.delete_rich_menu(rich_menu_id=menu.rich_menu_id)
                logger.info("刪除：%s", menu.rich_menu_id)
        except Exception as exc:
            logger.warning("刪除失敗：%s", exc)
