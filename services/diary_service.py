"""
日記生成服務模組 — 提供排程器與指令處理器共用的日記生成邏輯
"""

import logging

from models.database import _get_db
from services.ai_service import AIService
from templates.diary_template import DIARY_TEMPLATE

logger = logging.getLogger(__name__)

# 模組層級的 AI 服務實例（延遲初始化）
_ai: AIService | None = None


def _get_ai() -> AIService:
    """取得或建立 AIService 實例"""
    global _ai
    if _ai is None:
        _ai = AIService()
    return _ai


async def generate_diary(user_id: int, diary_date: str) -> str:
    """
    產出指定使用者、指定日期的日記。

    此函式封裝了從資料庫取得記錄、問卷，並呼叫 AI 生成日記的完整流程。
    供 scheduler_service.trigger_diary_generation() 排程呼叫使用。

    Args:
        user_id: Telegram 使用者 ID
        diary_date: 日期字串 YYYY-MM-DD

    Returns:
        生成的 Markdown 日記內容
    """
    db = _get_db()
    ai = _get_ai()

    entries = db.get_entries_by_date(user_id, diary_date)
    survey = db.get_survey(user_id, diary_date)

    logger.info(
        f"開始為使用者 {user_id} 生成 {diary_date} 的日記"
        f"（記錄 {len(entries)} 筆，問卷 {'已完成' if survey and survey.completed else '未完成'}）"
    )

    diary_content = await ai.generate_diary(diary_date, entries, survey, DIARY_TEMPLATE)

    # 儲存到資料庫
    from services.scheduler_service import get_now
    now_str = get_now().isoformat()
    db.save_diary(user_id, diary_date, diary_content, now_str)

    logger.info(f"使用者 {user_id} 的 {diary_date} 日記已生成並儲存")
    return diary_content
