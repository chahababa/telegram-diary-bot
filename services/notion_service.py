"""
Notion 服務模組 — 負責將日記推送至 Notion 資料庫
"""

import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Callable, Optional

from notion_client import Client
from notion_client.errors import APIResponseError
from openai import AsyncOpenAI

import config as _cfg
from models.database import Database

logger = logging.getLogger(__name__)

# 允許的標籤清單
_ALLOWED_TAGS = ["工作", "生活", "旅行", "美食", "健康", "反思"]

# 每個 Notion paragraph block 的最大字元數
_BLOCK_MAX_CHARS = 2000
_MAX_NOTION_RETRIES = 4

# ── 模組層級單例 ──────────────────────────────────

_notion: Optional[Client] = None
_ai: Optional[AsyncOpenAI] = None
_db: Optional[Database] = None
_data_source_id: Optional[str] = None


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


def _get_data_source_id() -> str:
    """取得日記資料庫的 data source ID（新版 Notion API 建頁需使用）。"""
    global _data_source_id
    if _data_source_id:
        return _data_source_id

    if _cfg.NOTION_DIARY_DATA_SOURCE_ID:
        _data_source_id = _cfg.NOTION_DIARY_DATA_SOURCE_ID
        return _data_source_id

    if not _cfg.NOTION_DIARY_DB_ID:
        raise RuntimeError("NOTION_DIARY_DB_ID 未設定")

    database = _get_notion().databases.retrieve(database_id=_cfg.NOTION_DIARY_DB_ID)
    data_sources = database.get("data_sources", [])
    if not data_sources:
        raise RuntimeError("Notion database 找不到 data source")
    if len(data_sources) > 1:
        raise RuntimeError("Notion database 有多個 data source，請設定 NOTION_DIARY_DATA_SOURCE_ID")

    _data_source_id = data_sources[0]["id"]
    return _data_source_id


# ── 公開 API ──────────────────────────────────────

def is_available() -> bool:
    """檢查 Notion 整合是否已設定。"""
    return bool(_cfg.NOTION_TOKEN and (_cfg.NOTION_DIARY_DATA_SOURCE_ID or _cfg.NOTION_DIARY_DB_ID))


def validate_database_schema() -> tuple[bool, list[str]]:
    """檢查 Notion 日記資料庫是否有程式需要的欄位與型別。"""
    if not is_available():
        return False, ["NOTION_TOKEN 與 NOTION_DIARY_DB_ID / NOTION_DIARY_DATA_SOURCE_ID 需先設定"]

    required = {
        "標題": "title",
        "日期": "date",
        "心情分數": "select",
        "標籤": "multi_select",
    }
    try:
        data_source = _get_notion().data_sources.retrieve(data_source_id=_get_data_source_id())
        properties = data_source.get("properties", {})
    except Exception as e:
        return False, [f"無法讀取 Notion data source: {e}"]

    errors = []
    for name, expected_type in required.items():
        actual = properties.get(name, {}).get("type")
        if actual != expected_type:
            errors.append(f"{name} 需為 {expected_type}，目前是 {actual or '不存在'}")
    return not errors, errors


async def _call_notion(method: Callable[..., Any], *args, **kwargs) -> Any:
    """呼叫 Notion API，遇到 rate limit 或暫時性錯誤時退避重試。"""
    for attempt in range(_MAX_NOTION_RETRIES):
        try:
            return method(*args, **kwargs)
        except APIResponseError as e:
            is_retryable = e.status == 429 or e.status >= 500
            is_last_attempt = attempt == _MAX_NOTION_RETRIES - 1
            if not is_retryable or is_last_attempt:
                raise

            retry_after = e.headers.get("retry-after")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = 1.0
            else:
                delay = min(2 ** attempt, 8)

            logger.warning(
                "Notion API 暫時失敗，準備重試 "
                f"(status={e.status}, code={e.code}, attempt={attempt + 1}/{_MAX_NOTION_RETRIES}, delay={delay}s)"
            )
            await asyncio.sleep(delay)


