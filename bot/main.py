"""Telegram 日記助理 Bot — 主入口"""

import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from bot.config import TELEGRAM_BOT_TOKEN
from bot.utils.logger import setup_logger
from bot.utils.error_handler import error_handler
from bot.handlers.command_handler import cmd_start, cmd_today
from bot.handlers.message_handler import handle_text_message, handle_voice_message, handle_unsupported

# 初始化 logger
setup_logger()
logger = logging.getLogger(__name__)


def main():
    """啟動 Bot"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN 未設定，請檢查 .env 檔案")
        return

    logger.info("正在啟動日記助理 Bot...")

    # 建立 Application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # 註冊指令處理
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))

    # 註冊文字訊息處理（排除指令）
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # 註冊語音訊息處理
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # 註冊不支援的訊息類型處理（圖片、貼圖、影片、文件等）
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.Sticker.ALL | filters.VIDEO | filters.Document.ALL | filters.ANIMATION,
        handle_unsupported,
    ))

    # 註冊全域錯誤處理
    app.add_error_handler(error_handler)

    logger.info("Bot 已啟動，開始接收訊息...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
