"""問卷對話流程模組"""

import logging
from datetime import datetime
import zoneinfo
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import TIMEZONE
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

tz = zoneinfo.ZoneInfo(TIMEZONE)


def _get_q_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """從 bot_data 取得問卷狀態"""
    return context.application.bot_data.setdefault("questionnaire", {})


def is_questionnaire_active(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """檢查問卷是否正在進行中"""
    q_data = _get_q_data(context)
    return q_data.get("active", False)


async def start_questionnaire(bot, chat_id: int, q_data: dict) -> None:
    """由排程器呼叫：啟動問卷流程，發出第一題"""
    today = datetime.now(tz).strftime("%Y-%m-%d")

    # 檢查今天是否已完成問卷
    if db.is_questionnaire_complete(today):
        logger.info(f"今日（{today}）問卷已完成，跳過")
        return

    settings = db.get_settings()
    template = settings.get("questionnaire_template", [])
    if not template:
        logger.warning("問卷範本為空，跳過問卷")
        return

    # 確保 daily_summary 存在
    db.get_or_create_summary(today)

    # 設定問卷狀態到 bot_data
    q_data["active"] = True
    q_data["date"] = today
    q_data["template"] = template
    q_data["step"] = 0

    # 發出第一題
    total = len(template)
    question = template[0]["question"]
    await bot.send_message(
        chat_id=chat_id,
        text=f"📋 問題 1/{total}：\n{question}",
    )
    logger.info(f"問卷已啟動，共 {total} 題")


async def handle_questionnaire_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理問卷回答：儲存答案，發出下一題或完成"""
    q_data = _get_q_data(context)
    answer_text = update.message.text
    step = q_data.get("step", 0)
    template = q_data.get("template", [])
    date = q_data.get("date")
    total = len(template)

    if step >= total:
        return

    current_q = template[step]
    key = current_q["key"]
    q_type = current_q.get("type", "text")

    # 根據類型解析答案
    if q_type == "list":
        parsed = [item.strip() for item in answer_text.replace("，", ",").split(",")]
    elif q_type == "score":
        try:
            parsed = int(answer_text)
            if parsed < -2 or parsed > 2:
                await update.message.reply_text("⚠️ 請輸入 -2 到 2 之間的整數。")
                return
            # 同時更新 mood_score
            db.update_summary_field(date, "mood_score", parsed)
        except ValueError:
            await update.message.reply_text("⚠️ 請輸入 -2 到 2 之間的整數。")
            return
    else:
        parsed = answer_text

    # 儲存答案到 questionnaire_answers
    summary = db.get_or_create_summary(date)
    answers = summary.get("questionnaire_answers", {}) or {}
    answers[key] = parsed
    db.update_summary_field(date, "questionnaire_answers", answers)

    # 更新步驟
    next_step = step + 1
    q_data["step"] = next_step
    db.update_summary_field(date, "questionnaire_step", next_step)

    if next_step < total:
        # 發出下一題
        next_q = template[next_step]["question"]
        await update.message.reply_text(
            f"📋 問題 {next_step + 1}/{total}：\n{next_q}"
        )
    else:
        # 問卷完成
        q_data["active"] = False
        await update.message.reply_text("✅ 問卷完成！今晚會幫你整理日記。")
        logger.info(f"問卷完成: {date}")


async def cancel_questionnaire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """處理 /cancel 指令：中止問卷"""
    q_data = _get_q_data(context)
    if not q_data.get("active", False):
        await update.message.reply_text("目前沒有進行中的問卷。")
        return

    q_data["active"] = False
    await update.message.reply_text("❌ 問卷已取消。")
    logger.info("問卷已被使用者取消")


async def auto_close_questionnaire(bot, chat_id: int, q_data: dict) -> None:
    """超時自動結算問卷"""
    if not q_data.get("active", False):
        return

    q_data["active"] = False
    await bot.send_message(
        chat_id=chat_id,
        text="⏰ 問卷回覆時間已截止，將以目前收集到的資料產出日記。",
    )
    logger.info("問卷已超時自動結算")
