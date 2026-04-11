"""
AI 服務模組 — 負責語音轉文字 (Whisper) 與日記生成 (GPT-4o)
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, WHISPER_MODEL, WHISPER_LANGUAGE, GPT_MODEL
from models.database import EntryRecord, SurveyRecord

logger = logging.getLogger(__name__)


class AIService:
    """封裝 OpenAI API 呼叫（使用非同步客戶端）"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    # ── 語音轉文字 ────────────────────────────

    async def transcribe_voice(self, audio_file_path: str) -> tuple[Optional[str], Optional[str]]:
        """
        使用 Whisper API 將語音檔轉為正體中文文字。
        回傳 (轉錄文字, 錯誤訊息)。成功時錯誤訊息為 None。
        """
        try:
            file_size = Path(audio_file_path).stat().st_size
            logger.info(f"開始語音轉文字，檔案大小: {file_size} bytes")

            if file_size == 0:
                return None, "語音檔案是空的"

            with open(audio_file_path, "rb") as audio_file:
                response = await self.client.audio.transcriptions.create(
                    model=WHISPER_MODEL,
                    file=audio_file,
                    language=WHISPER_LANGUAGE,
                    response_format="text",
                )

            text = response.strip() if isinstance(response, str) else response.text.strip()
            if not text:
                return None, "語音辨識結果為空（可能是靜音或雜訊）"

            logger.info(f"語音轉文字成功，長度: {len(text)} 字")
            return text, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"語音轉文字失敗: {error_msg}")
            return None, error_msg

    # ── 日記生成 ──────────────────────────────

    async def generate_diary(
        self,
        diary_date: str,
        entries: list[EntryRecord],
        survey: Optional[SurveyRecord],
        template: str,
    ) -> str:
        """
        使用 GPT-4o 將當天的記錄與問卷彙整成 Markdown 日記。
        """
        # 組合記錄內容
        if entries:
            entries_text = "\n".join(
                f"- [{e.timestamp}] ({e.entry_type}) {e.content}"
                for e in entries
            )
        else:
            entries_text = "（今天沒有記錄任何內容）"

        # 組合問卷內容
        if survey and survey.completed:
            survey_text = (
                f"最重要的事：{survey.most_important or '未填寫'}\n"
                f"感恩第 1 件：{survey.gratitude_1 or '未填寫'}\n"
                f"感恩第 2 件：{survey.gratitude_2 or '未填寫'}\n"
                f"感恩第 3 件：{survey.gratitude_3 or '未填寫'}\n"
                f"心情評分：{survey.mood_score if survey.mood_score is not None else '未填寫'}\n"
                f"補充內容：{survey.additional_notes or '無'}"
            )
        else:
            survey_text = "（今天未完成問卷）"

        prompt = f"""你是一位溫暖且善於觀察的日記助手。請根據以下資料，用正體中文撰寫一篇結構化的 Markdown 日記。

日期：{diary_date}

## 今日記錄
{entries_text}

## 晚間問卷
{survey_text}

## 日記範本格式
{template}

請注意：
1. 保持正體中文，使用台灣慣用語
2. 時間軸按照時間順序排列
3. 如果記錄中提到地點或人物，請分別整理
4. 語氣溫暖自然，像是在幫使用者回顧一天
5. 如果今天沒有記錄，仍然產出一份簡短的空白日記以保持連續性
6. 心情評分使用 emoji 呈現：-2=😢, -1=😔, 0=😐, 1=🙂, 2=😄
"""

        try:
            response = await self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {"role": "system", "content": "你是板橋好初早餐老闆的私人日記助手，專門幫他記錄每天的生活點滴。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )
            diary_content = response.choices[0].message.content
            logger.info(f"日記生成成功，日期: {diary_date}")
            return diary_content
        except Exception as e:
            logger.error(f"日記生成失敗: {type(e).__name__}: {e}")
            # 回傳基本格式的日記
            return self._fallback_diary(diary_date, entries, survey)

    def _fallback_diary(
        self,
        diary_date: str,
        entries: list[EntryRecord],
        survey: Optional[SurveyRecord],
    ) -> str:
        """AI 生成失敗時的備用日記格式"""
        lines = [
            f"# 📔 日記 — {diary_date}",
            "",
            "## ⏰ 時間軸",
        ]
        if entries:
            for e in entries:
                lines.append(f"- {e.timestamp} | {e.content}")
        else:
            lines.append("- （今天沒有記錄）")

        lines.extend(["", "## ⭐ 最重要的事"])
        if survey and survey.most_important:
            lines.append(survey.most_important)
        else:
            lines.append("未記錄")

        lines.extend(["", "## 🙏 感恩三件事"])
        if survey:
            for i, g in enumerate([survey.gratitude_1, survey.gratitude_2, survey.gratitude_3], 1):
                lines.append(f"{i}. {g or '未記錄'}")
        else:
            lines.extend(["1. 未記錄", "2. 未記錄", "3. 未記錄"])

        lines.extend(["", "## 😊 心情評分"])
        if survey and survey.mood_score is not None:
            mood_map = {-2: "😢", -1: "😔", 0: "😐", 1: "🙂", 2: "😄"}
            lines.append(f"{survey.mood_score} {mood_map.get(survey.mood_score, '')}")
        else:
            lines.append("未記錄")

        lines.extend(["", "---", f"*由日記助理自動產出（備用格式） — {diary_date}*"])
        return "\n".join(lines)
