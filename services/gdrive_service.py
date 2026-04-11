"""
Google Drive 服務模組 — 將日記上傳至 Google Drive
"""

import json
import logging
import tempfile
import os
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import asyncio

import config

logger = logging.getLogger(__name__)

# Google Drive API 範圍
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_drive_service():
    """建立 Google Drive API 服務實例（支援從環境變數或檔案讀取憑證）"""
    # 優先從環境變數讀取（Zeabur / 雲端部署用）
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if credentials_json:
        info = json.loads(credentials_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # 本地開發：從檔案讀取
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE,
            scopes=SCOPES,
        )
    return build("drive", "v3", credentials=creds)


def has_drive_credentials() -> bool:
    """檢查 Google Drive 憑證是否真的存在且可被使用。"""
    credentials_json = config.GOOGLE_CREDENTIALS_JSON or os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if credentials_json:
        try:
            json.loads(credentials_json)
            return True
        except json.JSONDecodeError:
            logger.warning("GOOGLE_CREDENTIALS_JSON 不是合法 JSON")
            return False

    credentials_path = Path(config.GOOGLE_CREDENTIALS_FILE)
    return credentials_path.is_file()


async def upload_diary(date_str: str, diary_content: str, max_retries: int = 3) -> str | None:
    """
    將日記上傳至 Google Drive

    Args:
        date_str: 日期字串 YYYY-MM-DD
        diary_content: 日記 Markdown 全文
        max_retries: 最大重試次數

    Returns:
        上傳成功回傳檔案 ID，失敗回傳 None
    """
    filename = f"diary-{date_str}.md"
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(f"開始上傳日記至 Google Drive（第 {attempt + 1} 次）：{filename}")

            # 寫入暫存檔案
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(diary_content)
                tmp_path = tmp.name

            try:
                service = _get_drive_service()

                file_metadata = {
                    "name": filename,
                    "mimeType": "text/markdown",
                }

                # 如果有指定資料夾 ID
                if config.GOOGLE_DRIVE_FOLDER_ID:
                    file_metadata["parents"] = [config.GOOGLE_DRIVE_FOLDER_ID]

                media = MediaFileUpload(
                    tmp_path,
                    mimetype="text/markdown",
                    resumable=True,
                )

                request = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, webViewLink",
                )
                file = await asyncio.to_thread(request.execute)

                file_id = file.get("id")
                web_link = file.get("webViewLink", "")
                logger.info(f"日記上傳成功：{filename}（ID: {file_id}）")
                return file_id

            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        except Exception as e:
            last_error = e
            logger.warning(f"Google Drive 上傳失敗（第 {attempt + 1} 次）：{e}")

    logger.error(f"Google Drive 上傳最終失敗：{last_error}")
    return None


async def save_diary_locally(date_str: str, diary_content: str) -> str:
    """
    當 Google Drive 上傳失敗時，暫存日記至本地

    Args:
        date_str: 日期字串
        diary_content: 日記內容

    Returns:
        本地檔案路徑
    """
    local_dir = Path("local_diaries")
    local_dir.mkdir(exist_ok=True)

    filename = f"diary-{date_str}.md"
    file_path = local_dir / filename

    file_path.write_text(diary_content, encoding="utf-8")
    logger.info(f"日記已暫存至本地：{file_path}")
    return str(file_path)

async def upload_diary_overwrite(date_str: str, diary_content: str, max_retries: int = 3) -> str | None:
    """
    上傳日記並覆蓋 Google Drive 上的同名檔案。
    若找不到同名檔案，則新建。
    適用於 /editdiary 的更新場景。

    Args:
        date_str: 日期字串 YYYY-MM-DD
        diary_content: 日記 Markdown 全文
        max_retries: 最大重試次數

    Returns:
        成功回傳檔案 ID，失敗回傳 None
    """
    filename = f"diary-{date_str}.md"
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(f"開始覆蓋上傳至 Google Drive（第 {attempt + 1} 次）：{filename}")

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(diary_content)
                tmp_path = tmp.name

            try:
                service = _get_drive_service()

                # 搜尋現有同名檔案
                query = f"name='{filename}' and trashed=false"
                if config.GOOGLE_DRIVE_FOLDER_ID:
                    query += f" and '{config.GOOGLE_DRIVE_FOLDER_ID}' in parents"

                search_results = await asyncio.to_thread(
                    lambda: service.files().list(q=query, fields="files(id)").execute()
                )
                existing_files = search_results.get("files", [])

                media = MediaFileUpload(tmp_path, mimetype="text/markdown", resumable=True)

                if existing_files:
                    # 更新現有檔案（Drive 自動保留版本歷史）
                    file_id = existing_files[0]["id"]
                    request = service.files().update(
                        fileId=file_id,
                        media_body=media,
                        fields="id",
                    )
                    result = await asyncio.to_thread(request.execute)
                    logger.info(f"日記覆蓋更新成功：{filename}（ID: {result.get('id')}）")
                    return result.get("id")
                else:
                    # 找不到舊檔則新建
                    file_metadata = {
                        "name": filename,
                        "mimeType": "text/markdown",
                    }
                    if config.GOOGLE_DRIVE_FOLDER_ID:
                        file_metadata["parents"] = [config.GOOGLE_DRIVE_FOLDER_ID]
                    request = service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields="id",
                    )
                    result = await asyncio.to_thread(request.execute)
                    logger.info(f"日記新建成功：{filename}（ID: {result.get('id')}）")
                    return result.get("id")

            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        except Exception as e:
            last_error = e
            logger.warning(f"upload_diary_overwrite 失敗（第 {attempt + 1} 次）：{e}")

    logger.error(f"upload_diary_overwrite 最終失敗：{last_error}")
    return None


def is_available() -> bool:
    """檢查是否已經設定 Google Drive 相關環境變數"""
    return bool(has_drive_credentials() and config.GOOGLE_DRIVE_FOLDER_ID)
