"""
指令處理模組 — 處理 /start, /today, /score, /diary, /status, /add 等指令
"""

import logging
import re
from datetime import datetime

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
        " 09:00 / 12:00 / 15:00 / 18:00 / 21:00\n\n"
        "🌙 每晚 23:00 我會問你幾個問題，幫助你回顧今天。\n"
        "📔 凌晨 00:00 我會自動產出今天的日記並上傳到 Google Drive。\n\n"
        "**可用指令：**\n"
        "/today — 查看今天的記錄數量\n"
        "/score — 查看近 7 天心情趨勢\n"
        "/diary — 手動產出今天的日記\n"
        "/diary 2026-04-02 — 產出指定日期的日記\n"
        "/add 2026-04-03 內容 — 補記指定日期的記錄\n"
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
            f" 📝 文字記錄：{text_count} 則\n"
            f" 🎤 語音記錄：{voice_count} 則\n"
            f" 📊 總計：{count} 則\n\n"
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
        lines.append(f" {s['diary_date']} {emoji} {bar} ({s['mood_score']:+d})")

    # 計算平均
    avg = sum(s["mood_score"] for s in scores) / len(scores)
    lines.append(f"\n 平均心情：{avg:+.1f}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /diary 指令 — 手動產出日記
    用法：
    /diary             -> 產出今天的日記
    /diary 2026-04-02  -> 產出指定日期的日記（補記功能）
    """
    from models.database import Database
    from services.ai_service import AIService
    from services.diary_service import get_diary_template
    from services.gdrive_service import upload_diary, is_available, save_diary_locally
    from services.scheduler_service import get_diary_date, get_now

    db: Database = context.bot_data["db"]
    ai: AIService = context.bot_data["ai"]

    user_id = update.effective_user.id

    # 解析日期參數
    args = context.args
    if args:
        date_str = args[0].strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            await update.message.reply_text(
                "⚠️ 日期格式不正確，請使用 YYYY-MM-DD。\n"
                "例如：/diary 2026-04-02"
            )
            return
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                "⚠️ 日期不合法，請確認年月日是否正確。\n"
                "例如：/diary 2026-04-02"
            )
            return
        diary_date = date_str
        is_backdated = True
    else:
        diary_date = get_diary_date()
        is_backdated = False

    # 提示訊息
    if is_backdated:
        await update.message.reply_text(
            f"📔 正在為 **{diary_date}** 補記日記，請稍候...",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"📔 正在產出 {diary_date} 的日記，請稍候...")

    # 取得資料
    entries = db.get_entries_by_date(user_id, diary_date)
    survey = db.get_survey(user_id, diary_date)

    if is_backdated and not entries and not survey:
        await update.message.reply_text(
            f"⚠️ **{diary_date}** 這天沒有任何記錄或問卷。\n\n"
            f"你可以先用以下指令補記內容，再重新產出日記：\n"
            f"/add {diary_date} 你想補記的內容",
            parse_mode="Markdown"
        )
        return

    try:
        # 生成日記
        diary_content = await ai.generate_diary(
            diary_date,
            entries,
            survey,
            get_diary_template(),
        )

        # 儲存到資料庫
        now_str = get_now().isoformat()
        db.save_diary(user_id, diary_date, diary_content, now_str)

        # 自動推送至 Notion（失敗不影響主流程）
        try:
            from services import notion_service
            if notion_service.is_available():
                mood_score = survey.mood_score if survey else None
                await notion_service.push_diary(user_id, diary_date, diary_content, mood_score)
                logger.info(f"使用者 {user_id} 的 {diary_date} 日記已推送至 Notion")
        except Exception as notion_err:
            logger.error(f"推送 Notion 失敗，不影響主流程 — user={user_id} date={diary_date}: {notion_err}")

        # 上傳到 Google Drive
        try:
            file_id = await upload_diary(diary_date, diary_content)
        except Exception as upload_err:
            logger.warning(f"Google Drive 上傳時發生例外：{upload_err}")
            file_id = None

        if file_id:
            db.mark_diary_uploaded(user_id, diary_date)
            upload_status = "✅ 已上傳至 Google Drive"
        elif is_available():
            local_path = await save_diary_locally(diary_date, diary_content)
            upload_status = f"⚠️ Google Drive 上傳失敗，已本地暫存：{local_path}"
        else:
            local_path = await save_diary_locally(diary_date, diary_content)
            upload_status = f"ℹ️ Google Drive 未設定，已本地暫存：{local_path}"

        # 明確關閉 parse_mode，避免全域預設 Markdown 解析掉 AI 內容或本地路徑。
        backdated_note = "（補記）" if is_backdated else ""
        header = f"📔 {diary_date} 的日記{backdated_note}\n{upload_status}"
        logger.info(f"準備傳送日記 header：user={user_id} date={diary_date} len={len(header)}")
        await update.message.reply_text(header, parse_mode=None)
        for i in range(0, len(diary_content), 4000):
            chunk = diary_content[i:i + 4000]
            logger.info(
                f"準備傳送日記 chunk：user={user_id} date={diary_date} index={i // 4000 + 1} len={len(chunk)}"
            )
            await update.message.reply_text(chunk, parse_mode=None)

    except Exception as e:
        error_detail = f"{type(e).__name__}: {e}"
        if hasattr(e, 'status_code'):
            error_detail += f" (status={e.status_code})"
        if hasattr(e, 'body'):
            error_detail += f" body={e.body}"
        logger.error(f"手動日記產出失敗（使用者 {user_id}，日期 {diary_date}）：{error_detail}")
        await update.message.reply_text(
            f"⚠️ 日記產出失敗\n\n錯誤詳情：{error_detail}"
        )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /add 指令 — 補記指定日期的內容
    用法：/add 2026-04-03 今天想補記的內容
    """
    from models.database import Database
    from services.scheduler_service import get_now

    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    # 參數驗證
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ 用法：/add <日期> <內容>\n\n"
            "📌 範例：\n"
            "/add 2026-04-03 今天早上去爬山，心情很好！\n\n"
            "日期格式：YYYY-MM-DD"
        )
        return

    date_str = context.args[0].strip()

    # 驗證日期格式
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        await update.message.reply_text(
            "⚠️ 日期格式不正確，請使用 YYYY-MM-DD。\n"
            "例如：/add 2026-04-03 今天的內容"
        )
        return

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "⚠️ 日期不合法，請確認年月日是否正確。\n"
            "例如：/add 2026-04-03 今天的內容"
        )
        return

    # 不允許補記未來的日期
    now = get_now()
    if target_date.date() > now.date():
        await update.message.reply_text(
            f"⚠️ 不能補記未來的日期（{date_str}）。\n"
            "請選擇今天或過去的日期。"
        )
        return

    # 組合內容（去掉第一個參數，其餘全部合併為內容）
    content = " ".join(context.args[1:]).strip()
    if not content:
        await update.message.reply_text("⚠️ 補記內容不能為空白！")
        return

    # 寫入資料庫
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    entry_id = db.add_entry(user_id, content, "text", now_str, date_str)

    count = db.get_entry_count_by_date(user_id, date_str)

    await update.message.reply_text(
        f"✅ 已補記到 **{date_str}**！（該天第 {count} 則）\n\n"
        f"📝 內容：{content}\n\n"
        f"💡 補記完成後，可以用以下指令重新產出那天的日記：\n"
        f"/diary {date_str}",
        parse_mode="Markdown"
    )
    logger.info(f"使用者 {user_id} 補記 {date_str}，entry_id: {entry_id}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /status 指令 — 查看 Bot 運作狀態"""
    from services.scheduler_service import get_now, get_jobs_info
    from services.gdrive_service import get_drive_status_async
    from services.notion_service import is_available as notion_is_available, validate_database_schema
    from models.database import Database

    db: Database = context.bot_data["db"]

    now = get_now()
    jobs = get_jobs_info()

    drive = await get_drive_status_async(validate_remote=True, timeout=8)
    if drive.available:
        drive_status = f"✅ 已連線（{drive.auth_type}）"
    elif drive.configured:
        drive_status = f"⚠️ 設定異常：{drive.message}"
    else:
        drive_status = "❌ 未設定"
    if notion_is_available():
        notion_ok, notion_errors = validate_database_schema()
        if notion_ok:
            notion_status = "✅ 已連線"
        else:
            notion_status = f"⚠️ 設定異常：{notion_errors[0]}"
    else:
        notion_status = "❌ 未設定"

    lines = [
        "🤖 **Bot 運作狀態**\n",
        f" ⏰ 目前時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣)",
        f" 📁 Google Drive：{drive_status}",
        f" 🗂 Notion：{notion_status}",
        f" 📊 已註冊排程：{len(jobs)} 個",
        "",
        "**排程任務：**",
    ]
    for job in jobs:
        lines.append(f" • {job['name']} → 下次執行: {job['next_run']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def register_command_handlers(app: Application):
    """註冊所有指令處理器"""
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("score", cmd_score))
    app.add_handler(CommandHandler("diary", cmd_diary))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("status", cmd_status))

    logger.info("已註冊所有指令處理器")
