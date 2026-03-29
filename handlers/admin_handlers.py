"""
管理員指令模組 — 讓你在 Telegram 裡直接修改 Bot 設定
不需要改程式碼，不需要碰電腦！

可用指令：
    /admin           — 查看所有管理員指令
    /set_reminder    — 修改提醒時間
    /set_survey_time — 修改問卷開始時間
    /set_template    — 查看/修改日記範本
    /set_admin       — 設定管理員（首次使用時自動設定）
"""

import json
import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, Application

from models.database import Database

logger = logging.getLogger(__name__)

# 預設管理員 ID（第一個使用 /set_admin 的人會成為管理員）
ADMIN_SETTING_KEY = "admin_user_id"


def _is_admin(db: Database, user_id: int) -> bool:
    """檢查使用者是否為管理員"""
    admin_id = db.get_setting(ADMIN_SETTING_KEY)
    if not admin_id:
        return True  # 還沒設定管理員，任何人都可以
    return str(user_id) == admin_id


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """顯示所有管理員指令"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員，無法使用此指令。")
        return

    help_text = (
        "🔧 **管理員指令清單**\n\n"
        "📌 **提醒時間**\n"
        "`/set_reminder 9 12 15 18 21`\n"
        "→ 設定每天幾點提醒記日記（用空格分隔）\n\n"
        "📌 **問卷時間**\n"
        "`/set_survey_time 23`\n"
        "→ 設定每晚幾點開始問卷\n\n"
        "📌 **日記範本**\n"
        "`/get_template`\n"
        "→ 查看目前的日記範本\n\n"
        "`/set_template`\n"
        "→ 修改日記範本（直接在指令後面貼上新範本）\n\n"
        "📌 **提醒訊息**\n"
        "`/get_reminder_msg`\n"
        "→ 查看各時段的提醒訊息\n\n"
        "`/set_reminder_msg 9 早安！今天有什麼計畫？`\n"
        "→ 修改某個時段的提醒訊息\n\n"
        "📌 **管理員**\n"
        "`/set_admin`\n"
        "→ 把你自己設為管理員（只能設定一次）\n\n"
        "📌 **查看設定**\n"
        "`/show_settings`\n"
        "→ 顯示目前所有設定"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def cmd_set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """設定管理員"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    existing = db.get_setting(ADMIN_SETTING_KEY)
    if existing and str(user_id) != existing:
        await update.message.reply_text("⛔ 管理員已經設定過了，無法更改。")
        return

    db.set_setting(ADMIN_SETTING_KEY, str(user_id))
    await update.message.reply_text(
        f"✅ 已將你設為管理員！\n"
        f"你的 User ID: `{user_id}`\n\n"
        f"輸入 /admin 查看所有管理員指令。",
        parse_mode="Markdown",
    )
    logger.info(f"管理員已設定: {user_id}")


async def cmd_set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修改提醒時間"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員。")
        return

    args = context.args
    if not args:
        current = db.get_setting("reminder_hours", "9,12,15,18,21")
        await update.message.reply_text(
            f"⏰ **目前的提醒時間**: {current.replace(',', ', ')} 點\n\n"
            f"要修改的話，輸入：\n"
            f"`/set_reminder 8 12 15 18 21`\n"
            f"（用空格分隔小時數）",
            parse_mode="Markdown",
        )
        return

    try:
        hours = [int(h) for h in args]
        for h in hours:
            if h < 0 or h > 23:
                raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ 格式錯誤！請輸入 0-23 之間的數字，用空格分隔。")
        return

    hours_str = ",".join(str(h) for h in sorted(hours))
    db.set_setting("reminder_hours", hours_str)

    display = "、".join(f"{h:02d}:00" for h in sorted(hours))
    await update.message.reply_text(
        f"✅ 提醒時間已更新！\n\n"
        f"新的提醒時間：{display}\n\n"
        f"⚠️ 需要重新部署才會生效。\n"
        f"如果你是用 Zeabur，到 Overview 頁面點 **Restart** 即可。",
        parse_mode="Markdown",
    )
    logger.info(f"提醒時間已更新: {hours_str}")


async def cmd_set_survey_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修改問卷開始時間"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員。")
        return

    args = context.args
    if not args:
        current = db.get_setting("survey_hour", "23")
        await update.message.reply_text(
            f"🌙 **目前的問卷時間**: {current}:00\n\n"
            f"要修改的話，輸入：\n"
            f"`/set_survey_time 22`",
            parse_mode="Markdown",
        )
        return

    try:
        hour = int(args[0])
        if hour < 0 or hour > 23:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ 請輸入 0-23 之間的數字。")
        return

    db.set_setting("survey_hour", str(hour))
    await update.message.reply_text(
        f"✅ 問卷時間已更新為 **{hour:02d}:00**\n\n"
        f"⚠️ 需要 Restart 才會生效。",
        parse_mode="Markdown",
    )


