"""
Embedding 服務模組 — 日記向量化與儲存

功能：
  generate_embedding(text)                        — 呼叫 OpenAI text-embedding-3-small 取得向量
  chunk_content(content, max_chars=500)           — 以雙換行分段，每段不超過 max_chars 字元
  store_embeddings(user_id, diary_date, content)  — 分段向量化並存入 diary_embeddings 資料表
"""

import logging
from typing import Optional

import numpy as np
from openai import AsyncOpenAI

import config as _cfg
from models.database import _get_db

logger = logging.getLogger(__name__)

# OpenAI Embedding 使用的模型
_EMBEDDING_MODEL = "text-embedding-3-small"

# 模組層級單例（延遲初始化）
_ai: Optional[AsyncOpenAI] = None


def _get_ai() -> AsyncOpenAI:
    """取得 AsyncOpenAI 客戶端（延遲初始化）"""
    global _ai
    if _ai is None:
        _ai = AsyncOpenAI(api_key=_cfg.OPENAI_API_KEY)
    return _ai


async def generate_embedding(text: str) -> list[float]:
    """
    呼叫 OpenAI text-embedding-3-small，回傳指定文字的向量（float list）。

    Args:
        text: 要向量化的文字

    Returns:
        embedding 向量（list of float）
    """
    response = await _get_ai().embeddings.create(
        model=_EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def chunk_content(content: str, max_chars: int = 500) -> list[str]:
    """
    以雙換行（\\n\\n）分段，每段不超過 max_chars 字元。
    若單一段落超過 max_chars，會進一步切分。

    Args:
        content:   日記全文
        max_chars: 每段最大字元數（預設 500）

    Returns:
        分段後的字串列表
    """
    chunks: list[str] = []
    # 先按空行分段
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    for para in paragraphs:
        # 若單一段落超過限制，進一步切分
        while len(para) > max_chars:
            chunks.append(para[:max_chars])
            para = para[max_chars:]
        if para:
            chunks.append(para)

    return chunks


async def store_embeddings(user_id: int, diary_date: str, content: str) -> int:
    """
    將日記內容分段向量化後，存入 diary_embeddings 資料表。

    流程：
    1. 先刪除同一 user_id + diary_date 的舊記錄（避免重複）
    2. 分段 (chunk_content)
    3. 逐段呼叫 generate_embedding
    4. numpy.ndarray.tobytes() 序列化為 BLOB 存入資料庫

    Args:
        user_id:     Telegram 使用者 ID
        diary_date:  日期字串 YYYY-MM-DD
        content:     日記全文

    Returns:
        成功儲存的段落數量
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime

    db = _get_db()
    tz = ZoneInfo(_cfg.TIMEZONE)
    now_str = datetime.now(tz).isoformat()

    # 先刪除既有的 embedding 記錄，確保重建時資料一致
    with db._get_conn() as conn:
        conn.execute(
            "DELETE FROM diary_embeddings WHERE user_id = ? AND diary_date = ?",
            (user_id, diary_date),
        )

    # 分段
    chunks = chunk_content(content)
    if not chunks:
        logger.warning(f"store_embeddings：{diary_date} 分段後為空，跳過")
        return 0

    stored = 0
    for idx, chunk in enumerate(chunks):
        try:
            # 取得向量
            vector = await generate_embedding(chunk)
            # numpy 序列化為 bytes（float32 節省空間）
            blob = np.array(vector, dtype=np.float32).tobytes()

            with db._get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO diary_embeddings "
                    "(user_id, diary_date, chunk_index, content_chunk, embedding, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, diary_date, idx, chunk, blob, now_str),
                )
            stored += 1
        except Exception as e:
            logger.error(
                f"store_embeddings：chunk {idx} 失敗 "
                f"— user={user_id} date={diary_date}: {e}"
            )

    logger.info(
        f"store_embeddings 完成 — user={user_id} date={diary_date} "
        f"共 {stored}/{len(chunks)} 段儲存成功"
    )
    return stored
