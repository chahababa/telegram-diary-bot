"""Supabase 連線與 CRUD 模組"""

import json
import logging
from supabase import create_client, Client
from bot.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    """取得 Supabase client 實例（單例模式）"""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL 和 SUPABASE_KEY 必須在 .env 中設定")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client 已建立")
    return _client


def test_connection():
    """測試 Supabase 連線：讀取 bot_settings 表"""
    try:
        client = get_client()
        result = client.table("bot_settings").select("id").limit(1).execute()
        logger.info(f"Supabase 連線成功，bot_settings 資料筆數: {len(result.data)}")
        print("[OK] Supabase 連線成功！")
        return True
    except Exception as e:
        logger.error(f"Supabase 連線失敗: {e}")
        print(f"[FAIL] Supabase 連線失敗: {e}")
        return False


# === CRUD 函式 ===

def add_entry(date: str, time: str, content: str, source_type: str) -> dict:
    """新增一筆 diary_entry"""
    client = get_client()
    data = {
        "date": date,
        "time": time,
        "content": content,
        "source_type": source_type,
    }
    result = client.table("diary_entries").insert(data).execute()
    logger.info(f"已新增 entry: {date} {time} ({source_type})")
    return result.data[0]


def get_entries_by_date(date: str) -> list:
    """取得指定日期的所有 entries，按時間排序"""
    client = get_client()
    result = (
        client.table("diary_entries")
        .select("*")
        .eq("date", date)
        .order("time")
        .execute()
    )
    return result.data


def count_entries_by_date(date: str) -> int:
    """計算指定日期的 entry 數量"""
    client = get_client()
    result = (
        client.table("diary_entries")
        .select("id", count="exact")
        .eq("date", date)
        .execute()
    )
    return result.count


# === bot_settings ===

def get_settings() -> dict:
    """讀取 bot_settings（id=1）"""
    client = get_client()
    result = client.table("bot_settings").select("*").eq("id", 1).execute()
    if result.data:
        return result.data[0]
    return {}


# === daily_summaries ===

def get_or_create_summary(date: str) -> dict:
    """取得或建立當日 daily_summary"""
    client = get_client()
    result = client.table("daily_summaries").select("*").eq("date", date).execute()
    if result.data:
        return result.data[0]
    # 建立新的 summary
    new_data = {"date": date, "questionnaire_answers": {}, "questionnaire_step": 0}
    result = client.table("daily_summaries").insert(new_data).execute()
    logger.info(f"已建立 daily_summary: {date}")
    return result.data[0]


def update_summary_field(date: str, field: str, value) -> dict:
    """更新 daily_summary 的指定欄位"""
    client = get_client()
    result = (
        client.table("daily_summaries")
        .update({field: value})
        .eq("date", date)
        .execute()
    )
    logger.info(f"已更新 daily_summary {date}.{field}")
    return result.data[0] if result.data else {}


def get_summary(date: str) -> dict | None:
    """取得當日 summary，不存在則回傳 None"""
    client = get_client()
    result = client.table("daily_summaries").select("*").eq("date", date).execute()
    return result.data[0] if result.data else None


def is_questionnaire_complete(date: str) -> bool:
    """判斷問卷是否已完成"""
    summary = get_summary(date)
    if not summary:
        return False
    settings = get_settings()
    template = settings.get("questionnaire_template", [])
    return summary.get("questionnaire_step", 0) >= len(template)


# === scheduler_state ===

def get_scheduler_state() -> dict:
    """讀取排程狀態（id=1）"""
    client = get_client()
    result = client.table("scheduler_state").select("*").eq("id", 1).execute()
    if result.data:
        return result.data[0]
    # 若不存在，建立初始狀態
    new_data = {"id": 1}
    result = client.table("scheduler_state").insert(new_data).execute()
    return result.data[0]


def update_scheduler_state(field: str, value) -> None:
    """更新排程狀態的指定欄位"""
    client = get_client()
    client.table("scheduler_state").update({field: value}).eq("id", 1).execute()
    logger.info(f"已更新 scheduler_state.{field} = {value}")
