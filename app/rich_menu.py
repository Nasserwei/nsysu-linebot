"""
rich_menu.py — LINE Rich Menu（圖文選單）設定
"""
from __future__ import annotations
import io
import logging

logger = logging.getLogger(__name__)


def _generate_menu_image() -> bytes:
    """生成 2500x843 的 Rich Menu 圖片。"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 2500, 843
        img = Image.new("RGB", (W, H), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        cells = [
            (0, 0, "📚 選課資訊", (30,  90,  160)),
            (1, 0, "📢 最新公告", (210, 70,  50 )),
            (2, 0, "🌤 高雄天氣", (26,  115, 200)),
            (0, 1, "📊 GPA計算",  (46,  125, 50 )),
            (1, 1, "🍽 美食推薦", (200, 100, 30 )),
            (2, 1, "🔗 常用連結", (80,  50,  160)),
        ]

        col_w = W // 3
        row_h = H // 2

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
        except Exception:
            font = ImageFont.load_default()

        for col, row, label, color in cells:
            x0, y0 = col * col_w, row * row_h
            x1, y1 = x0 + col_w, y0 + row_h
            draw.rectangle([x0, y0, x1, y1], fill=color)
            draw.rectangle([x0, y0, x1-1, y1-1], outline=(255,255,255), width=4)
            cx, cy = (x0+x1)//2, (y0+y1)//2
            draw.text((cx, cy), label, font=font, fill=(255,255,255), anchor="mm")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except ImportError:
        return _minimal_png(2500, 843)


def _minimal_png(width: int, height: int) -> bytes:
    """不依賴 Pillow 的最小合法白色 PNG。"""
    import struct, zlib

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw  = (b"\x00" + b"\xFF\xFF\xFF" * width) * height
    idat = chunk(b"IDAT", zlib.compress(raw, 1))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def create_rich_menu() -> str | None:
    """
    建立 Rich Menu 流程：
    1. 建立 Rich Menu（取得 ID）
    2. 上傳圖片
    3. 設為預設
    """
    from linebot.v3.messaging import (
        ApiClient, Configuration, MessagingApi, MessagingApiBlob,
        RichMenuArea, RichMenuBounds, RichMenuRequest, RichMenuSize,
        MessageAction,
    )
    from app.config import settings

    cfg = Configuration(access_token=settings.line_channel_access_token)

    # Step 1：建立 Rich Menu，取得 ID
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

    # Step 2：上傳圖片（必須在 set_default 之前）
    image_bytes = _generate_menu_image()
    logger.info("圖片大小：%d bytes", len(image_bytes))

    with ApiClient(cfg) as client:
        blob_api = MessagingApiBlob(client)
        blob_api.set_rich_menu_image(
            rich_menu_id=rich_menu_id,
            body=bytearray(image_bytes),
            _headers={"Content-Type": "image/png"},
        )
        logger.info("Step2 圖片上傳成功")

    # Step 3：設為預設（圖片上傳後才能執行）
    with ApiClient(cfg) as client:
        api = MessagingApi(client)
        api.set_default_rich_menu(rich_menu_id=rich_menu_id)
        logger.info("Step3 設為預設成功")

    return rich_menu_id


def delete_all_rich_menus() -> None:
    """刪除所有現有的 Rich Menu。"""
    from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
    from app.config import settings

    cfg = Configuration(access_token=settings.line_channel_access_token)
    with ApiClient(cfg) as client:
        api = MessagingApi(client)
        try:
            # 先取消預設
            try:
                api.cancel_default_rich_menu()
            except Exception:
                pass
            menus = api.get_rich_menu_list()
            for menu in menus.richmenus:
                api.delete_rich_menu(rich_menu_id=menu.rich_menu_id)
                logger.info("刪除：%s", menu.rich_menu_id)
        except Exception as exc:
            logger.warning("刪除失敗：%s", exc)
