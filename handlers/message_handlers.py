"""
訊息處理模組 — 處理一般文字訊息與語音訊息
"""

import logging
import os
import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, Application, filters

from models.database import Database
from services.ai_service import AIService
from services.scheduler_service import get_now, get_diary_date

logger = logging.getLogger(__name__)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理一般文字訊息 — 存入資料庫作為日記素材"""
    # 檢查是否在問卷流程中（交由 SurveyManager 處理）
    if context.user_data.get("survey_active"):
        return  # 讓 survey_handlers 的 ConversationHandler 處理

    db: Database = context.bot_data["db"]

    user_id = update.effective_user.id
    content = update.message.text.strip()

    if not content:
        return

    now = get_now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    diary_date = get_diary_date()

    db.add_entry(user_id, content, "text", timestamp, diary_date)

    count = db.get_entry_count_by_date(user_id, diary_date)
    await update.message.reply_text(
        f"✅ 已記錄！（今天第 {count} 則）",
    )
    logger.info(f"使用者 {user_id} 新增文字記錄，日期: {diary_date}")


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理語音訊息 — Whisper 轉文字後存入資料庫"""
    db: Database = context.bot_data["db"]
    ai: AIService = context.bot_data["ai"]

    user_id = update.effective_user.id
    now = get_now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    diary_date = get_diary_date()

    await update.message.reply_text("🎤 正在辨識語音，請稍候...")

    # 下載語音檔案
    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)

    # 儲存為暫存檔
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)

    try:
        # Whisper 語音轉文字（回傳 tuple: text, error_msg）
        text, error_msg = await ai.transcribe_voice(tmp_path)

        if text:
            db.add_entry(user_id, text, "voice", timestamp, diary_date)
            count = db.get_entry_count_by_date(user_id, diary_date)
            await update.message.reply_text(
                f"🎤 語音辨識完成：\n\n「{text}」\n\n✅ 已記錄！（今天第 {count} 則）"
            )
            logger.info(f"使用者 {user_id} 新增語音記錄，日期: {diary_date}")
        else:
            # 顯示具體的錯誤原因，方便除錯
            error_detail = f"\n\n🔍 錯誤細節：{error_msg}" if error_msg else ""
            await update.message.reply_text(
                f"⚠️ 語音辨識失敗了。{error_detail}\n\n"
                "請試著用文字輸入，或重新錄一段語音試試看！"
            )
            logger.warning(f"使用者 {user_id} 語音辨識失敗: {error_msg}")
    finally:
        # 清理暫存檔
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def register_message_handlers(app: Application):
    """註冊訊息處理器（需在 ConversationHandler 之後加入，優先級較低）"""
    # 文字訊息（排除指令）
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text_message,
        ),
        group=1,  # 較低優先級，讓問卷 ConversationHandler 優先
    )

    # 語音訊息
    app.add_handler(
        MessageHandler(
            filters.VOICE,
            handle_voice_message,
        ),
        group=1,
    )

    logger.info("已註冊訊息處理器")
