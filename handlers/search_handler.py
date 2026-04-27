"""
語意搜尋處理模組 — /search

流程：
  1. 將使用者查詢文字轉為 Embedding
  2. 比對資料庫中所有 diary_embeddings 的餘弦相似度
  3. 取 Top 5（去重同日期），若無結果給予提示
  4. 將相關段落交給 AI 彙整後回覆
"""

import logging

import numpy as np
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, Application

import config as _cfg
from models.database import Database, _get_db
from services.settings_service import get_gpt_model

logger = logging.getLogger(__name__)

# 搜尋結果取 Top N 筆（依日期去重）
_TOP_K = 5


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """計算兩向量的餘弦相似度"""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def _summarize_results(query: str, hits: list[dict]) -> str:
    """
    將搜尋到的相關段落交給 GPT 彙整成自然語言回覆。

    Args:
        query: 使用者原始查詢
        hits:  [{"diary_date": str, "content_chunk": str, "score": float}, ...]

    Returns:
        AI 彙整後的回覆文字
    """
    from openai import AsyncOpenAI

    ai = AsyncOpenAI(api_key=_cfg.OPENAI_API_KEY)

    # 組合參考段落
    context_parts = []
    for h in hits:
        context_parts.append(f"【{h['diary_date']}】\n{h['content_chunk']}")
    context_text = "\n\n".join(context_parts)

    system_prompt = (
        "你是一個日記搜尋助手，根據使用者的查詢關鍵字，"
        "從下方提供的日記片段中找出相關內容，用正體中文整理成清晰、溫暖的摘要回覆。"
        "不要逐字引用，請用自然語言彙整重點。"
    )
    user_prompt = (
        f"使用者查詢：「{query}」\n\n"
        f"以下是相關的日記片段（按日期排列）：\n\n{context_text}\n\n"
        "請根據以上內容，給使用者一個有條理的彙整回覆。"
    )

    response = await ai.chat.completions.create(
        model=get_gpt_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/search 查詢 — 語意搜尋歷史日記

    流程：
      1. 查詢文字 → Embedding
      2. 比對所有 diary_embeddings（餘弦相似度）
      3. Top 5 去重（同日期只取最高分那段）
      4. AI 彙整相關段落後回覆

    空表時提示先執行 /sync_all；無結果時提示換關鍵字。
    """
    from services.embedding_service import generate_embedding

    user_id = update.effective_user.id
    db: Database = context.bot_data["db"]

    # 確認有查詢文字
    if not context.args:
        await update.message.reply_text(
            "🔍 用法：/search 查詢關鍵字\n\n"
            "例如：/search 早餐店開會\n"
            "     /search 心情很好的一天"
        )
        return

    query = " ".join(context.args).strip()

    # 確認 diary_embeddings 是否有資料
    with db._get_conn() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM diary_embeddings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total_chunks = count_row["cnt"] if count_row else 0

    if total_chunks == 0:
        await update.message.reply_text(
            "📭 尚無任何 Embedding 資料。\n\n"
            "請先執行 /sync_all 將日記同步到 Notion，\n"
            "系統會在同步時自動建立搜尋索引。"
        )
        return

    await update.message.reply_text(
        f"🔍 正在搜尋「{query}」，請稍候..."
    )

    # 取得查詢向量
    try:
        query_vec = np.array(await generate_embedding(query), dtype=np.float32)
    except Exception as e:
        logger.error(f"搜尋 Embedding 失敗：{e}")
        await update.message.reply_text(
            "⚠️ 語意搜尋時發生錯誤，請稍後再試。"
        )
        return

    # 讀取所有 embeddings，計算相似度
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT diary_date, chunk_index, content_chunk, embedding "
            "FROM diary_embeddings WHERE user_id = ? ORDER BY diary_date DESC",
            (user_id,),
        ).fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 找不到任何 Embedding 記錄，請先執行 /sync_all。"
        )
        return

    # 計算每個 chunk 的相似度
    scored: list[dict] = []
    for row in rows:
        try:
            # 從 BLOB 反序列化向量（float32）
            vec = np.frombuffer(row["embedding"], dtype=np.float32)
            score = _cosine_similarity(query_vec, vec)
            scored.append({
                "diary_date": row["diary_date"],
                "chunk_index": row["chunk_index"],
                "content_chunk": row["content_chunk"],
                "score": score,
            })
        except Exception as e:
            logger.warning(f"向量解析失敗 {row['diary_date']} chunk {row['chunk_index']}: {e}")

    if not scored:
        await update.message.reply_text(
            "⚠️ 向量比對時發生問題，請稍後再試。"
        )
        return

    # 依相似度降冪排序
    scored.sort(key=lambda x: x["score"], reverse=True)

    # 去重：同日期只保留相似度最高的那段（已排序，取第一個出現的日期）
    seen_dates: set[str] = set()
    top_hits: list[dict] = []
    for item in scored:
        if item["diary_date"] not in seen_dates:
            seen_dates.add(item["diary_date"])
            top_hits.append(item)
        if len(top_hits) >= _TOP_K:
            break

    # 篩掉相似度極低的結果（< 0.1 視為無關）
    top_hits = [h for h in top_hits if h["score"] >= 0.1]

    if not top_hits:
        await update.message.reply_text(
            f"🔍 找不到與「{query}」相關的日記內容。\n\n"
            "建議試試其他關鍵字，例如：\n"
            "• 人名或地點\n"
            "• 特定事件或心情\n"
            "• 具體活動描述"
        )
        return

    # AI 彙整
    try:
        summary = await _summarize_results(query, top_hits)
    except Exception as e:
        logger.error(f"AI 彙整失敗：{e}")
        # 降級：直接列出相關段落
        lines = [f"🔍 「{query}」的相關日記片段：\n"]
        for h in top_hits:
            lines.append(f"📅 {h['diary_date']}（相似度 {h['score']:.2f}）\n{h['content_chunk']}")
        summary = "\n\n".join(lines)

    # 附上來源日期列表
    date_list = "、".join(h["diary_date"] for h in top_hits)
    result_msg = (
        f"🔍 **搜尋：{query}**\n"
        f"📅 來源日記：{date_list}\n\n"
        f"{summary}"
    )

    # 訊息超過 4096 字元時分段發送（AI 生成內容不使用 Markdown 解析，避免特殊字元導致 BadRequest）
    if len(result_msg) <= 4096:
        await update.message.reply_text(result_msg, parse_mode=None)
    else:
        await update.message.reply_text(
            f"🔍 搜尋：{query}\n📅 來源日記：{date_list}",
            parse_mode=None,
        )
        for i in range(0, len(summary), 4000):
            await update.message.reply_text(summary[i:i + 4000], parse_mode=None)

    logger.info(
        f"使用者 {user_id} 搜尋「{query}」，回傳 {len(top_hits)} 筆結果"
    )


def register_search_handlers(app: Application):
    """註冊 /search 指令處理器"""
    app.add_handler(CommandHandler("search", cmd_search))
    logger.info("已註冊 /search 處理器")
