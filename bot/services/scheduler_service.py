"""排程管理模組：定時提醒、問卷觸發、自動結算"""

import logging
from datetime import datetime
import zoneinfo
from telegram.ext import Application
from bot.config import TIMEZONE
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

tz = zoneinfo.ZoneInfo(TIMEZONE)

# 儲存 chat_id，在使用者第一次互動時設定
_chat_id: int | None = None


def set_chat_id(chat_id: int) -> None:
    """設定使用者的 chat_id（由 handler 呼叫）"""
    global _chat_id
    _chat_id = chat_id


def get_chat_id() -> int | None:
    """取得使用者的 chat_id"""
    return _chat_id


def get_questionnaire_data(app: Application) -> dict:
    """從 bot_data 取得問卷狀態"""
    return app.bot_data.setdefault("questionnaire", {})


def init_scheduler(app: Application) -> None:
    """初始化排程：設定每分鐘檢查一次是否需要發送提醒或問卷"""
    job_queue = app.job_queue

    # 每分鐘檢查一次提醒
    job_queue.run_repeating(
        check_and_send_reminder,
        interval=60,
        first=10,
        name="reminder_check",
    )

    # 每分鐘檢查一次問卷觸發
    job_queue.run_repeating(
        check_and_send_questionnaire,
        interval=60,
        first=15,
        name="questionnaire_check",
    )

    # 每分鐘檢查一次問卷超時
    job_queue.run_repeating(
        check_questionnaire_timeout,
        interval=60,
        first=20,
        name="questionnaire_timeout_check",
    )

    logger.info("排程器已初始化")


async def check_and_send_reminder(context) -> None:
    """檢查是否需要發送提醒"""
    chat_id = get_chat_id()
    if not chat_id:
        return

    now = datetime.now(tz)
    current_hour = now.hour

    # 從 Supabase 讀取最新設定
    settings = db.get_settings()
    reminder_hours = settings.get("reminder_hours", [9, 12, 15, 18, 21])

    if current_hour not in reminder_hours:
        return

    # 檢查是否已發送過這個時段的提醒
    state = db.get_scheduler_state()
    last_sent = state.get("last_reminder_sent")
    if last_sent:
        last_sent_dt = datetime.fromisoformat(last_sent)
        if hasattr(last_sent_dt, 'tzinfo') and last_sent_dt.tzinfo:
            last_sent_local = last_sent_dt.astimezone(tz)
        else:
            last_sent_local = last_sent_dt.replace(tzinfo=tz)
        # 同一天同一小時不重複發送
        if last_sent_local.date() == now.date() and last_sent_local.hour == current_hour:
            return

    # 發送提醒
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"💡 提醒你記錄一下現在的生活片段！\n（現在是 {current_hour}:00，隨時傳文字或語音給我）",
    )

    # 更新狀態
    db.update_scheduler_state("last_reminder_sent", now.isoformat())
    logger.info(f"已發送 {current_hour}:00 提醒")


async def check_and_send_questionnaire(context) -> None:
    """檢查是否需要觸發問卷"""
    chat_id = get_chat_id()
    if not chat_id:
        return

    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")

    # 從 Supabase 讀取最新設定
    settings = db.get_settings()
    questionnaire_hour = settings.get("questionnaire_hour", 23)

    if now.hour != questionnaire_hour:
        return

    # 檢查今天是否已發送過問卷
    state = db.get_scheduler_state()
    last_sent = state.get("last_questionnaire_sent")
    if last_sent == today:
        return

    # 檢查問卷是否已完成
    if db.is_questionnaire_complete(today):
        return

    # 用 bot_data 儲存問卷狀態
    from bot.handlers.questionnaire_handler import start_questionnaire
    q_data = get_questionnaire_data(context.application)
    await start_questionnaire(context.bot, chat_id, q_data)

    # 更新狀態
    db.update_scheduler_state("last_questionnaire_sent", today)
    logger.info(f"已觸發 {today} 問卷")


async def check_questionnaire_timeout(context) -> None:
    """檢查問卷是否超時（問卷觸發時間的第 50 分鐘自動結算）"""
    chat_id = get_chat_id()
    if not chat_id:
        return

    now = datetime.now(tz)
    settings = db.get_settings()
    questionnaire_hour = settings.get("questionnaire_hour", 23)

    # 在問卷觸發時間的第 50 分鐘結算
    if now.hour != questionnaire_hour or now.minute < 50 or now.minute > 51:
        return

    q_data = get_questionnaire_data(context.application)
    if not q_data.get("active", False):
        return

    from bot.handlers.questionnaire_handler import auto_close_questionnaire
    await auto_close_questionnaire(context.bot, chat_id, q_data)
    logger.info("問卷超時自動結算")
