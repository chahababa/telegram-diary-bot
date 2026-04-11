"""
Notion 服務模組 — 負責將日記推送至 Notion 資料庫
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from notion_client import Client
from openai import AsyncOpenAI

import config as _cfg
from models.database import Database

logger = logging.getLogger(__name__)

# 允許的標籤清單
_ALLOWED_TAGS = ["工作", "生活", "旅行", "美食", "健康", "反思"]

# 每個 Notion paragraph block 的最大字元數
_BLOCK_MAX_CHARS = 2000

# ── 模組層級單例 ──────────────────────────────────

_notion: Optional[Client] = None
_ai: Optional[AsyncOpenAI] = None
_db: Optional[Database] = None


def _get_notion() -> Client:
    """取得 Notion 客戶端（延遲初始化）"""
    global _notion
    if _notion is None:
        _notion = Client(auth=_cfg.NOTION_TOKEN)
    return _notion


def _get_ai() -> AsyncOpenAI:
    """取得 OpenAI 客戶端（延遲初始化）"""
    global _ai
    if _ai is None:
        _ai = AsyncOpenAI(api_key=_cfg.OPENAI_API_KEY)
    return _ai


def _get_db() -> Database:
    """取得資料庫實例（延遲初始化）"""
    global _db
    if _db is None:
        _db = Database()
    return _db


# ── 公開 API ──────────────────────────────────────

def is_available() -> bool:
    """檢查 Notion 整合是否已設定（Token 不為空）"""
    return bool(_cfg.NOTION_TOKEN)


async def extract_tags(diary_content: str) -> list[str]:
    """
    用 OpenAI 從日記內容萃取 1-3 個標籤。
    只能從允許清單中選擇：工作、生活、旅行、美食、健康、反思。
    若日記內容不符合任何標籤，回傳空 list。
    """
    allowed_str = "、".join(_ALLOWED_TAGS)
    prompt = (
        f"請從以下日記內容中，選出最符合的 1 到 3 個標籤。\n"
        f"標籤只能從這個清單中挑選：{allowed_str}\n"
        f"如果日記內容不符合任何標籤，回傳空字串。\n"
        f"回傳格式：只輸出標籤，用逗號分隔，不要有其他文字。例如：工作,生活\n\n"
        f"日記內容：\n{diary_content[:2000]}"
    )
    try:
        response = await _get_ai().chat.completions.create(
            model=_cfg.GPT_MODEL,
            messages=[
                {"role": "system", "content": "你是一個日記分類助手，只輸出標籤，不說其他話。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_completion_tokens=50,
        )
        raw = response.choices[0].message.content.strip()
        if not raw:
            return []
        # 解析逗號分隔的標籤，過濾只保留允許清單中的值
        tags = [t.strip() for t in raw.split(",") if t.strip() in _ALLOWED_TAGS]
        return tags[:3]
    except Exception as e:
        logger.error(f"標籤萃取失敗: {e}")
        return []


async def extract_title(diary_content: str) -> str:
    """
    用 OpenAI 從日記內容產出一個精簡標題（15 字以內）。
    """
    prompt = (
        f"請根據以下日記內容，用正體中文產出一個精簡的標題，不超過 15 個字。\n"
        f"只輸出標題本身，不要加引號或其他說明。\n\n"
        f"日記內容：\n{diary_content[:2000]}"
    )
    try:
        response = await _get_ai().chat.completions.create(
            model=_cfg.GPT_MODEL,
            messages=[
                {"role": "system", "content": "你是一個日記標題產生器，只輸出標題，不說其他話。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_completion_tokens=30,
        )
        title = response.choices[0].message.content.strip()
        # 截斷超過 15 字的標題（保險）
        return title[:15] if title else diary_content[:15]
    except Exception as e:
        logger.error(f"標題萃取失敗: {e}")
        # 萃取失敗時用日記前 15 字作為標題
        return diary_content[:15].strip()


def _split_content_to_blocks(content: str) -> list[dict]:
    """
    將 Markdown 日記內容拆成多個 Notion paragraph block。
    按段落（空行）分割，每個 block 不超過 _BLOCK_MAX_CHARS 字元。
    """
    blocks = []
    # 先按空行分段
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    for para in paragraphs:
        # 若單一段落超過限制，進一步切分
        while len(para) > _BLOCK_MAX_CHARS:
            chunk = para[:_BLOCK_MAX_CHARS]
            blocks.append(_make_paragraph_block(chunk))
            para = para[_BLOCK_MAX_CHARS:]
        if para:
            blocks.append(_make_paragraph_block(para))

    return blocks


def _make_paragraph_block(text: str) -> dict:
    """建立 Notion paragraph block 物件"""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": text},
                }
            ]
        },
    }


async def push_diary(
    user_id: int,
    diary_date: str,
    diary_content: str,
    mood_score: Optional[int],
) -> bool:
    """
    推送日記到 Notion 資料庫。

    流程：
    1. 查詢 notion_sync_log 是否已推送過
    2. 已推送 → 更新既有 Notion 頁面
    3. 未推送 → 建立新 Notion 頁面
    4. 成功後記錄到 notion_sync_log

    回傳是否成功（True/False）。
    """
    if not is_available():
        logger.warning("Notion Token 未設定，跳過推送")
        return False

    db = _get_db()
    tz = ZoneInfo(_cfg.TIMEZONE)
    now_str = datetime.now(tz).isoformat()

    # ── 查詢既有推送紀錄 ──────────────────────────
    with db._get_conn() as conn:
        row = conn.execute(
            "SELECT notion_page_id FROM notion_sync_log "
            "WHERE user_id = ? AND diary_date = ?",
            (user_id, diary_date),
        ).fetchone()

    existing_page_id: Optional[str] = row["notion_page_id"] if row else None

    # ── 萃取標題與標籤 ────────────────────────────
    title = await extract_title(diary_content)
    tags = await extract_tags(diary_content)

    # ── 組合 Notion 頁面屬性 ──────────────────────
    mood_str = str(mood_score) if mood_score is not None else None

    properties: dict = {
        "標題": {
            "title": [
                {"text": {"content": title}}
            ]
        },
        "日期": {
            "date": {"start": diary_date}
        },
    }
    if mood_str is not None:
        properties["心情分數"] = {
            "select": {"name": mood_str}
        }
    if tags:
        properties["標籤"] = {
            "multi_select": [{"name": t} for t in tags]
        }

    # ── 拆分日記內容為 blocks ──────────────────────
    content_blocks = _split_content_to_blocks(diary_content)

    notion = _get_notion()

    try:
        if existing_page_id:
            # ── 更新既有頁面 ──────────────────────
            # 更新屬性
            notion.pages.update(
                page_id=existing_page_id,
                properties=properties,
            )
            # 清除舊 blocks，再重新寫入
            old_blocks = notion.blocks.children.list(block_id=existing_page_id)
            for block in old_blocks.get("results", []):
                try:
                    notion.blocks.delete(block_id=block["id"])
                except Exception as del_err:
                    logger.warning(f"刪除舊 block 失敗 ({block['id']}): {del_err}")

            # 寫入新 blocks（Notion 一次最多 100 個）
            for i in range(0, len(content_blocks), 100):
                notion.blocks.children.append(
                    block_id=existing_page_id,
                    children=content_blocks[i:i + 100],
                )
            page_id = existing_page_id
            logger.info(f"Notion 頁面已更新 — user={user_id} date={diary_date} page={page_id}")

        else:
            # ── 建立新頁面 ────────────────────────
            response = notion.pages.create(
                parent={"database_id": _cfg.NOTION_DIARY_DB_ID},
                properties=properties,
                children=content_blocks[:100],  # 建立時最多帶 100 個 blocks
            )
            page_id = response["id"]

            # 若 blocks 超過 100 個，分批追加
            for i in range(100, len(content_blocks), 100):
                notion.blocks.children.append(
                    block_id=page_id,
                    children=content_blocks[i:i + 100],
                )
            logger.info(f"Notion 頁面已建立 — user={user_id} date={diary_date} page={page_id}")

        # ── 寫入同步紀錄 ──────────────────────────
        with db._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO notion_sync_log "
                "(user_id, diary_date, notion_page_id, synced_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, diary_date, page_id, now_str),
            )
        return True

    except Exception as e:
        logger.error(f"推送 Notion 失敗 — user={user_id} date={diary_date}: {e}")
        return False
