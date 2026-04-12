"""
手動 Notion 同步處理模組

指令：
  /sync [日期]   — 同步指定日期（省略則為今天）的日記到 Notion
  /sync_all      — 同步所有歷史日記到 Notion，每 10 篇回報進度
"""

import asyncio
import logging
import re
from datetime import datetime

from telegram import Update, BotCommand
from telegram.ext import ContextTypes, CommandHandler, Application

from models.database import Database, _get_db

logger = logging.getLogger(__name__)


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sync [日期] — 手動同步單筆日記到 Notion

    用法：
      /sync              → 同步今天的日記
      /sync 2026-04-10   → 同步指定日期的日記
    """
    from services.notion_service import push_diary, is_available
    from services.scheduler_service import get_diary_date

    # 確認 Notion 是否已設定
    if not is_available():
        await update.message.reply_text(
            "⚠️ Notion 尚未設定。\n\n"
            "請在 .env 中加入 NOTION_TOKEN 與 NOTION_DIARY_DB_ID 後重啟 Bot。"
        )
        return

    user_id = update.effective_user.id
    db: Database = context.bot_data["db"]

    # 解析日期參數
    args = context.args
    if args:
        date_str = args[0].strip()
        # 驗證日期格式
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            await update.message.reply_text(
                "⚠️ 日期格式不正確，請使用 YYYY-MM-DD。\n"
                "例如：/sync 2026-04-10"
            )
            return
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("⚠️ 日期不合法，請確認年月日是否正確。")
            return
        diary_date = date_str
    else:
        diary_date = get_diary_date()

    # 從資料庫取得日記內容
    diary_row = db.get_diary(user_id, diary_date)
    if not diary_row:
        await update.message.reply_text(
            f"⚠️ 找不到 **{diary_date}** 的日記。\n\n"
            f"請先用 /diary {diary_date} 產出日記後再同步。",
            parse_mode="Markdown",
        )
        return

    diary_content = diary_row["content"]

    # 取得心情分數（從 surveys 表）
    survey = db.get_survey(user_id, diary_date)
    mood = survey.mood_score if survey and survey.mood_score is not None else None

    await update.message.reply_text(
        f"🔄 正在將 **{diary_date}** 的日記同步到 Notion...",
        parse_mode="Markdown",
    )

    # 呼叫 Notion 推送
    success = await push_diary(user_id, diary_date, diary_content, mood)

    if success:
        await update.message.reply_text(
            f"✅ **{diary_date}** 的日記已成功同步到 Notion！",
            parse_mode="Markdown",
        )
        logger.info(f"使用者 {user_id} 手動同步 {diary_date} 至 Notion 成功")
    else:
        await update.message.reply_text(
            f"❌ 同步失敗，請確認 Notion 設定或查看 Bot 日誌。"
        )
        logger.warning(f"使用者 {user_id} 手動同步 {diary_date} 至 Notion 失敗")


async def cmd_sync_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/sync_all — 同步所有歷史日記到 Notion

    逐一推送 generated_diaries 中的所有日記，每 10 篇回報一次進度，
    每筆間隔 0.5 秒，避免對 Notion API 造成過大壓力。
    """
    from services.notion_service import push_diary, is_available

    # 確認 Notion 是否已設定
    if not is_available():
        await update.message.reply_text(
            "⚠️ Notion 尚未設定。\n\n"
            "請在 .env 中加入 NOTION_TOKEN 與 NOTION_DIARY_DB_ID 後重啟 Bot。"
        )
        return

    user_id = update.effective_user.id
    db: Database = context.bot_data["db"]

    # 查詢所有有日記的日期（由舊到新）
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT diary_date, content FROM generated_diaries "
            "WHERE user_id = ? ORDER BY diary_date ASC",
            (user_id,),
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 目前沒有任何日記記錄。\n\n"
            "請先用 /diary 產出日記後再使用 /sync_all。"
        )
        return

    total = len(rows)
    await update.message.reply_text(
        f"🔄 開始同步所有 **{total}** 篇日記到 Notion，請稍候...\n"
        "（每 10 篇會回報一次進度）",
        parse_mode="Markdown",
    )

    success_count = 0
    fail_count = 0

    for i, row in enumerate(rows, start=1):
        diary_date = row["diary_date"]
        diary_content = row["content"]

        # 取得心情分數
        survey = db.get_survey(user_id, diary_date)
        mood = survey.mood_score if survey and survey.mood_score is not None else None

        # 推送到 Notion
        try:
            ok = await push_diary(user_id, diary_date, diary_content, mood)
            if ok:
                success_count += 1
            else:
                fail_count += 1
                logger.warning(f"sync_all：{diary_date} 推送回傳 False")
        except Exception as e:
            fail_count += 1
            logger.error(f"sync_all：{diary_date} 推送異常 — {e}")

        # 每 10 篇回報進度
        if i % 10 == 0:
            await update.message.reply_text(
                f"📊 進度：{i}/{total} 篇（✅ {success_count} 成功 / ❌ {fail_count} 失敗）"
            )

        # 每筆間隔 0.5 秒，避免 API 頻率限制
        await asyncio.sleep(0.5)

    # 完成回報
    await update.message.reply_text(
        f"🎉 同步完成！\n\n"
        f"📊 總計：{total} 篇\n"
        f"✅ 成功：{success_count} 篇\n"
        f"❌ 失敗：{fail_count} 篇",
        parse_mode="Markdown",
    )
    logger.info(
        f"使用者 {user_id} 完成 sync_all：{total} 篇，成功 {success_count}，失敗 {fail_count}"
    )


def register_sync_handlers(app: Application):
    """註冊 /sync 與 /sync_all 指令處理器"""
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CommandHandler("sync_all", cmd_sync_all))
    logger.info("已註冊 /sync 與 /sync_all 處理器")
