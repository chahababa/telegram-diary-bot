"""
調整過去日記處理模組 — /editdiary

操作流程：
  選擇有日記的日期 → 選擇動作（查看/補充）→ 輸入補充內容（/done）→ 確認重新生成

版本歷史：
  重新生成前自動將舊版存入 diary_history 資料表
Google Drive：
  覆蓋同名檔案（Drive 本身保留版本歷史）
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from models.database import Database
from services.scheduler_service import get_now

logger = logging.getLogger(__name__)

# ── 狀態常數 ──────────────────────────────────
(
    EDITDIARY_DATE,
    EDITDIARY_ACTION,
    EDITDIARY_INPUT,
    EDITDIARY_CONFIRM,
) = range(4)


# ── 日期鍵盤 ──────────────────────────────────

def _get_diary_date_keyboard(db: Database, user_id: int):
    """顯示有已生成日記的日期列表（最近 14 筆）"""
    dates = db.get_diary_dates_with_diary(user_id, limit=14)
    if not dates:
        return None
    buttons = [
        [InlineKeyboardButton(d, callback_data=f"ed:{d}")]
        for d in dates
    ]
    return InlineKeyboardMarkup(buttons)


# ── 入口 ──────────────────────────────────────

async def cmd_editdiary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """入口：/editdiary — 調整過去日記"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    keyboard = _get_diary_date_keyboard(db, user_id)
    if keyboard is None:
        await update.message.reply_text(
            "📭 目前沒有已產出的日記可以調整。\n"
            "完成一天的記錄後，可用 /diary 手動生成。"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📖 *調整過去日記*\n\n請選擇要調整的日期：",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return EDITDIARY_DATE


# ── 日期選擇 ──────────────────────────────────

async def handle_edit_date_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理日期選擇"""
    query = update.callback_query
    await query.answer()

    date_str = query.data.split(":", 1)[1]
    context.user_data["editdiary_date"] = date_str
    context.user_data["editdiary_entries"] = []

    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    entry_count = db.get_entry_count_by_date(user_id, date_str)
    diary = db.get_diary(user_id, date_str)
    gen_time = diary["created_at"][:16] if diary else "未知"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ 新增補充內容", callback_data="ed_action:add")],
        [InlineKeyboardButton("📖 查看目前日記", callback_data="ed_action:view")],
    ])

    await query.edit_message_text(
        f"📖 *{date_str}* 的日記\n\n"
        f"共有 {entry_count} 筆記錄，日記生成於 {gen_time}\n\n"
        "你想怎麼做？",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return EDITDIARY_ACTION


# ── 動作選擇 ──────────────────────────────────

async def handle_edit_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理查看 / 新增補充的選擇"""
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]
    diary_date = context.user_data.get("editdiary_date")

    if action == "end":
        context.user_data.clear()
        await query.edit_message_text("✅ 已結束。")
        return ConversationHandler.END

    if action == "view":
        db: Database = context.bot_data["db"]
        user_id = update.effective_user.id
        diary = db.get_diary(user_id, diary_date)

        if not diary:
            await query.edit_message_text("⚠️ 找不到這天的日記內容。")
            return ConversationHandler.END

        content = diary["content"]
        await query.edit_message_text(
            f"📖 *{diary_date} 的日記*（以下分段傳送）",
            parse_mode="Markdown",
        )
        # 分段傳送日記全文
        for i in range(0, len(content), 4000):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=content[i:i + 4000],
            )

        # 看完後再詢問是否補充
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ 新增補充內容", callback_data="ed_action:add"),
            InlineKeyboardButton("❌ 結束", callback_data="ed_action:end"),
        ]])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="是否要新增補充內容？",
            reply_markup=keyboard,
        )
        return EDITDIARY_ACTION

    # action == "add"
    await query.edit_message_text(
        f"✏️ 請輸入要補充到 *{diary_date}* 的內容。\n"
        "可以分多則訊息傳送，完成後輸入 /done。\n\n"
        "（輸入 /cancel 取消）",
        parse_mode="Markdown",
    )
    return EDITDIARY_INPUT


