"""
rich_menu.py — LINE Rich Menu（圖文選單）設定

Rich Menu 讓用戶隨時看到功能按鈕，不需要打「你好」才能叫出選單。
執行此腳本一次即可設定完成，之後永久生效。

使用方式：
  python app/rich_menu.py
  
或透過 API 端點：
  POST /admin/setup-rich-menu
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def create_rich_menu() -> str | None:
    """
    建立 Rich Menu 並回傳 richMenuId。
    Rich Menu 分成 6 個格子：
    ┌─────────────┬─────────────┬─────────────┐
    │  📚 選課資訊  │  📢 最新公告  │  🌤️ 高雄天氣  │
    ├─────────────┼─────────────┼─────────────┤
    │  📊 GPA計算  │  🍽️ 美食推薦  │  🔗 常用連結  │
    └─────────────┴─────────────┴─────────────┘
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

        # Rich Menu 尺寸（寬2500，高843 為 LINE 標準大尺寸）
        rich_menu_request = RichMenuRequest(
            size=RichMenuSize(width=2500, height=843),
            selected=True,  # 預設展開
            name="主選單",
            chat_bar_text="📋 點我開啟功能選單",
            areas=[
                # 第一排
                RichMenuArea(
                    bounds=RichMenuBounds(x=0,    y=0, width=833, height=421),
                    action=MessageAction(label="選課資訊", text="選課"),
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=833,  y=0, width=834, height=421),
                    action=MessageAction(label="最新公告", text="公告"),
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1667, y=0, width=833, height=421),
                    action=MessageAction(label="高雄天氣", text="天氣"),
                ),
                # 第二排
                RichMenuArea(
                    bounds=RichMenuBounds(x=0,    y=421, width=833, height=422),
                    action=MessageAction(label="GPA計算", text="GPA"),
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
        logger.info("Rich Menu 建立成功：%s", rich_menu_id)

        # 上傳圖片
        image_path = os.path.join(os.path.dirname(__file__), "..", "data", "rich_menu.png")
        if os.path.exists(image_path):
            with ApiClient(configuration) as blob_client:
                blob_api = MessagingApiBlob(blob_client)
                with open(image_path, "rb") as f:
                    blob_api.set_rich_menu_image(
                        rich_menu_id=rich_menu_id,
                        body=f.read(),
                        _headers={"Content-Type": "image/png"},
                    )
            logger.info("Rich Menu 圖片上傳成功")
        else:
            logger.warning("找不到 rich_menu.png，將使用預設外觀（無圖片）")

        # 設為預設 Rich Menu（所有用戶都會看到）
        line_bot_api.set_default_rich_menu(rich_menu_id=rich_menu_id)
        logger.info("已設為預設 Rich Menu")

        return rich_menu_id


def delete_all_rich_menus() -> None:
    """刪除所有已建立的 Rich Menu（重設用）。"""
    from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
    from app.config import settings

    configuration = Configuration(access_token=settings.line_channel_access_token)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        menus = line_bot_api.get_rich_menu_list()
        for menu in menus.richmenus:
            line_bot_api.delete_rich_menu(rich_menu_id=menu.rich_menu_id)
            logger.info("已刪除 Rich Menu：%s", menu.rich_menu_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 從專案根目錄執行：python app/rich_menu.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from dotenv import load_dotenv
    load_dotenv()

    print("🔄 刪除舊的 Rich Menu...")
    delete_all_rich_menus()

    print("🔄 建立新的 Rich Menu...")
    menu_id = create_rich_menu()
    if menu_id:
        print(f"✅ Rich Menu 設定完成！ID: {menu_id}")
        print("📱 重新開啟 LINE 對話就能看到選單")
    else:
        print("❌ Rich Menu 建立失敗，請檢查 .env 設定")
