"""
Google Calendar 服務模組 — 讀取使用者今天的 Google Calendar 行程

使用與 Google Drive 相同的 Service Account 憑證。
使用前需先將 Google Calendar 分享給 Service Account 的 email。
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import pytz

import config

logger = logging.getLogger(__name__)

# Google Calendar API 範圍（唯讀）
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_calendar_service():
    """建立 Google Calendar API 服務實例（使用 Service Account 憑證）"""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    # 優先從環境變數讀取（Zeabur / 雲端部署用）
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON") or config.GOOGLE_CREDENTIALS_JSON
    if credentials_json:
        info = json.loads(credentials_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # 本地開發：從檔案讀取
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE,
            scopes=SCOPES,
        )
    return build("calendar", "v3", credentials=creds)


def has_calendar_credentials() -> bool:
    """檢查 Google Calendar 憑證是否存在"""
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON") or config.GOOGLE_CREDENTIALS_JSON
    if credentials_json:
        try:
            json.loads(credentials_json)
            return True
        except json.JSONDecodeError:
            logger.warning("GOOGLE_CREDENTIALS_JSON 不是合法 JSON，無法使用 Google Calendar")
            return False
    return Path(config.GOOGLE_CREDENTIALS_FILE).is_file()


def is_available() -> bool:
    """檢查 Google Calendar 服務是否可用（有憑證且有設定 Calendar ID）"""
    return has_calendar_credentials() and bool(config.GCAL_CALENDAR_ID)


async def get_today_events(diary_date: str | None = None) -> list[dict]:
    """
    取得指定日期的 Google Calendar 行程列表。

    Args:
        diary_date: 要查詢的日記日期（格式 YYYY-MM-DD）。
                    若為 None，則使用今天的實際日期。
                    凌晨 00:00–03:59 呼叫時應傳入 get_diary_date() 的回傳值，
                    確保行程日期與日記歸屬日期一致。

    Returns:
        行程列表，每筆 dict 包含：
            - title (str): 行程名稱
            - start_time (str): 開始時間，格式 "HH:MM"；全天行程為 "全天"
            - end_time (str): 結束時間，格式 "HH:MM"；全天行程為 ""
            - description (str): 行程描述（可能為空）
            - event_id (str): Google Calendar 事件 ID

    Raises:
        Exception: 若 API 呼叫失敗
    """
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)

    if diary_date:
        # 使用指定的日記歸屬日期（處理凌晨 00:00–03:59 記錄歸前日的情境）
        target = datetime.strptime(diary_date, "%Y-%m-%d")
        day_start = now.replace(
            year=target.year, month=target.month, day=target.day,
            hour=0, minute=0, second=0, microsecond=0,
        )
        day_end = now.replace(
            year=target.year, month=target.month, day=target.day,
            hour=23, minute=59, second=59, microsecond=999999,
        )
    else:
        # 預設使用今天的實際日期
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    time_min = day_start.isoformat()
    time_max = day_end.isoformat()

    service = _get_calendar_service()

    events_result = await asyncio.to_thread(
        lambda: service.events().list(
            calendarId=config.GCAL_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute()
    )

    raw_events = events_result.get("items", [])
    events = []

    for e in raw_events:
        start = e.get("start", {})
        end = e.get("end", {})

        if "dateTime" in start:
            # 有具體時間的行程
            start_dt = datetime.fromisoformat(start["dateTime"]).astimezone(tz)
            end_dt = datetime.fromisoformat(end["dateTime"]).astimezone(tz)
            start_str = start_dt.strftime("%H:%M")
            end_str = end_dt.strftime("%H:%M")
        else:
            # 全天行程（只有 date 欄位）
            start_str = "全天"
            end_str = ""

        events.append({
            "title": e.get("summary", "（未命名行程）"),
            "start_time": start_str,
            "end_time": end_str,
            "description": e.get("description", ""),
            "event_id": e.get("id", ""),
        })

    logger.info(f"取得今天 Google Calendar 行程：{len(events)} 筆")
    return events
