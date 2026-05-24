"""
config.py — 環境變數與全域設定
使用 pydantic-settings 自動讀取 .env 檔案
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── LINE Bot ──────────────────────────────────────────
    line_channel_secret: str = Field(..., env="LINE_CHANNEL_SECRET")
    line_channel_access_token: str = Field(..., env="LINE_CHANNEL_ACCESS_TOKEN")

    # ── 資料庫 ────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite:///./data/nsysu_bot.db",
        env="DATABASE_URL",
    )

    # ── 爬蟲 ──────────────────────────────────────────────
    crawler_interval_minutes: int = Field(default=30, env="CRAWLER_INTERVAL_MINUTES")
    nsysu_mis_url: str = Field(
        default="https://mis.nsysu.edu.tw/news",
        env="NSYSU_MIS_URL",
    )

    # ── 廣播 ──────────────────────────────────────────────
    enable_broadcast: bool = Field(default=True, env="ENABLE_BROADCAST")

    # ── NLP ───────────────────────────────────────────────
    nlp_similarity_threshold: float = Field(
        default=0.15, env="NLP_SIMILARITY_THRESHOLD"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全域單例
settings = Settings()
