"""指令處理模組：/start, /today, /score, /status"""

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


async def cmd_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /score 指令：設定心情分數（-2 到 2）"""
    today = datetime.now(tz).strftime("%Y-%m-%d")

    if not context.args:
        await update.message.reply_text("📌 使用方式：/score <分數>\n分數範圍：-2（很差）到 2（很好）")
        return

    try:
        score = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ 請輸入整數，範圍 -2 到 2。")
        return

    if score < -2 or score > 2:
        await update.message.reply_text("⚠️ 分數範圍是 -2 到 2，請重新輸入。")
        return

    db.get_or_create_summary(today)
    db.update_summary_field(today, "mood_score", score)

    score_labels = {-2: "😢 很差", -1: "😕 不太好", 0: "😐 普通", 1: "🙂 不錯", 2: "😄 很好"}
    label = score_labels.get(score, str(score))
    await update.message.reply_text(f"🎭 今日心情分數已設定為：{label}")
    logger.info(f"心情分數已更新: {today} = {score}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /status 指令：顯示今日狀態摘要"""
    today = datetime.now(tz).strftime("%Y-%m-%d")

    # 紀錄筆數
    entries = db.get_entries_by_date(today)
    text_count = sum(1 for e in entries if e["source_type"] == "text")
    voice_count = sum(1 for e in entries if e["source_type"] == "voice")

    # 問卷與心情
    summary = db.get_summary(today)
    settings = db.get_settings()
    template = settings.get("questionnaire_template", [])
    total_questions = len(template)

    if summary:
        q_step = summary.get("questionnaire_step", 0)
        mood = summary.get("mood_score")
        diary_done = bool(summary.get("diary_output"))
        uploaded = summary.get("diary_uploaded", False)
    else:
        q_step = 0
        mood = None
        diary_done = False
        uploaded = False

    # 組合狀態訊息
    score_labels = {-2: "😢 很差", -1: "😕 不太好", 0: "😐 普通", 1: "🙂 不錯", 2: "😄 很好"}
    mood_str = score_labels.get(mood, "未設定") if mood is not None else "未設定"

    if q_step >= total_questions and total_questions > 0:
        q_status = "✅ 已完成"
    elif q_step > 0:
        q_status = f"⏳ 進行中（{q_step}/{total_questions}）"
    else:
        q_status = "⬜ 未開始"

    diary_str = "✅ 已產出" if diary_done else "⬜ 未產出"
    upload_str = "✅ 已上傳" if uploaded else "⬜ 未上傳"

    lines = [
        f"📊 {today} 狀態摘要\n",
        f"📝 文字紀錄：{text_count} 筆",
        f"🎤 語音紀錄：{voice_count} 筆",
        f"📋 問卷進度：{q_status}",
        f"🎭 心情分數：{mood_str}",
        f"📖 日記產出：{diary_str}",
        f"☁️ 雲端上傳：{upload_str}",
    ]

    await update.message.reply_text("\n".join(lines))
