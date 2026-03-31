"""指令處理模組：/start, /today"""

import logging
from datetime import datetime
import zoneinfo
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import TIMEZONE
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

tz = zoneinfo.ZoneInfo(TIMEZONE)

WELCOME_MESSAGE = """👋 嗨！我是你的日記助理。
隨時傳文字或語音給我，我會幫你記下來。
每晚 23:00 我會問你幾個問題回顧今天，
凌晨會自動幫你整理成一篇完整的日記。

📌 可用指令：
/today — 查看今天的紀錄
/score — 設定心情分數
/diary — 手動產出日記
/status — 查看今日狀態"""


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /start 指令：回覆歡迎訊息"""
    await update.message.reply_text(WELCOME_MESSAGE)
    logger.info(f"使用者 {update.effective_user.id} 啟動了 Bot")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /today 指令：列出今天所有紀錄"""
    today = datetime.now(tz).strftime("%Y-%m-%d")
    entries = db.get_entries_by_date(today)

    if not entries:
        await update.message.reply_text("📭 今天還沒有任何紀錄喔！")
        return

    lines = [f"📅 {today} 的紀錄（共 {len(entries)} 筆）：\n"]
    for i, entry in enumerate(entries, 1):
        icon = "🎤" if entry["source_type"] == "voice" else "📝"
        time_str = entry["time"][:5]  # HH:MM
        content = entry["content"]
        # 內容過長時截斷顯示
        if len(content) > 100:
            content = content[:100] + "..."
        lines.append(f"{i}. {icon} [{time_str}] {content}")

    await update.message.reply_text("\n".join(lines))
