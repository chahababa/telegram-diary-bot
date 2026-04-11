"""
Google Calendar 行程回顧處理模組 — /calendar

操作流程：
  取得今日行程 → 逐一詢問進行狀況（預設「有做」，可標記「沒做」）
  → 儲存為當天記錄 → 詢問是否立即產出日記
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from models.database import Database
from services.scheduler_service import get_diary_date, get_now

logger = logging.getLogger(__name__)

# ── 狀態常數 ──────────────────────────────────
(
    GCAL_FEEDBACK,    # 等待使用者回應當前行程
    GCAL_GEN_CHOICE,  # 詢問是否立即產出日記
) = range(2)


# ── 工具函式 ──────────────────────────────────

def _format_event_prompt(event: dict) -> str:
    """產生詢問單一行程狀況的訊息文字"""
    title = event["title"]
    start = event["start_time"]

    if start == "全天":
        time_label = "全天行程"
    else:
        end = event["end_time"]
        time_label = f"{start}–{end}" if end else start

    return (
        f"📅 *{time_label}*｜*{title}*\n\n"
        "這個行程進行得怎麼樣？\n"
        "直接回覆心得，或輸入「沒做」跳過此行程。\n\n"
        "（輸入 /skip 跳過，/cancel 結束回顧）"
    )


def _format_event_entry(event: dict, feedback: str) -> str:
    """將行程與使用者回饋組合為日記記錄內容"""
    title = event["title"]
    start = event["start_time"]

    if start == "全天":
        time_label = "全天"
    else:
        time_label = start

    if feedback == "沒做":
        return f"[行程回顧] {time_label}《{title}》：（未進行）"
    else:
        return f"[行程回顧] {time_label}《{title}》：{feedback}"


async def _ask_next_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """詢問下一個行程，若全部問完則進入日記生成步驟"""
    events: list = context.user_data["gcal_events"]
    index: int = context.user_data["gcal_index"]

    if index >= len(events):
        # 全部行程問完，詢問是否產出日記
        saved_count = context.user_data.get("gcal_saved_count", 0)
        diary_date = context.user_data.get("gcal_diary_date")

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📔 產出日記", callback_data="gcal_gen:yes"),
            InlineKeyboardButton("稍後再說", callback_data="gcal_gen:no"),
        ]])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"✅ 所有行程回顧完成！已儲存 {saved_count} 筆記錄。\n\n"
                f"是否要現在產出 *{diary_date}* 的日記？"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return GCAL_GEN_CHOICE

    # 詢問目前行程
    event = events[index]
    progress = f"（{index + 1}/{len(events)}）"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{progress}\n\n{_format_event_prompt(event)}",
        parse_mode="Markdown",
    )
    return GCAL_FEEDBACK


# ── 入口 ──────────────────────────────────────

async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """入口：/calendar — 開始今日行程回顧"""
    from services.gcal_service import is_available, get_today_events

    if not is_available():
        await update.message.reply_text(
            "⚠️ Google Calendar 尚未設定。\n\n"
            "請先完成以下設定：\n"
            "1. 在 .env 中加入 `GCAL_CALENDAR_ID`（通常填入你的 Gmail 信箱）\n"
            "2. 將 Google Calendar 分享給 Service Account 的 email\n\n"
            "詳細步驟請參考專案說明文件。"
        )
        return ConversationHandler.END

    diary_date = get_diary_date()

    await update.message.reply_text("🗓️ 正在讀取今天的行程，請稍候...")

    try:
        events = await get_today_events(diary_date=diary_date)
    except Exception as e:
        logger.error(f"取得 Google Calendar 行程失敗：{e}")
        await update.message.reply_text(
            "⚠️ 無法讀取 Google Calendar 行程。\n\n"
            "可能原因：\n"
            "• Service Account 尚未被分享行程存取權\n"
            "• GCAL_CALENDAR_ID 設定有誤\n"
            "• 網路或 API 錯誤\n\n"
            f"錯誤詳情：{type(e).__name__}: {e}"
        )
        return ConversationHandler.END

    if not events:
        await update.message.reply_text(
            "📭 今天的 Google Calendar 沒有任何行程。\n\n"
            "如果你覺得應該有行程，請確認：\n"
            "• 行程是否在正確的日曆中\n"
            "• GCAL_CALENDAR_ID 設定是否正確"
        )
        return ConversationHandler.END

    context.user_data["gcal_events"] = events
    context.user_data["gcal_index"] = 0
    context.user_data["gcal_saved_count"] = 0
    context.user_data["gcal_diary_date"] = diary_date

    await update.message.reply_text(
        f"🗓️ 找到今天 *{diary_date}* 共 *{len(events)}* 個行程。\n\n"
        "我會逐一詢問每個行程的狀況，請直接回覆心得，\n"
        "或輸入「沒做」標記此行程未進行。",
        parse_mode="Markdown",
    )

    return await _ask_next_event(update, context)


# ── 行程回饋處理 ──────────────────────────────

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收使用者對當前行程的回饋，儲存後詢問下一個"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    events: list = context.user_data["gcal_events"]
    index: int = context.user_data["gcal_index"]
    diary_date: str = context.user_data["gcal_diary_date"]

    feedback = update.message.text.strip()
    event = events[index]
    entry_content = _format_event_entry(event, feedback)

    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    db.add_entry(user_id, entry_content, "text", now_str, diary_date)
    context.user_data["gcal_saved_count"] = context.user_data.get("gcal_saved_count", 0) + 1

    if feedback == "沒做":
        await update.message.reply_text("⏭️ 已記錄為未進行。")
    else:
        await update.message.reply_text("✅ 已記錄！")

    context.user_data["gcal_index"] = index + 1
    return await _ask_next_event(update, context)


async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/skip — 跳過當前行程，不儲存任何記錄"""
    events: list = context.user_data["gcal_events"]
    index: int = context.user_data["gcal_index"]

    event = events[index]
    await update.message.reply_text(
        f"⏭️ 已跳過《{event['title']}》（不記錄）。"
    )

    context.user_data["gcal_index"] = index + 1
    return await _ask_next_event(update, context)


