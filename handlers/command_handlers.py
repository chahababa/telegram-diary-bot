"""
指令處理模組 — 處理 /start, /today, /score, /diary, /status 等指令
"""

import logging

from telegram import Update, BotCommand
from telegram.ext import ContextTypes, CommandHandler, Application

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /start 指令 — 歡迎訊息"""
    user = update.effective_user
    welcome = (
        f"👋 嗨 {user.first_name}！歡迎使用**日記助理 Bot**！\n\n"
        "📝 你可以隨時傳送**文字**或**語音訊息**給我，我會幫你記錄下來。\n\n"
        "⏰ 每天我會在以下時間提醒你記日記：\n"
        "　　09:00 / 12:00 / 15:00 / 18:00 / 21:00\n\n"
        "🌙 每晚 23:00 我會問你幾個問題，幫助你回顧今天。\n"
        "📔 凌晨 00:00 我會自動產出今天的日記並上傳到 Google Drive。\n\n"
        "**可用指令：**\n"
        "/today — 查看今天的記錄數量\n"
        "/score — 查看近 7 天心情趨勢\n"
        "/diary — 手動產出今天的日記\n"
        "/status — 查看 Bot 運作狀態"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")
    logger.info(f"使用者 {user.id} ({user.first_name}) 啟動了 Bot")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /today 指令 — 查看今天的記錄統計"""
    from services.scheduler_service import get_diary_date
    from models.database import Database

    db: Database = context.bot_data["db"]

    user_id = update.effective_user.id
    diary_date = get_diary_date()
    count = db.get_entry_count_by_date(user_id, diary_date)
    entries = db.get_entries_by_date(user_id, diary_date)

    if count == 0:
        msg = f"📋 **{diary_date}** 的記錄\n\n目前還沒有任何記錄喔！\n\n隨時傳送文字或語音給我吧 🎤"
    else:
        text_count = sum(1 for e in entries if e.entry_type == "text")
        voice_count = sum(1 for e in entries if e.entry_type == "voice")
        msg = (
            f"📋 **{diary_date}** 的記錄統計\n\n"
            f"　📝 文字記錄：{text_count} 則\n"
            f"　🎤 語音記錄：{voice_count} 則\n"
            f"　📊 總計：{count} 則\n\n"
            f"繼續加油！晚上 23:00 會有結算問卷 🌙"
        )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /score 指令 — 近 7 天心情趨勢"""
    from models.database import Database

    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    scores = db.get_mood_scores(user_id, limit=7)

    if not scores:
        await update.message.reply_text("📊 目前還沒有心情評分記錄。\n完成今晚的問卷後就會有了！")
        return

    mood_emoji = {-2: "😢", -1: "😔", 0: "😐", 1: "🙂", 2: "😄"}
    lines = ["📊 **近 7 天心情趨勢**\n"]
    for s in reversed(scores):  # 由舊到新
        emoji = mood_emoji.get(s["mood_score"], "❓")
        bar = "█" * (s["mood_score"] + 3)  # -2→1格, +2→5格
        lines.append(f"　{s['diary_date']} {emoji} {bar} ({s['mood_score']:+d})")

    # 計算平均
    avg = sum(s["mood_score"] for s in scores) / len(scores)
    lines.append(f"\n　平均心情：{avg:+.1f}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /diary 指令 — 手動產出今天的日記"""
    from models.database import Database
    from services.ai_service import AIService
    from services.gdrive_service import upload_diary, is_available
    from services.scheduler_service import get_diary_date, get_now
    from templates.diary_template import DIARY_TEMPLATE

    db: Database = context.bot_data["db"]
    ai: AIService = context.bot_data["ai"]

    user_id = update.effective_user.id
    diary_date = get_diary_date()

    await update.message.reply_text(f"📔 正在產出 {diary_date} 的日記，請稍候...")

    # 取得資料
    entries = db.get_entries_by_date(user_id, diary_date)
    survey = db.get_survey(user_id, diary_date)

    # 生成日記
    diary_content = await ai.generate_diary(diary_date, entries, survey, DIARY_TEMPLATE)

    # 儲存到資料庫
    now_str = get_now().isoformat()
    db.save_diary(user_id, diary_date, diary_content, now_str)

    # 上傳到 Google Drive
    file_id = await upload_diary(diary_date, diary_content)
    if file_id:
        db.mark_diary_uploaded(user_id, diary_date)
        upload_status = "✅ 已上傳至 Google Drive"
    elif is_available():
        upload_status = "⚠️ Google Drive 上傳失敗，已本地暫存"
    else:
        upload_status = "ℹ️ Google Drive 未設定，已本地暫存"

    # 回傳日記
    # Telegram 訊息上限 4096 字元，超過需分段
    header = f"📔 **{diary_date} 的日記**\n{upload_status}\n\n"
    full_msg = header + diary_content

    if len(full_msg) <= 4096:
        await update.message.reply_text(full_msg, parse_mode="Markdown")
    else:
        # 分段傳送
        await update.message.reply_text(header, parse_mode="Markdown")
        for i in range(0, len(diary_content), 4000):
            chunk = diary_content[i:i + 4000]
            await update.message.reply_text(chunk)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /status 指令 — 查看 Bot 運作狀態"""
    from services.scheduler_service import get_now, get_jobs_info
    from services.gdrive_service import is_available
    from models.database import Database

    db: Database = context.bot_data["db"]

    now = get_now()
    jobs = get_jobs_info()

    # 系統狀態
    drive_status = "✅ 已連線" if is_available() else "❌ 未設定"

    lines = [
        "🤖 **Bot 運作狀態**\n",
        f"　⏰ 目前時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣)",
        f"　📁 Google Drive：{drive_status}",
        f"　📊 已註冊排程：{len(jobs)} 個",
        "",
        "**排程任務：**",
    ]
    for job in jobs:
        lines.append(f"　• {job['name']} → 下次執行: {job['next_run']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def register_command_handlers(app: Application):
    """註冊所有指令處理器"""
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("score", cmd_score))
    app.add_handler(CommandHandler("diary", cmd_diary))
    app.add_handler(CommandHandler("status", cmd_status))

    logger.info("已註冊所有指令處理器")
