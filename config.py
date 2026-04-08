"""
設定模組 — 從 .env 載入所有環境變數與常數
"""


import os
from pathlib import Path
from dotenv import load_dotenv


# 載入 .env 檔案
load_dotenv(Path(__file__).parent / ".env")


# === Telegram Bot ===
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")


# === OpenAI API ===
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")


# === Google Drive ===
GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")  # Zeabur 雲端部署用


# === 時區 ===
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Taipei")


# === 資料庫 ===
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(Path(__file__).parent / "diary.db"))


# === 排程時間設定 ===
REMINDER_HOURS: list[int] = [9, 12, 15, 18, 21]  # 提醒記日記的時間點
SURVEY_HOUR: int = 23        # 結算問卷開始時間
SURVEY_TIMEOUT_MINUTE: int = 50  # 23:50 超時自動結算
DIARY_GENERATION_HOUR: int = 0   # 00:00 產出日記


# === GPT 模型 ===
GPT_MODEL: str = os.getenv("GPT_MODEL", "gpt-4o")

# === 語音轉文字 ===
WHISPER_MODEL: str = "whisper-1"
WHISPER_LANGUAGE: str = "zh"

# === 本地備份 ===
LOCAL_BACKUP_DIR: str = os.getenv("LOCAL_BACKUP_DIR", str(Path(__file__).parent / "backup_diaries"))


def validate_config() -> list[str]:
    """檢查必要設定是否已填寫"""
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    return missing
