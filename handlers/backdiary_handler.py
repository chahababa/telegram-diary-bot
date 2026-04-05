"""
補記過去日記處理模組 — /backdiary

操作流程：
  選擇日期 → 輸入內容（/done 結束）→ 補填問卷（可略過）→ 生成日記（可稍後）

限制：
  00:00–05:59 禁止使用，避免與「深夜記錄自動歸前日」邏輯衝突
"""

import logging
import re
from datetime import timedelta, datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from models.database import Database
from services.scheduler_service import get_now

logger = logging.getLogger(__name__)

# ── 狀態常數 ──────────────────────────────────
(
    BACKDIARY_DATE,
    BACKDIARY_INPUT,
    BACKDIARY_SURVEY_CHOICE,
    BACKDIARY_SURVEY_IMPORTANT,
    BACKDIARY_SURVEY_GRAT_1,
    BACKDIARY_SURVEY_GRAT_2,
    BACKDIARY_SURVEY_GRAT_3,
    BACKDIARY_SURVEY_MOOD,
    BACKDIARY_SURVEY_EXTRA,
    BACKDIARY_DIARY_CHOICE,
) = range(10)

MOOD_KEYBOARD = ReplyKeyboardMarkup(
    [["-2 😢", "-1 😔", "0 😐", "+1 🙂", "+2 😄"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)


# ── 日期鍵盤 ──────────────────────────────────

def _get_date_keyboard() -> InlineKeyboardMarkup:
    """產生最近 14 天的日期選擇 Inline Keyboard（不含今天）"""
    today = get_now().date()
    buttons = []
    row = []
    for i in range(1, 15):
        d = today - timedelta(days=i)
        label = f"{d.month}/{d.day}"
        row.append(InlineKeyboardButton(label, callback_data=f"bd:{d.isoformat()}"))
        if len(row) == 7:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── 入口 ──────────────────────────────────────

async def cmd_backdiary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """入口：/backdiary — 補記過去日記"""
    now = get_now()
    if 0 <= now.hour < 6:
        await update.message.reply_text(
            "🌙 補記功能在 00:00–05:59 暫時關閉，\n"
            "請於 06:00 後使用（避免日期歸屬混亂）。"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📅 *補記過去日記*\n\n"
        "請點選要補記的日期，\n"
        "或直接輸入日期（格式：YYYY-MM-DD）：",
        parse_mode="Markdown",
        reply_markup=_get_date_keyboard(),
    )
    return BACKDIARY_DATE


# ── 日期選擇 ──────────────────────────────────

async def handle_date_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 Inline Keyboard 日期點選"""
    query = update.callback_query
    await query.answer()

    date_str = query.data.split(":", 1)[1]
    context.user_data["backdiary_date"] = date_str
    context.user_data["backdiary_entries"] = []

    await query.edit_message_text(
        f"📅 已選擇 *{date_str}*\n\n"
        "請開始輸入當天的記錄內容，\n"
        "可以分多則訊息傳送，完成後輸入 /done。\n\n"
        "（輸入 /cancel 取消）",
        parse_mode="Markdown",
    )
    return BACKDIARY_INPUT


async def handle_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理手動輸入的日期文字"""
    text = update.message.text.strip()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        await update.message.reply_text(
            "⚠️ 格式不正確，請使用 YYYY-MM-DD。\n"
            "例如：2026-03-31\n\n"
            "也可以直接點選上方的日期按鈕。"
        )
        return BACKDIARY_DATE

    try:
        target = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("⚠️ 日期不合法，請重新輸入。")
        return BACKDIARY_DATE

    today = get_now().date()
    if target >= today:
        await update.message.reply_text("⚠️ 只能補記今天以前的日期，請重新選擇。")
        return BACKDIARY_DATE

    context.user_data["backdiary_date"] = text
    context.user_data["backdiary_entries"] = []

    await update.message.reply_text(
        f"📅 已選擇 *{text}*\n\n"
        "請開始輸入當天的記錄內容，\n"
        "可以分多則訊息傳送，完成後輸入 /done。\n\n"
        "（輸入 /cancel 取消）",
        parse_mode="Markdown",
    )
    return BACKDIARY_INPUT


# ── 內容輸入 ──────────────────────────────────

async def handle_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收補記內容訊息"""
    text = update.message.text.strip()
    if "backdiary_entries" not in context.user_data:
        context.user_data["backdiary_entries"] = []
    context.user_data["backdiary_entries"].append(text)
    n = len(context.user_data["backdiary_entries"])
    await update.message.reply_text(
        f"✅ 第 {n} 則已收到。\n繼續傳送，或輸入 /done 完成。"
    )
    return BACKDIARY_INPUT


async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/done — 完成輸入，存入 DB，詢問是否補填問卷"""
    entries = context.user_data.get("backdiary_entries", [])
    diary_date = context.user_data.get("backdiary_date")

    if not entries:
        await update.message.reply_text(
            "⚠️ 尚未輸入任何內容，請先傳送記錄再輸入 /done。"
        )
        return BACKDIARY_INPUT

    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")

    for entry_text in entries:
        db.add_entry(user_id, entry_text, "text", now_str, diary_date)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 補填問卷", callback_data="bd_survey:yes"),
        InlineKeyboardButton("略過", callback_data="bd_survey:no"),
    ]])

    await update.message.reply_text(
        f"✅ 已儲存 {len(entries)} 筆記錄到 *{diary_date}*！\n\n"
        "是否要補填當天的晚間問卷？",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return BACKDIARY_SURVEY_CHOICE


# ── 問卷選擇 ──────────────────────────────────

async def handle_survey_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理是否補填問卷的 Inline 按鈕"""
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]

    if choice == "no":
        await query.edit_message_text("✅ 已略過問卷。")
        return await _ask_gen_diary(update, context)

    await query.edit_message_text(
        "📝 *補填晚間問卷*\n\n"
        "❓ *那天最重要的一件事是什麼？*\n"
        "（輸入 /skip 跳過此題，/cancel 結束）",
        parse_mode="Markdown",
    )
    return BACKDIARY_SURVEY_IMPORTANT


# ── 問卷步驟 ──────────────────────────────────

async def sv_important(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    diary_date = context.user_data["backdiary_date"]
    survey = db.get_or_create_summary(user_id, diary_date)
    db.update_survey_field(survey.id, "most_important", update.message.text.strip())
    await update.message.reply_text("🙏 *感恩的第 1 件事？*", parse_mode="Markdown")
    return BACKDIARY_SURVEY_GRAT_1


async def sv_skip_to_grat1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏭️ 已跳過。\n\n🙏 *感恩的第 1 件事？*", parse_mode="Markdown"
    )
    return BACKDIARY_SURVEY_GRAT_1


async def sv_grat1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    diary_date = context.user_data["backdiary_date"]
    survey = db.get_or_create_summary(user_id, diary_date)
    db.update_survey_field(survey.id, "gratitude_1", update.message.text.strip())
    await update.message.reply_text("🙏 *感恩的第 2 件事？*", parse_mode="Markdown")
    return BACKDIARY_SURVEY_GRAT_2


async def sv_skip_to_grat2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏭️ 已跳過。\n\n🙏 *感恩的第 2 件事？*", parse_mode="Markdown"
    )
    return BACKDIARY_SURVEY_GRAT_2


async def sv_grat2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    diary_date = context.user_data["backdiary_date"]
    survey = db.get_or_create_summary(user_id, diary_date)
    db.update_survey_field(survey.id, "gratitude_2", update.message.text.strip())
    await update.message.reply_text("🙏 *感恩的第 3 件事？*", parse_mode="Markdown")
    return BACKDIARY_SURVEY_GRAT_3


async def sv_skip_to_grat3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏭️ 已跳過。\n\n🙏 *感恩的第 3 件事？*", parse_mode="Markdown"
    )
    return BACKDIARY_SURVEY_GRAT_3


async def sv_grat3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    diary_date = context.user_data["backdiary_date"]
    survey = db.get_or_create_summary(user_id, diary_date)
    db.update_survey_field(survey.id, "gratitude_3", update.message.text.strip())
    await update.message.reply_text(
        "😊 *心情評分？*\n請選擇 -2 到 +2：",
        parse_mode="Markdown",
        reply_markup=MOOD_KEYBOARD,
    )
    return BACKDIARY_SURVEY_MOOD


async def sv_skip_to_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏭️ 已跳過。\n\n😊 *心情評分？*\n請選擇 -2 到 +2：",
        parse_mode="Markdown",
        reply_markup=MOOD_KEYBOARD,
    )
    return BACKDIARY_SURVEY_MOOD


async def sv_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    diary_date = context.user_data["backdiary_date"]
    text = update.message.text.strip()
    try:
        score = int(text.split()[0])
        if not (-2 <= score <= 2):
            raise ValueError
    except (ValueError, IndexError):
        await update.message.reply_text(
            "⚠️ 請輸入 -2 到 +2 之間的數字。",
            reply_markup=MOOD_KEYBOARD,
        )
        return BACKDIARY_SURVEY_MOOD
    survey = db.get_or_create_summary(user_id, diary_date)
    db.update_survey_field(survey.id, "mood_score", score)
    await update.message.reply_text(
        "📝 *還有什麼想補充的嗎？*\n（沒有的話輸入「沒有」或 /skip）",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return BACKDIARY_SURVEY_EXTRA


async def sv_skip_to_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏭️ 已跳過。\n\n📝 *還有什麼想補充的嗎？*\n（沒有的話輸入「沒有」或 /skip）",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return BACKDIARY_SURVEY_EXTRA


async def sv_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    diary_date = context.user_data["backdiary_date"]
    text = update.message.text.strip()
    if text.lower() not in ("沒有", "無", "沒", "no", "none"):
        survey = db.get_or_create_summary(user_id, diary_date)
        db.update_survey_field(survey.id, "additional_notes", text)
    # 完成問卷
    survey = db.get_or_create_summary(user_id, diary_date)
    db.update_survey_field(survey.id, "completed", 1)
    await update.message.reply_text("✅ 問卷已完成！")
    return await _ask_gen_diary(update, context)


async def sv_skip_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """跳過補充內容，直接完成問卷"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    diary_date = context.user_data["backdiary_date"]
    survey = db.get_or_create_summary(user_id, diary_date)
    db.update_survey_field(survey.id, "completed", 1)
    await update.message.reply_text("✅ 問卷已完成！")
    return await _ask_gen_diary(update, context)


# ── 生成日記 ──────────────────────────────────

async def _ask_gen_diary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """詢問是否立即生成日記（可從 callback_query 或 message 呼叫）"""
    diary_date = context.user_data.get("backdiary_date")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📔 生成日記", callback_data="bd_gen:yes"),
        InlineKeyboardButton("稍後再說", callback_data="bd_gen:no"),
    ]])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"是否要現在生成 *{diary_date}* 的日記？",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return BACKDIARY_DIARY_CHOICE