async def cmd_get_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看目前的日記範本"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員。")
        return

    from templates.diary_template import DIARY_TEMPLATE
    custom = db.get_setting("diary_template")
    template = custom if custom else DIARY_TEMPLATE

    await update.message.reply_text(
        f"📔 **目前的日記範本：**\n\n"
        f"```\n{template}\n```\n\n"
        f"要修改的話，輸入：\n"
        f"`/set_template` 後面接你的新範本",
        parse_mode="Markdown",
    )


async def cmd_set_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修改日記範本"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員。")
        return

    # 取得指令後面的所有文字作為範本
    text = update.message.text
    # 移除 /set_template 前綴
    template = text.replace("/set_template", "", 1).strip()

    if not template:
        await update.message.reply_text(
            "📝 請在 `/set_template` 後面貼上你的新範本。\n\n"
            "範例：\n"
            "`/set_template\n"
            "# 📔 日記 — {date}\n"
            "## 今天做了什麼\n"
            "## 心得感想\n"
            "## 明天計畫`",
            parse_mode="Markdown",
        )
        return

    db.set_setting("diary_template", template)
    await update.message.reply_text(
        f"✅ 日記範本已更新！\n\n"
        f"新範本預覽：\n```\n{template[:500]}\n```\n\n"
        f"下次產出日記時就會使用新範本。",
        parse_mode="Markdown",
    )
    logger.info("日記範本已更新")


async def cmd_get_reminder_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看各時段的提醒訊息"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員。")
        return

    from templates.diary_template import REMINDER_MESSAGES

    lines = ["📨 **各時段提醒訊息：**\n"]
    hours = db.get_setting("reminder_hours", "9,12,15,18,21")
    for h in hours.split(","):
        h_int = int(h)
        custom = db.get_setting(f"reminder_msg_{h}")
        default = REMINDER_MESSAGES.get(h_int, "📝 記得記日記喔！")
        msg = custom if custom else default
        source = "（自訂）" if custom else "（預設）"
        lines.append(f"  {h_int:02d}:00 → {msg} {source}")

    lines.append(f"\n修改方式：\n`/set_reminder_msg 9 你想要的訊息內容`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_set_reminder_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修改某個時段的提醒訊息"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員。")
        return

    text = update.message.text.replace("/set_reminder_msg", "", 1).strip()
    parts = text.split(" ", 1)

    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ 格式：`/set_reminder_msg 9 你的訊息`\n"
            "第一個數字是小時，後面是訊息內容。",
            parse_mode="Markdown",
        )
        return

    try:
        hour = int(parts[0])
        msg = parts[1].strip()
    except ValueError:
        await update.message.reply_text("⚠️ 第一個參數必須是數字（小時）。")
        return

    db.set_setting(f"reminder_msg_{hour}", msg)
    await update.message.reply_text(
        f"✅ {hour:02d}:00 的提醒訊息已更新為：\n\n「{msg}」",
    )


async def cmd_show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """顯示目前所有設定"""
    db: Database = context.bot_data["db"]
    user_id = update.effective_user.id

    if not _is_admin(db, user_id):
        await update.message.reply_text("⛔ 你不是管理員。")
        return

    reminder_hours = db.get_setting("reminder_hours", "9,12,15,18,21")
    survey_hour = db.get_setting("survey_hour", "23")
    has_custom_template = "✅ 有自訂範本" if db.get_setting("diary_template") else "📋 使用預設範本"
    admin_id = db.get_setting(ADMIN_SETTING_KEY, "未設定")

    display_hours = "、".join(f"{int(h):02d}:00" for h in reminder_hours.split(","))

    msg = (
        "⚙️ **目前的 Bot 設定**\n\n"
        f"👤 管理員 ID：`{admin_id}`\n"
        f"⏰ 提醒時間：{display_hours}\n"
        f"🌙 問卷時間：{survey_hour}:00\n"
        f"📔 日記範本：{has_custom_template}\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


def register_admin_handlers(app: Application):
    """註冊所有管理員指令"""
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("set_admin", cmd_set_admin))
    app.add_handler(CommandHandler("set_reminder", cmd_set_reminder))
    app.add_handler(CommandHandler("set_survey_time", cmd_set_survey_time))
    app.add_handler(CommandHandler("get_template", cmd_get_template))
    app.add_handler(CommandHandler("set_template", cmd_set_template))
    app.add_handler(CommandHandler("get_reminder_msg", cmd_get_reminder_msg))
    app.add_handler(CommandHandler("set_reminder_msg", cmd_set_reminder_msg))
    app.add_handler(CommandHandler("show_settings", cmd_show_settings))

    logger.info("已註冊管理員指令處理器")
