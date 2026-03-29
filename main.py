"""
Telegram 日記助理 Bot — 主程式
每天隨時記錄文字/語音，每晚自動彙整成結構化 Markdown 日記。
"""

import logging
import sys
from pathlib import Path

from telegram import BotCommand
from telegram.ext import ApplicationBuilder

from config import TELEGRAM_BOT_TOKEN, validate_config, LOCAL_BACKUP_DIR
from handlers.command_handlers import register_command_handlers
from handlers.message_handlers import register_message_handlers
from handlers.survey_handlers import SurveyManager
from models.database import Database
from services.ai_service import AIService
from services.drive_service import DriveService
from services.scheduler_service import SchedulerService
from templates.diary_template import REMINDER_MESSAGES, DIARY_TEMPLATE

# ── 日誌設定 ──────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── 排程回呼函式 ──────────────────────────────

async def scheduled_reminder(app):
    """定時提醒所有使用者記日記"""
    db: Database = app.bot_data["db"]
    scheduler: SchedulerService = app.bot_data["scheduler"]

    user_ids = db.get_all_user_ids()
    hour = scheduler.get_now().hour
    message = REMINDER_MESSAGES.get(hour, "📝 記得記錄今天的生活喔！")

    for user_id in user_ids:
        try:
            await app.bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.error(f"提醒使用者 {user_id} 失敗: {e}")


async def scheduled_diary_generation(app):
    """00:00 自動為所有使用者產出日記"""
    db: Database = app.bot_data["db"]
    ai: AIService = app.bot_data["ai"]
    drive: DriveService = app.bot_data["drive"]
    scheduler: SchedulerService = app.bot_data["scheduler"]

    # 產出的是「昨天」的日記
    from datetime import timedelta
    now = scheduler.get_now()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    user_ids = db.get_all_user_ids()
    logger.info(f"開始產出 {yesterday} 的日記，使用者數: {len(user_ids)}")

    for user_id in user_ids:
        try:
            entries = db.get_entries_by_date(user_id, yesterday)
            survey = db.get_survey(user_id, yesterday)

            # 生成日記
            diary_content = await ai.generate_diary(
                yesterday, entries, survey, DIARY_TEMPLATE
            )

            # 儲存
            now_str = now.isoformat()
            db.save_diary(user_id, yesterday, diary_content, now_str)

            # 上傳 Google Drive
            file_id = await drive.upload_diary(yesterday, diary_content)
            if file_id:
                db.mark_diary_uploaded(user_id, yesterday)
                upload_msg = "✅ 已上傳至 Google Drive"
            elif drive.is_available():
                upload_msg = "⚠️ Google Drive 上傳失敗，已本地暫存"
            else:
                upload_msg = "ℹ️ 已本地暫存"

            # 傳送日記給使用者
            header = f"📔 **{yesterday} 的日記已產出！**\n{upload_msg}\n\n"
            full_msg = header + diary_content

            if len(full_msg) <= 4096:
                await app.bot.send_message(
                    chat_id=user_id, text=full_msg, parse_mode="Markdown"
                )
            else:
                await app.bot.send_message(
                    chat_id=user_id, text=header, parse_mode="Markdown"
                )
                for i in range(0, len(diary_content), 4000):
                    await app.bot.send_message(
                        chat_id=user_id, text=diary_content[i:i + 4000]
                    )

            logger.info(f"使用者 {user_id} 的 {yesterday} 日記已產出")

        except Exception as e:
            logger.error(f"產出使用者 {user_id} 日記失敗: {e}")


# ── 應用程式初始化 ─────────────────────────────

async def post_init(app):
    """Bot 啟動後的初始化工作"""
    # 設定 Bot 指令選單
    commands = [
        BotCommand("start", "開始使用日記助理"),
        BotCommand("today", "查看今天的記錄數量"),
        BotCommand("score", "查看近 7 天心情趨勢"),
        BotCommand("diary", "手動產出今天的日記"),
        BotCommand("status", "查看 Bot 運作狀態"),
        BotCommand("survey", "手動開始問卷"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot 指令選單已設定")

    # 啟動排程服務
    scheduler: SchedulerService = app.bot_data["scheduler"]
    survey_manager: SurveyManager = app.bot_data["survey_manager"]

    scheduler.set_callbacks(
        reminder_callback=lambda: scheduled_reminder(app),
        survey_callback=lambda: survey_manager.trigger_survey_for_all(app),
        survey_timeout_callback=lambda: survey_manager.timeout_survey_for_all(app),
        diary_callback=lambda: scheduled_diary_generation(app),
    )
    scheduler.start()
    logger.info("所有排程已啟動")


async def post_shutdown(app):
    """Bot 關閉時的清理工作"""
    scheduler: SchedulerService = app.bot_data["scheduler"]
    scheduler.stop()
    logger.info("Bot 已關閉")


def main():
    """主程式進入點"""
    # 驗證設定
    missing = validate_config()
    if missing:
        logger.error(f"缺少必要的環境變數: {', '.join(missing)}")
        logger.error("請確認 .env 檔案中已設定以上變數")
        sys.exit(1)

    # 建立暫存目錄
    Path(LOCAL_BACKUP_DIR).mkdir(parents=True, exist_ok=True)

    # 初始化各服務
    db = Database()
    ai = AIService()
    drive = DriveService()
    scheduler = SchedulerService()
    survey_manager = SurveyManager()

    logger.info("所有服務初始化完成")

    # 建立 Telegram Bot 應用程式
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # 注入共用服務到 bot_data
    app.bot_data["db"] = db
    app.bot_data["ai"] = ai
    app.bot_data["drive"] = drive
    app.bot_data["scheduler"] = scheduler
    app.bot_data["survey_manager"] = survey_manager

    # 註冊處理器（順序重要：ConversationHandler 需優先）
    app.add_handler(survey_manager.get_conversation_handler(), group=0)
    register_command_handlers(app)
    register_message_handlers(app)

    # 啟動 Bot
    logger.info("🚀 日記助理 Bot 啟動中...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