async def handle_gen_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理生成日記的確認按鈕"""
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]
    diary_date = context.user_data.get("backdiary_date")
    user_id = update.effective_user.id

    if choice == "no":
        await query.edit_message_text(
            f"好的！稍後可用 /diary {diary_date} 來生成日記。"
        )
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(
        f"📔 正在生成 *{diary_date}* 的日記，請稍候...",
        parse_mode="Markdown",
    )

    db: Database = context.bot_data["db"]
    ai = context.bot_data["ai"]
    from templates.diary_template import DIARY_TEMPLATE
    from services.gdrive_service import upload_diary, is_available, save_diary_locally

    entries = db.get_entries_by_date(user_id, diary_date)
    survey = db.get_survey(user_id, diary_date)

    new_content = await ai.generate_diary(diary_date, entries, survey, DIARY_TEMPLATE)

    # 若原本已有日記，補充在下方；若無，直接建立
    existing = db.get_diary(user_id, diary_date)
    now_time = get_now()
    now_str = now_time.isoformat()
    now_label = now_time.strftime("%Y-%m-%d %H:%M")

    if existing:
        combined = (
            existing["content"]
            + f"\n\n---\n\n## 📎 補充記錄（{now_label} 補記）\n\n"
            + new_content
        )
    else:
        combined = new_content

    db.save_diary(user_id, diary_date, combined, now_str)

    # 上傳 Drive（並存：帶時間戳避免覆蓋原檔）
    timestamp = now_time.strftime("%Y%m%d_%H%M%S")
    drive_date_str = f"{diary_date}_補充_{timestamp}"
    file_id = await upload_diary(drive_date_str, combined)
    if file_id:
        upload_status = "✅ 已上傳至 Google Drive（並存新檔）"
    elif is_available():
        await save_diary_locally(drive_date_str, combined)
        upload_status = "⚠️ Drive 上傳失敗，已本地暫存"
    else:
        upload_status = "ℹ️ Google Drive 未設定"

    # 回傳補充日記給使用者
    header = f"📔 *{diary_date} 的補充日記*\n{upload_status}\n\n"
    full_msg = header + new_content

    if len(full_msg) <= 4096:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=full_msg,
            parse_mode="Markdown",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=header,
            parse_mode="Markdown",
        )
        for i in range(0, len(new_content), 4000):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=new_content[i:i + 4000],
            )

    context.user_data.clear()
    return ConversationHandler.END


# ── 取消 ──────────────────────────────────────

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ 補記已取消。",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ── 建立 ConversationHandler ──────────────────

def get_backdiary_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("backdiary", cmd_backdiary)],
        states={
            BACKDIARY_DATE: [
                CallbackQueryHandler(handle_date_cb, pattern="^bd:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_text),
            ],
            BACKDIARY_INPUT: [
                CommandHandler("done", handle_done),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_content),
            ],
            BACKDIARY_SURVEY_CHOICE: [
                CallbackQueryHandler(handle_survey_choice, pattern="^bd_survey:"),
            ],
            BACKDIARY_SURVEY_IMPORTANT: [
                CommandHandler("skip", sv_skip_to_grat1),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sv_important),
            ],
            BACKDIARY_SURVEY_GRAT_1: [
                CommandHandler("skip", sv_skip_to_grat2),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sv_grat1),
            ],
            BACKDIARY_SURVEY_GRAT_2: [
                CommandHandler("skip", sv_skip_to_grat3),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sv_grat2),
            ],
            BACKDIARY_SURVEY_GRAT_3: [
                CommandHandler("skip", sv_skip_to_mood),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sv_grat3),
            ],
            BACKDIARY_SURVEY_MOOD: [
                CommandHandler("skip", sv_skip_to_extra),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sv_mood),
            ],
            BACKDIARY_SURVEY_EXTRA: [
                CommandHandler("skip", sv_skip_extra),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sv_extra),
            ],
            BACKDIARY_DIARY_CHOICE: [
                CallbackQueryHandler(handle_gen_choice, pattern="^bd_gen:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", handle_cancel)],
        per_user=True,
        per_chat=True,
    )