# ── 內容輸入 ──────────────────────────────────

async def handle_edit_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收補充內容訊息"""
    text = update.message.text.strip()
    if "editdiary_entries" not in context.user_data:
        context.user_data["editdiary_entries"] = []
    context.user_data["editdiary_entries"].append(text)
    n = len(context.user_data["editdiary_entries"])
    await update.message.reply_text(
        f"✅ 第 {n} 則已收到。\n繼續傳送，或輸入 /done 完成。"
    )
    return EDITDIARY_INPUT


async def handle_edit_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/done — 完成補充輸入，詢問是否重新生成日記"""
    entries = context.user_data.get("editdiary_entries", [])
    diary_date = context.user_data.get("editdiary_date")

    if not entries:
        await update.message.reply_text(
            "⚠️ 尚未輸入任何補充內容，請先傳送內容再輸入 /done。"
        )
        return EDITDIARY_INPUT

    # 先存入 DB
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id
    now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    for entry_text in entries:
        db.add_entry(user_id, entry_text, "text", now_str, diary_date)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 確認重新生成", callback_data="ed_confirm:yes"),
        InlineKeyboardButton("❌ 取消", callback_data="ed_confirm:no"),
    ]])

    await update.message.reply_text(
        f"已儲存 {len(entries)} 筆補充內容到 *{diary_date}*。\n\n"
        "⚠️ 是否要重新生成這天的日記？\n"
        "舊版本將自動備份到 DB 版本歷史，\n"
        "Google Drive 同名檔案將被覆蓋。",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return EDITDIARY_CONFIRM


# ── 確認重新生成 ──────────────────────────────

async def handle_edit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """確認或取消重新生成日記"""
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":")[1]
    diary_date = context.user_data.get("editdiary_date")
    user_id = update.effective_user.id

    if choice == "no":
        await query.edit_message_text(
            f"✅ 已取消重新生成。\n"
            f"補充內容已儲存，可之後用 /diary {diary_date} 重新生成。"
        )
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(
        f"🔄 正在重新生成 *{diary_date}* 的日記，請稍候...",
        parse_mode="Markdown",
    )

    db: Database = context.bot_data["db"]
    ai = context.bot_data["ai"]
    from services.diary_service import get_diary_template
    from services.gdrive_service import upload_diary_overwrite, is_available, save_diary_locally

    # 將舊版本存入歷史記錄
    db.save_diary_to_history(user_id, diary_date)

    # 重新生成（含所有記錄＋補充內容）
    entries = db.get_entries_by_date(user_id, diary_date)
    survey = db.get_survey(user_id, diary_date)
    new_content = await ai.generate_diary(
        diary_date,
        entries,
        survey,
        get_diary_template(),
    )

    now_str = get_now().isoformat()
    db.save_diary(user_id, diary_date, new_content, now_str)

    # 覆蓋上傳至 Drive
    file_id = await upload_diary_overwrite(diary_date, new_content)
    if file_id:
        upload_status = "✅ 已覆蓋上傳至 Google Drive"
    elif is_available():
        await save_diary_locally(diary_date, new_content)
        upload_status = "⚠️ Drive 上傳失敗，已本地暫存"
    else:
        upload_status = "ℹ️ Google Drive 未設定"

    header = f"📔 *{diary_date} 更新後的日記*\n{upload_status}\n\n"
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

async def handle_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ 操作已取消。")
    return ConversationHandler.END


# ── 建立 ConversationHandler ──────────────────

def get_editdiary_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("editdiary", cmd_editdiary)],
        states={
            EDITDIARY_DATE: [
                CallbackQueryHandler(handle_edit_date_cb, pattern="^ed:"),
            ],
            EDITDIARY_ACTION: [
                CallbackQueryHandler(handle_edit_action, pattern="^ed_action:"),
            ],
            EDITDIARY_INPUT: [
                CommandHandler("done", handle_edit_done),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_content),
            ],
            EDITDIARY_CONFIRM: [
                CallbackQueryHandler(handle_edit_confirm, pattern="^ed_confirm:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", handle_edit_cancel)],
        per_user=True,
        per_chat=True,
    )
