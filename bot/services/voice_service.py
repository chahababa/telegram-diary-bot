"""語音下載 + Whisper 轉文字模組"""

import os
import logging
import tempfile
from openai import OpenAI
from bot.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

_openai_client = OpenAI(api_key=OPENAI_API_KEY)

MAX_RETRIES = 2


async def download_and_transcribe(voice_file, bot) -> str:
    """從 Telegram 下載語音檔 → 呼叫 Whisper API 轉文字 → 回傳轉寫結果"""
    ogg_path = None
    try:
        # 建立暫存檔案
        ogg_path = os.path.join(tempfile.gettempdir(), f"voice_{voice_file.file_id}.ogg")

        # 從 Telegram 下載語音檔
        file = await bot.get_file(voice_file.file_id)
        await file.download_to_drive(ogg_path)
        logger.info(f"語音檔已下載: {ogg_path}")

        # 呼叫 Whisper API，含重試機制
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with open(ogg_path, "rb") as audio_file:
                    transcript = _openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="zh",
                    )
                logger.info(f"語音轉寫成功（第 {attempt} 次嘗試）")
                return transcript.text
            except Exception as e:
                last_error = e
                logger.warning(f"Whisper API 第 {attempt} 次嘗試失敗: {e}")

        # 重試用盡仍失敗
        raise last_error

    finally:
        # 清理暫存的 .ogg 檔案
        if ogg_path and os.path.exists(ogg_path):
            try:
                os.remove(ogg_path)
                logger.info(f"已清理暫存檔: {ogg_path}")
            except Exception as e:
                logger.warning(f"清理暫存檔失敗: {e}")