# ── 日記生成確認 ──────────────────────────────

async def handle_gen_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理是否立即產出日記的 Inline 按鈕"""
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]
    diary_date = context.user_data.get("gcal_diary_date")

    if choice == "no":
        await query.edit_message_text(
            f"好的！稍後可用 /diary 來產出今天的日記。"
        )
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(
        f"📔 正在產出 *{diary_date}* 的日記，請稍候...",
        parse_mode="Markdown",
    )

    db: Database = context.bot_data["db"]
    ai = context.bot_data["ai"]
    user_id = update.effective_user.id

    from services.diary_service import get_diary_template
    from services.gdrive_service import upload_diary, is_available, save_diary_locally

    entries = db.get_entries_by_date(user_id, diary_date)
    survey = db.get_survey(user_id, diary_date)

    try:
        diary_content = await ai.generate_diary(
            diary_date,
            entries,
            survey,
            get_diary_template(),
        )

        now_time = get_now()
        now_str = now_time.isoformat()
        db.save_diary(user_id, diary_date, diary_content, now_str)

        file_id = await upload_diary(diary_date, diary_content)
        if file_id:
            db.mark_diary_uploaded(user_id, diary_date)
            upload_status = "✅ 已上傳至 Google Drive"
        elif is_available():
            await save_diary_locally(diary_date, diary_content)
            upload_status = "⚠️ Drive 上傳失敗，已本地暫存"
        else:
            upload_status = "ℹ️ Google Drive 未設定"

        header = f"📔 *{diary_date} 的日記*\n{upload_status}\n\n"
        full_msg = header + diary_content

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
            for i in range(0, len(diary_content), 4000):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=diary_content[i:i + 4000],
                )

    except Exception as e:
        logger.error(f"Calendar 行程回顧後產出日記失敗（使用者 {user_id}，日期 {diary_date}）：{e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"⚠️ 日記產出時發生錯誤：{type(e).__name__}\n\n"
                "行程記錄已儲存，稍後可用 /diary 重新產出。"
            ),
        )

    context.user_data.clear()
    return ConversationHandler.END


# ── 取消 ──────────────────────────────────────

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cancel — 取消行程回顧"""
    saved = context.user_data.get("gcal_saved_count", 0)
    context.user_data.clear()

    msg = "❌ 行程回顧已取消。"
    if saved > 0:
        msg += f"\n（已儲存的 {saved} 筆記錄不會消失）"

    await update.message.reply_text(msg)
    return ConversationHandler.END


# ── 建立 ConversationHandler ──────────────────

def get_gcal_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("calendar", cmd_calendar)],
        states={
            GCAL_FEEDBACK: [
                CommandHandler("skip", handle_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_feedback),
            ],
            GCAL_GEN_CHOICE: [
                CallbackQueryHandler(handle_gen_choice, pattern="^gcal_gen:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", handle_cancel)],
        per_user=True,
        per_chat=True,
    )
