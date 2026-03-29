"""
排程服務模組 — 使用 APScheduler 管理定時任務
"""

import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import TIMEZONE, REMINDER_HOURS, SURVEY_HOUR, SURVEY_TIMEOUT_MINUTE, DIARY_GENERATION_HOUR

logger = logging.getLogger(__name__)


class SchedulerService:
    """非同步排程服務"""

    def __init__(self):
        self.tz = pytz.timezone(TIMEZONE)
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self._reminder_callback = None
        self._survey_callback = None
        self._survey_timeout_callback = None
        self._diary_callback = None

    def set_callbacks(
        self,
        reminder_callback,
        survey_callback,
        survey_timeout_callback,
        diary_callback,
    ):
        """設定各排程的回呼函式"""
        self._reminder_callback = reminder_callback
        self._survey_callback = survey_callback
        self._survey_timeout_callback = survey_timeout_callback
        self._diary_callback = diary_callback

    def start(self):
        """啟動排程器並註冊所有排程任務"""
        # 1. 定時提醒記日記（09:00, 12:00, 15:00, 18:00, 21:00）
        for hour in REMINDER_HOURS:
            self.scheduler.add_job(
                self._reminder_callback,
                CronTrigger(hour=hour, minute=0, timezone=self.tz),
                id=f"reminder_{hour}",
                name=f"日記提醒 {hour}:00",
                replace_existing=True,
            )
            logger.info(f"已註冊提醒排程: {hour:02d}:00")

        # 2. 23:00 結算問卷
        self.scheduler.add_job(
            self._survey_callback,
            CronTrigger(hour=SURVEY_HOUR, minute=0, timezone=self.tz),
            id="survey_start",
            name="結算問卷開始",
            replace_existing=True,
        )
        logger.info(f"已註冊問卷排程: {SURVEY_HOUR:02d}:00")

        # 3. 23:50 問卷超時自動結算
        self.scheduler.add_job(
            self._survey_timeout_callback,
            CronTrigger(hour=SURVEY_HOUR, minute=SURVEY_TIMEOUT_MINUTE, timezone=self.tz),
            id="survey_timeout",
            name="問卷超時結算",
            replace_existing=True,
        )
        logger.info(f"已註冊問卷超時排程: {SURVEY_HOUR:02d}:{SURVEY_TIMEOUT_MINUTE:02d}")

        # 4. 00:00 自動產出日記
        self.scheduler.add_job(
            self._diary_callback,
            CronTrigger(hour=DIARY_GENERATION_HOUR, minute=0, timezone=self.tz),
            id="diary_generation",
            name="日記自動產出",
            replace_existing=True,
        )
        logger.info(f"已註冊日記產出排程: {DIARY_GENERATION_HOUR:02d}:00")

        self.scheduler.start()
        logger.info("排程服務已啟動")

    def stop(self):
        """停止排程器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("排程服務已停止")

    def get_now(self) -> datetime:
        """取得台灣時區的當前時間"""
        return datetime.now(self.tz)

    def get_today_str(self) -> str:
        """取得今天的日期字串 YYYY-MM-DD"""
        return self.get_now().strftime("%Y-%m-%d")

    def get_diary_date(self) -> str:
        """
        取得歸屬日期。
        如果現在是 00:00~04:59，歸屬前一天（處理跨日情境）。
        """
        now = self.get_now()
        if now.hour < 5:
            from datetime import timedelta
            return (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return now.strftime("%Y-%m-%d")

    def get_jobs_info(self) -> list[dict]:
        """取得所有排程任務資訊"""
        jobs = self.scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
            }
            for job in jobs
        ]