async def _list_child_blocks(page_id: str) -> list[dict]:
    """分頁取回頁面第一層 blocks。"""
    notion = _get_notion()
    blocks: list[dict] = []
    start_cursor: Optional[str] = None

    while True:
        params: dict[str, Any] = {"block_id": page_id, "page_size": 100}
        if start_cursor:
            params["start_cursor"] = start_cursor

        response = await _call_notion(notion.blocks.children.list, **params)
        blocks.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        start_cursor = response.get("next_cursor")
        if not start_cursor:
            break

    return blocks


async def _find_page_id_by_date(diary_date: str) -> Optional[str]:
    """用日期從 Notion 找既有頁面，避免本機同步紀錄遺失時重複建立。"""
    notion = _get_notion()
    response = await _call_notion(
        notion.data_sources.query,
        data_source_id=_get_data_source_id(),
        filter={
            "property": "日期",
            "date": {
                "equals": diary_date,
            },
        },
        page_size=2,
    )
    pages = response.get("results", [])
    if not pages:
        return None
    if len(pages) > 1:
        logger.warning(f"Notion 已有多個 {diary_date} 頁面，將更新第一筆以避免再建立重複頁")
    return pages[0]["id"]


async def _append_blocks(page_id: str, content_blocks: list[dict]) -> None:
    """分批追加 blocks。"""
    notion = _get_notion()
    for i in range(0, len(content_blocks), 100):
        await _call_notion(
            notion.blocks.children.append,
            block_id=page_id,
            children=content_blocks[i:i + 100],
        )


async def _replace_page_blocks(page_id: str, content_blocks: list[dict]) -> None:
    """刪除頁面舊 blocks 後寫入新內容。"""
    notion = _get_notion()
    old_blocks = await _list_child_blocks(page_id)
    for block in old_blocks:
        try:
            await _call_notion(notion.blocks.delete, block_id=block["id"])
        except Exception as del_err:
            logger.warning(f"刪除舊 block 失敗 ({block['id']}): {del_err}")

    await _append_blocks(page_id, content_blocks)


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
            max_tokens=50,
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
            max_tokens=30,
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
    if not existing_page_id:
        existing_page_id = await _find_page_id_by_date(diary_date)

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
            await _call_notion(
                notion.pages.update,
                page_id=existing_page_id,
                properties=properties,
            )

            await _replace_page_blocks(existing_page_id, content_blocks)
            page_id = existing_page_id
            logger.info(f"Notion 頁面已更新 — user={user_id} date={diary_date} page={page_id}")

        else:
            # ── 建立新頁面 ────────────────────────
            response = await _call_notion(
                notion.pages.create,
                parent={"type": "data_source_id", "data_source_id": _get_data_source_id()},
                properties=properties,
                children=content_blocks[:100],  # 建立時最多帶 100 個 blocks
            )
            page_id = response["id"]

            # 若 blocks 超過 100 個，分批追加
            await _append_blocks(page_id, content_blocks[100:])
            logger.info(f"Notion 頁面已建立 — user={user_id} date={diary_date} page={page_id}")

        # ── 寫入同步紀錄 ──────────────────────────
        with db._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO notion_sync_log "
                "(user_id, diary_date, notion_page_id, synced_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, diary_date, page_id, now_str),
            )

        # ── 觸發 Embedding 生成與儲存（失敗不影響主流程）──
        try:
            from services.embedding_service import store_embeddings
            await store_embeddings(user_id, diary_date, diary_content)
        except Exception as emb_err:
            logger.warning(f"Embedding 儲存失敗，不影響主流程 — user={user_id} date={diary_date}: {emb_err}")

        return True

    except Exception as e:
        logger.error(f"推送 Notion 失敗 — user={user_id} date={diary_date}: {e}")
        return False
