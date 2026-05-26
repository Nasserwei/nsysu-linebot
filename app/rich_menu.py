"""
rich_menu.py — LINE Rich Menu（圖文選單）設定

使用純色背景圖片，不需要本地圖片檔案。
LINE Rich Menu 需要上傳圖片，這裡自動生成一張簡單的 PNG。
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def _generate_menu_image() -> bytes:
    """
    用 Pillow 生成 Rich Menu 圖片（2500x843）
    分成 6 格，每格顯示 emoji + 文字。
    若 Pillow 不可用則回傳最小合法 PNG。
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 2500, 843
        img = Image.new("RGB", (W, H), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 格子定義 [col, row, emoji, label, bg_color]
        cells = [
            (0, 0, "📚", "選課資訊", (30,  90,  160)),
            (1, 0, "📢", "最新公告", (210, 70,  50 )),
            (2, 0, "🌤️", "高雄天氣", (26,  115, 200)),
            (0, 1, "📊", "GPA 計算", (46,  125, 50 )),
            (1, 1, "🍽️", "美食推薦", (200, 100, 30 )),
            (2, 1, "🔗", "常用連結", (80,  50,  160)),
        ]

        col_w = W // 3
        row_h = H // 2

        for col, row, emoji, label, color in cells:
            x0 = col * col_w
            y0 = row * row_h
            x1 = x0 + col_w
            y1 = y0 + row_h

            # 背景色
            draw.rectangle([x0, y0, x1, y1], fill=color)
            # 格線
            draw.rectangle([x0, y0, x1 - 1, y1 - 1],
                           outline=(255, 255, 255), width=3)

            # 文字（用預設字體）
            cx = (x0 + x1) // 2
            cy = (y0 + y1) // 2

            # emoji 行
            try:
                font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 80)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
            except Exception:
                font_big = ImageFont.load_default()
                font_small = font_big

            draw.text((cx, cy - 60), emoji, font=font_big,
                      fill=(255, 255, 255), anchor="mm")
            draw.text((cx, cy + 60), label, font=font_small,
                      fill=(255, 255, 255), anchor="mm")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except ImportError:
        # Pillow 不可用：回傳一個 2500x843 白色 PNG（最小合法）
        return _minimal_png(2500, 843)


def _minimal_png(width: int, height: int) -> bytes:
    """用 zlib 生成一個純白的 PNG，不依賴 Pillow。"""
    import struct, zlib

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = png_chunk(b"IHDR", ihdr_data)

    # IDAT — 純白 RGB
    raw_row = b"\x00" + b"\xFF\xFF\xFF" * width
    raw = raw_row * height
    idat = png_chunk(b"IDAT", zlib.compress(raw))

    iend = png_chunk(b"IEND", b"")

    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def create_rich_menu() -> str | None:
    """
    建立 Rich Menu 並設為預設，回傳 richMenuId。
    ┌──────────┬──────────┬──────────┐
    │ 📚 選課資訊 │ 📢 最新公告 │ 🌤️ 高雄天氣 │
    ├──────────┼──────────┼──────────┤
    │ 📊 GPA計算 │ 🍽️ 美食推薦 │ 🔗 常用連結 │
    └──────────┴──────────┴──────────┘
    """
    from linebot.v3.messaging import (
        ApiClient,
        Configuration,
        MessagingApi,
        MessagingApiBlob,
        RichMenuArea,
        RichMenuBounds,
        RichMenuRequest,
        RichMenuSize,
        MessageAction,
    )
    from app.config import settings

    configuration = Configuration(access_token=settings.line_channel_access_token)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        rich_menu_request = RichMenuRequest(
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

        # 建立 Rich Menu
        rich_menu_id = line_bot_api.create_rich_menu(
            rich_menu_request=rich_menu_request
        ).rich_menu_id
        logger.info("Rich Menu 建立：%s", rich_menu_id)

    # 上傳圖片（需要獨立的 ApiClient）
    with ApiClient(configuration) as blob_client:
        blob_api = MessagingApiBlob(blob_client)
        image_bytes = _generate_menu_image()
        blob_api.set_rich_menu_image(
            rich_menu_id=rich_menu_id,
            body=bytearray(image_bytes),
            _headers={"Content-Type": "image/png"},
        )
        logger.info("Rich Menu 圖片上傳完成，大小：%d bytes", len(image_bytes))

    # 設為預設（所有用戶都能看到）
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.set_default_rich_menu(rich_menu_id=rich_menu_id)
        logger.info("已設為預設 Rich Menu")

    return rich_menu_id


def delete_all_rich_menus() -> None:
    """刪除所有 Rich Menu。"""
    from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
    from app.config import settings

    configuration = Configuration(access_token=settings.line_channel_access_token)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        try:
            menus = line_bot_api.get_rich_menu_list()
            for menu in menus.richmenus:
                line_bot_api.delete_rich_menu(rich_menu_id=menu.rich_menu_id)
                logger.info("刪除 Rich Menu：%s", menu.rich_menu_id)
        except Exception as exc:
            logger.warning("刪除 Rich Menu 失敗：%s", exc)
