"""AI 日記產出模組"""

import os
import logging
from datetime import datetime, timedelta
import zoneinfo
from openai import OpenAI
from bot.config import OPENAI_API_KEY, TIMEZONE
from bot.db import supabase_client as db

logger = logging.getLogger(__name__)

tz = zoneinfo.ZoneInfo(TIMEZONE)
_openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 星期對照表
WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]


def _load_prompt_template() -> str:
    """讀取日記 Prompt 範本"""
    # 優先從 Supabase bot_settings 讀取
    settings = db.get_settings()
    custom_prompt = settings.get("diary_prompt_template")
    if custom_prompt:
        return custom_prompt

    # 否則從檔案讀取
    template_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "diary_prompt.txt")
    template_path = os.path.normpath(template_path)
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def _build_simple_diary(date: str, entries: list, summary: dict | None) -> str:
    """產出精簡版日記（純條列，不經 GPT）"""
    weekday = WEEKDAY_NAMES[datetime.strptime(date, "%Y-%m-%d").weekday()]
    lines = [f"### 📅 {date} 星期{weekday}\n"]
    lines.append("#### 📖 今日時間軸")

    if entries:
        for entry in entries:
            icon = "🎤" if entry["source_type"] == "voice" else "📝"
            time_str = entry["time"][:5]
            lines.append(f"- {icon} [{time_str}] {entry['content']}")
    else:
        lines.append("- 無紀錄")

    # 問卷回答
    if summary:
        answers = summary.get("questionnaire_answers", {}) or {}
        mood = summary.get("mood_score")

        lines.append("\n#### 🙏 今日感恩")
        gratitude = answers.get("gratitude")
        if gratitude:
            if isinstance(gratitude, list):
                for item in gratitude:
                    lines.append(f"- {item}")
            else:
                lines.append(str(gratitude))
        else:
            lines.append("未記錄")

        lines.append("\n#### 🎭 心情指數")
        score_labels = {-2: "😢 很差 (-2)", -1: "😕 不太好 (-1)", 0: "😐 普通 (0)", 1: "🙂 不錯 (1)", 2: "😄 很好 (2)"}
        lines.append(score_labels.get(mood, "未記錄") if mood is not None else "未記錄")

        lines.append("\n#### 💡 今日學習與想法")
        lines.append(answers.get("learning", "未記錄"))

        lines.append("\n#### ✨ 值得記錄的時刻")
        lines.append(answers.get("highlight", "未記錄"))
    else:
        lines.append("\n#### 🙏 今日感恩\n未記錄")
        lines.append("\n#### 🎭 心情指數\n未記錄")
        lines.append("\n#### 💡 今日學習與想法\n未記錄")
        lines.append("\n#### ✨ 值得記錄的時刻\n未記錄")

    return "\n".join(lines)


def _build_gpt_user_message(date: str, entries: list, summary: dict | None) -> str:
    """組合送給 GPT 的使用者訊息"""
    weekday = WEEKDAY_NAMES[datetime.strptime(date, "%Y-%m-%d").weekday()]
    parts = [f"日期：{date} 星期{weekday}\n"]

    # 當日紀錄
    parts.append("## 當日紀錄")
    for entry in entries:
        icon = "🎤語音" if entry["source_type"] == "voice" else "📝文字"
        time_str = entry["time"][:5]
        parts.append(f"- [{time_str}]（{icon}）{entry['content']}")

    # 問卷回答
    parts.append("\n## 問卷回答")
    if summary:
        answers = summary.get("questionnaire_answers", {}) or {}
        mood = summary.get("mood_score")

        gratitude = answers.get("gratitude")
        if gratitude:
            if isinstance(gratitude, list):
                parts.append(f"- 今天感恩的事：{', '.join(gratitude)}")
            else:
                parts.append(f"- 今天感恩的事：{gratitude}")
        else:
            parts.append("- 今天感恩的事：未回答")

        if mood is not None:
            parts.append(f"- 心情分數：{mood}")
        else:
            parts.append("- 心情分數：未設定")

        parts.append(f"- 今天的學習或想法：{answers.get('learning', '未回答')}")
        parts.append(f"- 值得記錄的時刻：{answers.get('highlight', '未回答')}")
    else:
        parts.append("（未完成問卷）")

    return "\n".join(parts)


async def generate_diary(date: str) -> str:
    """主函式：產出指定日期的日記"""
    entries = db.get_entries_by_date(date)
    summary = db.get_summary(date)
    questionnaire_complete = db.is_questionnaire_complete(date)

    # 零紀錄 + 零問卷 → 不產出
    if len(entries) == 0 and not questionnaire_complete:
        return ""

    # 紀錄不足 + 問卷未完成 → 精簡版
    if len(entries) < 2 and not questionnaire_complete:
        diary = _build_simple_diary(date, entries, summary)
        db.get_or_create_summary(date)
        db.update_summary_field(date, "diary_output", diary)
        return diary

    # 正常流程 → 呼叫 GPT
    try:
        prompt_template = _load_prompt_template()
        user_message = _build_gpt_user_message(date, entries, summary)

        settings = db.get_settings()
        model = settings.get("gpt_model", "gpt-4o")

        response = _openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_template},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        diary = response.choices[0].message.content
        logger.info(f"AI 日記產出成功: {date}")

    except Exception as e:
        logger.error(f"GPT API 呼叫失敗，使用精簡版日記: {e}")
        diary = _build_simple_diary(date, entries, summary)

    # 儲存日記
    db.get_or_create_summary(date)
    db.update_summary_field(date, "diary_output", diary)
    return diary
