"""全域錯誤處理模組"""

import logging
import traceback
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """全域錯誤處理：記錄完整錯誤並通知使用者"""
    logger.error(
        f"處理更新時發生例外: {context.error}\n"
        f"{''.join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__))}"
    )

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ 發生錯誤，請稍後再試。",
            )
        except Exception:
            logger.error("無法發送錯誤通知給使用者")
