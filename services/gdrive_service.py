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
            config.GOOGLE_SERVICE_ACCOUNT_JSON,
            scopes=SCOPES,
        )
    return build("drive", "v3", credentials=creds)


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
