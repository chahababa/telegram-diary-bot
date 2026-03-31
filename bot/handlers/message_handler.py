"""訊息處理模組：文字訊息、語音訊息、不支援的媒體"""

import logging
from datetime import datetime
import zoneinfo
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import TIMEZONE
from bot.db import supabase_client as db
from bot.services.voice_service import download_and_transcribe

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


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理語音訊息：下載 → Whisper 轉寫 → 存入 Supabase"""
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    await update.message.reply_text("🎙️ 語音轉寫中，請稍候...")

    try:
        text = await download_and_transcribe(update.message.voice, context.bot)
    except Exception as e:
        logger.error(f"語音轉寫失敗: {e}")
        await update.message.reply_text("❌ 語音轉寫失敗，請改用文字輸入。")
        return

    # 存入資料庫
    db.add_entry(date_str, time_str, text, "voice")
    count = db.count_entries_by_date(date_str)

    # 顯示轉寫結果前 30 字
    preview = text[:30] + "..." if len(text) > 30 else text
    await update.message.reply_text(f"🎤 語音已轉文字並記錄（今日第 {count} 筆）：「{preview}」")
    logger.info(f"已記錄語音訊息: {text[:30]}...")


async def handle_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理不支援的訊息類型（圖片、貼圖、影片等）"""
    await update.message.reply_text("⚠️ 目前只支援文字和語音訊息喔！")
