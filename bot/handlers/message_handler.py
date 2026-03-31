"""訊息處理模組：文字訊息、不支援的媒體"""

import logging
from datetime import datetime
import zoneinfo
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import TIMEZONE
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

tz = zoneinfo.ZoneInfo(TIMEZONE)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理文字訊息：存入 Supabase 並回覆確認"""
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    content = update.message.text

    # 存入資料庫
    db.add_entry(date_str, time_str, content, "text")

    # 計算今日第幾筆
    count = db.count_entries_by_date(date_str)

    await update.message.reply_text(f"📝 已記錄（今日第 {count} 筆）")
    logger.info(f"已記錄文字訊息: {content[:30]}...")


async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理不支援的訊息類型（圖片、貼圖、影片等）"""
    await update.message.reply_text("⚠️ 目前只支援文字和語音訊息喔！")
