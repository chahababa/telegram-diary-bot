"""
Telegram 日記助理 Bot — 主程式
每天隨時記錄文字/語音，每晚自動彙整成結構化 Markdown 日記。
"""

import logging
import sys
import warnings
from pathlib import Path

from telegram import BotCommand
from telegram.warnings import PTBUserWarning
from telegram.ext import ApplicationBuilder

from config import TELEGRAM_BOT_TOKEN, validate_config, LOCAL_BACKUP_DIR
from handlers.admin_handlers import register_admin_handlers
from handlers.backdiary_handler import get_backdiary_handler
from handlers.command_handlers import register_command_handlers
from handlers.editdiary_handler import get_editdiary_handler
from handlers.message_handlers import register_message_handlers
from handlers.survey_handlers import SurveyManager
from models.database import Database
from services.ai_service import AIService
from templates.diary_template import REMINDER_MESSAGES, DIARY_TEMPLATE

# ── 日誌設定 ──────────────────────────────────

if hasattr(sys.stdout, "reconfigure"):
    # Windows cp950 終端無法穩定輸出 emoji，改用容錯模式避免記錄流程中斷。
    sys.stdout.reconfigure(errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="backslashreplace")

warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message\..*",
    category=PTBUserWarning,
)

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


# ── 應用程式初始化 ─────────────────────────────

async def post_init(app):
    """Bot 啟動後的初始化工作"""
    # 設定 Bot 指令選單
    commands = [
        BotCommand("start", "開始使用日記助理"),
        BotCommand("today", "查看今天的記錄數量"),
        BotCommand("score", "查看近 7 天心情趨勢"),
        BotCommand("diary", "手動產出今天的日記"),
        BotCommand("backdiary", "📅 補記過去日期的日記"),
        BotCommand("editdiary", "✏️ 調整過去日期的日記"),
        BotCommand("status", "查看 Bot 運作狀態"),
        BotCommand("survey", "手動開始問卷"),
        BotCommand("admin", "管理員設定選單"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot 指令選單已設定")

    # 啟動排程服務
    from services.scheduler_service import init_scheduler
    init_scheduler(app.bot)


async def post_shutdown(app):
    """Bot 關閉時的清理工作"""
    from services.scheduler_service import shutdown_scheduler
    shutdown_scheduler()
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
    app.bot_data["survey_manager"] = survey_manager

    # 註冊處理器（順序重要：ConversationHandler 需優先）
    app.add_handler(survey_manager.get_conversation_handler(), group=0)
    app.add_handler(get_backdiary_handler(), group=0)
    app.add_handler(get_editdiary_handler(), group=0)
    register_command_handlers(app)
    register_admin_handlers(app)
    register_message_handlers(app)

    # 啟動 Bot
    logger.info("🚀 日記助理 Bot 啟動中...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
