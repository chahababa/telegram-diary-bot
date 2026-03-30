"""
問卷處理模組 — 管理每晚 23:00 的結算問卷流程
問卷步驟：最重要的事 → 感恩 3 件 → 心情評分 (-2~+2) → 補充
"""

import logging
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, filters, Application,
)

from models.database import Database
from services.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)

# 問卷狀態常數
(
    STEP_IMPORTANT,
    STEP_GRATITUDE_1,
    STEP_GRATITUDE_2,
    STEP_GRATITUDE_3,
    STEP_MOOD,
    STEP_ADDITIONAL,
) = range(6)

# 心情評分鍵盤
MOOD_KEYBOARD = ReplyKeyboardMarkup(
    [["-2 😢", "-1 😔", "0 😐", "+1 🙂", "+2 😄"]],
    one_time_keyboard=True,
    resize_keyboard=True,
)


class SurveyManager:
    """問卷流程管理器"""

    def __init__(self):
        self.active_surveys: dict[int, int] = {}  # user_id → survey_id

    def get_conversation_handler(self) -> ConversationHandler:
        """建立並回傳問卷的 ConversationHandler"""
        return ConversationHandler(
            entry_points=[
                CommandHandler("survey", self._start_survey),
            ],
            states={
                STEP_IMPORTANT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_important)
                ],
                STEP_GRATITUDE_1: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_gratitude_1)
                ],
                STEP_GRATITUDE_2: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_gratitude_2)
                ],
                STEP_GRATITUDE_3: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_gratitude_3)
                ],
                STEP_MOOD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_mood)
                ],
                STEP_ADDITIONAL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_additional)
                ],
            },
            fallbacks=[
                CommandHandler("skip", self._skip_survey),
                CommandHandler("cancel", self._cancel_survey),
            ],
            per_user=True,
            per_chat=True,
        )

    async def trigger_survey_for_all(self, app):
        """由排程觸發，對所有使用者發起問卷"""
        db: Database = app.bot_data["db"]
        scheduler: SchedulerService = app.bot_data["scheduler"]

        user_ids = db.get_all_user_ids()
        diary_date = scheduler.get_diary_date()

        for user_id in user_ids:
            try:
                # 建立問卷記錄
                now_str = scheduler.get_now().isoformat()
                survey_id = db.create_survey(user_id, diary_date, now_str)
                self.active_surveys[user_id] = survey_id

                await app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "🌙 **晚安！來回顧今天吧！**\n\n"
                        "👉 請輸入 /survey 開始今日回顧問卷"
                    ),
                    parse_mode="Markdown",
                )
                logger.info(f"已發送問卷給使用者 {user_id}")
            except Exception as e:
                logger.error(f"發送問卷給使用者 {user_id} 失敗: {e}")

    async def timeout_survey_for_all(self, app):
        """23:50 超時自動結算所有未完成的問卷"""
        db: Database = app.bot_data["db"]
        scheduler: SchedulerService = app.bot_data["scheduler"]
        diary_date = scheduler.get_diary_date()

        for user_id, survey_id in list(self.active_surveys.items()):
            try:
                db.update_survey_field(survey_id, "completed", 1)
                del self.active_surveys[user_id]

                await app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⏰ 問卷時間到了，已自動結算！\n"
                        "已回答的部分都會納入今天的日記 📔\n"
                        "晚安！明天見 🌟"
                    ),
                )
                logger.info(f"使用者 {user_id} 問卷超時自動結算")
            except Exception as e:
                logger.error(f"超時結算使用者 {user_id} 失敗: {e}")

    # ── 問卷步驟處理 ────────────────────────────

    async def _start_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """手動開始問卷（或被排程推播後使用者回覆時觸發）"""
        db: Database = context.bot_data["db"]
        scheduler: SchedulerService = context.bot_data["scheduler"]
        user_id = update.effective_user.id
        diary_date = scheduler.get_diary_date()

        # 如果沒有進行中的問卷，建立一個
        if user_id not in self.active_surveys:
            now_str = scheduler.get_now().isoformat()
            survey_id = db.create_survey(user_id, diary_date, now_str)
            self.active_surveys[user_id] = survey_id

        context.user_data["survey_active"] = True
        context.user_data["survey_step"] = STEP_IMPORTANT

        await update.message.reply_text(
            "🌙 開始今日回顧問卷！\n\n"
            "❓ **今天最重要的一件事是什麼？**\n"
            "（輸入 /skip 跳過此題）",
            parse_mode="Markdown",
        )
        return STEP_IMPORTANT

    async def _handle_important(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理：最重要的事"""
        db: Database = context.bot_data["db"]
        user_id = update.effective_user.id
        survey_id = self.active_surveys.get(user_id)

        if survey_id:
            db.update_survey_field(survey_id, "most_important", update.message.text.strip())

        context.user_data["survey_step"] = STEP_GRATITUDE_1
        await update.message.reply_text(
            "👍 收到！\n\n🙏 **今天感恩的第 1 件事是什麼？**",
            parse_mode="Markdown",
        )
        return STEP_GRATITUDE_1

    async def _handle_gratitude_1(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理：感恩第 1 件"""
        db: Database = context.bot_data["db"]
        user_id = update.effective_user.id
        survey_id = self.active_surveys.get(user_id)

        if survey_id:
            db.update_survey_field(survey_id, "gratitude_1", update.message.text.strip())

        context.user_data["survey_step"] = STEP_GRATITUDE_2
        await update.message.reply_text(
            "🙏 **感恩的第 2 件事？**",
            parse_mode="Markdown",
        )
        return STEP_GRATITUDE_2

    async def _handle_gratitude_2(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理：感恩第 2 件"""
        db: Database = context.bot_data["db"]
        user_id = update.effective_user.id
        survey_id = self.active_surveys.get(user_id)

        if survey_id:
            db.update_survey_field(survey_id, "gratitude_2", update.message.text.strip())

        context.user_data["survey_step"] = STEP_GRATITUDE_3
        await update.message.reply_text(
            "🙏 **感恩的第 3 件事？**",
            parse_mode="Markdown",
        )
        return STEP_GRATITUDE_3

    async def _handle_gratitude_3(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理：感恩第 3 件"""
        db: Database = context.bot_data["db"]
        user_id = update.effective_user.id
        survey_id = self.active_surveys.get(user_id)

        if survey_id:
            db.update_survey_field(survey_id, "gratitude_3", update.message.text.strip())

        context.user_data["survey_step"] = STEP_MOOD
        await update.message.reply_text(
            "😊 **今天的心情評分？**\n\n請選擇 -2 到 +2：",
            parse_mode="Markdown",
            reply_markup=MOOD_KEYBOARD,
        )
        return STEP_MOOD

    async def _handle_mood(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理：心情評分"""
        db: Database = context.bot_data["db"]
        user_id = update.effective_user.id
        survey_id = self.active_surveys.get(user_id)

        # 解析心情評分（從 "+1 🙂" 格式中取出數字）
        text = update.message.text.strip()
        try:
            score = int(text.split()[0])
            if score < -2 or score > 2:
                raise ValueError
        except (ValueError, IndexError):
            await update.message.reply_text(
                "⚠️ 請輸入 -2 到 +2 之間的數字。",
                reply_markup=MOOD_KEYBOARD,
            )
            return STEP_MOOD

        if survey_id:
            db.update_survey_field(survey_id, "mood_score", score)

        context.user_data["survey_step"] = STEP_ADDITIONAL
        await update.message.reply_text(
            "📝 **還有什麼想補充的嗎？**\n\n"
            "（沒有的話輸入「沒有」或 /skip）",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return STEP_ADDITIONAL

    async def _handle_additional(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理：補充內容（最後一步）"""
        db: Database = context.bot_data["db"]
        user_id = update.effective_user.id
        survey_id = self.active_surveys.get(user_id)

        text = update.message.text.strip()
        if text.lower() not in ("沒有", "無", "沒", "no", "none"):
            if survey_id:
                db.update_survey_field(survey_id, "additional_notes", text)

        # 完成問卷
        if survey_id:
            db.update_survey_field(survey_id, "completed", 1)
            if user_id in self.active_surveys:
                del self.active_surveys[user_id]

        context.user_data["survey_active"] = False

        await update.message.reply_text(
            "✅ 問卷完成！謝謝你的回顧 🌟\n\n"
            "今天的日記會在凌晨 00:00 自動產出。\n"
            "也可以用 /diary 手動產出。\n\n"
            "晚安！好好休息 🌙",
            reply_markup=ReplyKeyboardRemove(),
        )
        logger.info(f"使用者 {user_id} 完成問卷")
        return ConversationHandler.END

    async def _skip_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """跳過當前問題"""
        current_step = context.user_data.get("survey_step", STEP_IMPORTANT)
        
        if current_step == STEP_IMPORTANT:
            next_step = STEP_GRATITUDE_1
            text = "⏭️ 已跳過。\n\n🙏 **今天感恩的第 1 件事是什麼？**"
            markup = ReplyKeyboardRemove()
        elif current_step == STEP_GRATITUDE_1:
            next_step = STEP_GRATITUDE_2
            text = "⏭️ 已跳過。\n\n🙏 **感恩的第 2 件事？**"
            markup = None
        elif current_step == STEP_GRATITUDE_2:
            next_step = STEP_GRATITUDE_3
            text = "⏭️ 已跳過。\n\n🙏 **感恩的第 3 件事？**"
            markup = None
        elif current_step == STEP_GRATITUDE_3:
            next_step = STEP_MOOD
            text = "⏭️ 已跳過。\n\n😊 **今天的心情評分？**\n\n請選擇 -2 到 +2："
            markup = MOOD_KEYBOARD
        elif current_step == STEP_MOOD:
            next_step = STEP_ADDITIONAL
            text = "⏭️ 已跳過。\n\n📝 **還有什麼想補充的嗎？**\n\n（沒有的話輸入「沒有」或 /skip）"
            markup = ReplyKeyboardRemove()
        else:
            # 補充內容也跳過，就完成問卷
            update.message.text = "沒有"
            return await self._handle_additional(update, context)

        context.user_data["survey_step"] = next_step
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
        return next_step

    async def _cancel_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """取消問卷"""
        user_id = update.effective_user.id
        db: Database = context.bot_data["db"]
        survey_id = self.active_surveys.get(user_id)

        if survey_id:
            db.update_survey_field(survey_id, "completed", 1)
            if user_id in self.active_surveys:
                del self.active_surveys[user_id]

        context.user_data["survey_active"] = False

        await update.message.reply_text(
            "🛑 問卷已取消。已回答的部分會保留。\n"
            "晚安！🌙",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END
