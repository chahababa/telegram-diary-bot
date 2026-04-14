"""
排程服務模組 — 管理定時提醒、問卷觸發與日記產出排程
使用 APScheduler 實現持久化排程任務
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from telegram import Bot

import config
from models.database import get_all_user_ids, is_questionnaire_complete, get_or_create_summary, _get_db

logger = logging.getLogger(__name__)

# 全域排程器
scheduler: AsyncIOScheduler | None = None

# 全域 Bot 參考（在 main.py 初始化時設定）
_bot: Bot | None = None


def _get_survey_hour(db) -> int:
    """讀取問卷開始時間，格式錯誤時退回預設值。"""
    raw_survey = db.get_setting("survey_hour", "")
    if raw_survey:
        try:
            return int(raw_survey)
        except ValueError:
            logger.warning("survey_hour 設定格式錯誤，改用預設值")
    return config.SURVEY_HOUR


def init_scheduler(bot: Bot):
    """
    初始化排程器

    Args:
        bot: Telegram Bot 實例
    """
    global scheduler, _bot
    _bot = bot

    tz = ZoneInfo(config.TIMEZONE)

    # 使用與 diary_bot.db 相同的目錄存放 scheduler_jobs.db
    db_dir = Path(config.DATABASE_PATH).parent
    scheduler_db_path = db_dir / "scheduler_jobs.db"

    # 使用 SQLite 作為持久化 jobstore，確保 Bot 重啟後排程不遺失
    jobstores = {
        "default": SQLAlchemyJobStore(url=f"sqlite:///{scheduler_db_path}")
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone=tz,
    )
    
    db = _get_db()
    raw_hours = db.get_setting("reminder_hours", "")
    if raw_hours:
        try:
            reminder_hours = [int(x.strip()) for x in raw_hours.split(",")]
        except ValueError:
            reminder_hours = config.REMINDER_HOURS
    else:
        reminder_hours = config.REMINDER_HOURS

    survey_hour = _get_survey_hour(db)

    # 註冊定時提醒（每 3 小時）
    for hour in reminder_hours:
        scheduler.add_job(
            send_reminder,
            "cron",
            hour=hour,
            minute=0,
            id=f"reminder_{hour}",
            replace_existing=True,
            name=f"每日 {hour}:00 提醒",
        )

    # 註冊 23:00 問卷
    scheduler.add_job(
        send_questionnaire,
        "cron",
        hour=survey_hour,
        minute=0,
        id="questionnaire_23",
        replace_existing=True,
        name=f"{survey_hour}:00 結算問卷",
    )

    # 問卷開始後 50 分鐘自動結算，避免與自訂 survey_hour 脫鉤
    scheduler.add_job(
        auto_close_questionnaire,
        "cron",
        hour=survey_hour,
        minute=50,
        id="questionnaire_timeout",
        replace_existing=True,
        name=f"{survey_hour}:50 問卷超時結算",
    )

    # 註冊 00:00 日記產出
    scheduler.add_job(
        trigger_diary_generation,
        "cron",
        hour=config.DIARY_GENERATION_HOUR,
        minute=0,
        id="diary_generation_00",
        replace_existing=True,
        name="00:00 日記產出",
    )

    scheduler.start()
    logger.info("排程器已啟動，所有排程任務已註冊")


async def send_reminder():
    """
    發送定時提醒給所有使用者
    """
    if _bot is None:
        logger.error("Bot 尚未初始化")
        return

    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    time_str = now.strftime("%H:%M")
    current_hour = now.hour

    user_ids = get_all_user_ids()
    logger.info(f"發送提醒：{time_str}，共 {len(user_ids)} 位使用者")
    
    db = _get_db()
    custom_msg = db.get_setting(f"reminder_msg_{current_hour}", "")
    msg_text = custom_msg if custom_msg else f"📝 現在是 {time_str}，記一下你這幾個小時做了什麼吧！"

    for user_id in user_ids:
        try:
            await _bot.send_message(
                chat_id=user_id,
                text=msg_text,
            )
        except Exception as e:
            logger.warning(f"無法發送提醒給使用者 {user_id}：{e}")


async def send_questionnaire():
    """
    發送 23:00 結算問卷給所有使用者
    """
    if _bot is None:
        logger.error("Bot 尚未初始化")
        return

    tz = ZoneInfo(config.TIMEZONE)
    today = datetime.now(tz).strftime("%Y-%m-%d")

    user_ids = get_all_user_ids()
    logger.info(f"發送結算問卷：{today}，共 {len(user_ids)} 位使用者")

    for user_id in user_ids:
        try:
            # 建立或取得當日摘要
            get_or_create_summary(user_id, today)

            await _bot.send_message(
                chat_id=user_id,
                text=(
                    "🌙 今天辛苦了！讓我們來回顧一下今天吧～\n\n"
                    "👉 請輸入 /survey 開始今日回顧問卷"
                ),
            )
            logger.info(f"已發送結算問卷提醒給 {user_id}")
        except Exception as e:
            logger.warning(f"無法發送問卷給使用者 {user_id}：{e}")


async def auto_close_questionnaire():
    """
    23:50 超時機制 — 未完成的問卷以現有資料自動結算
    """
    if _bot is None:
        return

    tz = ZoneInfo(config.TIMEZONE)
    today = datetime.now(tz).strftime("%Y-%m-%d")

    user_ids = get_all_user_ids()

    for user_id in user_ids:
        if not is_questionnaire_complete(user_id, today):
            try:
                from models.database import update_summary_field
                # 將問卷標記為完成，讓日記產出時能納入已回答的部分
                update_summary_field(user_id, today, "completed", 1)

                await _bot.send_message(
                    chat_id=user_id,
                    text="⏰ 問卷回覆時間已截止，將以目前收集到的資料產出日記。",
                )
                logger.info(f"使用者 {user_id} 問卷超時自動結算")
            except Exception as e:
                logger.warning(f"無法通知使用者 {user_id} 問卷超時：{e}")


async def trigger_diary_generation():
    """
    00:00 觸發日記產出
    """
    if _bot is None:
        return

    tz = ZoneInfo(config.TIMEZONE)
    # 產出的是「昨天」的日記
    yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")

    user_ids = get_all_user_ids()
    logger.info(f"觸發日記產出：{yesterday}，共 {len(user_ids)} 位使用者")

    for user_id in user_ids:
        try:
            from services.diary_service import generate_diary
            from services.gdrive_service import upload_diary, save_diary_locally
            from models.database import update_summary_field, is_diary_generated

            # 避免重複產出
            if is_diary_generated(user_id, yesterday):
                logger.info(f"使用者 {user_id} 的 {yesterday} 日記已存在，跳過")
                continue

            # 產出日記
            diary = await generate_diary(user_id, yesterday)

            # 傳送至 Telegram
            # Telegram 訊息長度限制為 4096 字元
            if len(diary) <= 4096:
                await _bot.send_message(chat_id=user_id, text=diary, parse_mode=None)
            else:
                # 分段傳送
                chunks = [diary[i:i + 4000] for i in range(0, len(diary), 4000)]
                for chunk in chunks:
                    await _bot.send_message(chat_id=user_id, text=chunk, parse_mode=None)

            # 上傳至 Google Drive
            file_id = await upload_diary(yesterday, diary)
            if file_id:
                update_summary_field(user_id, yesterday, "diary_uploaded", True)
                await _bot.send_message(
                    chat_id=user_id,
                    text="✅ 日記已同步儲存至 Google Drive！",
                    parse_mode=None,
                )
            else:
                # 上傳失敗，暫存本地
                local_path = await save_diary_locally(yesterday, diary)
                await _bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ Google Drive 上傳失敗，日記已暫存至本地：{local_path}",
                    parse_mode=None,
                )

        except Exception as e:
            error_detail = f"{type(e).__name__}: {e}"
            if hasattr(e, 'status_code'):
                error_detail += f" (status={e.status_code})"
            if hasattr(e, 'body'):
                error_detail += f" body={e.body}"
            logger.error(f"使用者 {user_id} 日記產出失敗：{error_detail}")
            try:
                await _bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ 日記產出失敗\n\n錯誤詳情：{error_detail}",
                    parse_mode=None,
                )
            except Exception:
                pass


def shutdown_scheduler():
    """關閉排程器"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("排程器已關閉")

def get_now() -> datetime:
    tz = ZoneInfo(config.TIMEZONE)
    return datetime.now(tz)

def get_diary_date(now_dt: datetime = None) -> str:
    """取得目前的日記歸屬日期
    如果目前時間在 00:00~03:59 之間，則歸屬前一天的日記。
    """
    if now_dt is None:
        now_dt = get_now()
    if now_dt.hour < 4:
        return (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    return now_dt.strftime("%Y-%m-%d")

def get_jobs_info() -> list[dict]:
    """取得目前排程任務的資訊"""
    global scheduler
    if not scheduler:
        return []
    jobs = []
    tz = ZoneInfo(config.TIMEZONE)
    for job in scheduler.get_jobs():
        next_run = "未定"
        if job.next_run_time:
            next_run = job.next_run_time.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run,
        })
    return jobs
