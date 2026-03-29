"""
Google Drive 服務模組 — 上傳日記 Markdown 檔案至 Google Drive
"""

import logging
import os
from pathlib import Path
from typing import Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import GOOGLE_DRIVE_FOLDER_ID, GOOGLE_CREDENTIALS_FILE, LOCAL_BACKUP_DIR

logger = logging.getLogger(__name__)

# Google Drive API 權限範圍
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveService:
    """封裝 Google Drive API 操作"""

    def __init__(self):
        self.folder_id = GOOGLE_DRIVE_FOLDER_ID
        self.service = None
        self._init_service()

    def _init_service(self):
        """初始化 Google Drive API 服務"""
        creds_path = Path(GOOGLE_CREDENTIALS_FILE)
        if not creds_path.exists():
            logger.warning(
                f"找不到 Google 憑證檔案: {creds_path}。"
                "Google Drive 上傳功能將無法使用。"
                "請參考 README 設定 Service Account。"
            )
            return

        try:
            credentials = Credentials.from_service_account_file(
                str(creds_path), scopes=SCOPES
            )
            self.service = build("drive", "v3", credentials=credentials)
            logger.info("Google Drive API 初始化成功")
        except Exception as e:
            logger.error(f"Google Drive API 初始化失敗: {e}")

    def is_available(self) -> bool:
        """檢查 Drive 服務是否可用"""
        return self.service is not None and bool(self.folder_id)

    async def upload_diary(self, diary_date: str, content: str) -> Optional[str]:
        """
        上傳日記到 Google Drive。
        失敗時重試 2 次，最終失敗則存到本地暫存。
        回傳 Google Drive 檔案 ID 或 None。
        """
        filename = f"diary-{diary_date}.md"

        if not self.is_available():
            logger.warning("Google Drive 服務未就緒，改為本地暫存")
            self._save_local_backup(filename, content)
            return None

        # 先寫入暫存檔
        temp_path = Path(LOCAL_BACKUP_DIR) / filename
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(content, encoding="utf-8")

        # 重試最多 2 次
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                file_metadata = {
                    "name": filename,
                    "parents": [self.folder_id],
                    "mimeType": "text/markdown",
                }

                # 檢查是否已存在同名檔案（覆蓋更新）
                existing_id = self._find_existing_file(filename)

                if existing_id:
                    # 更新現有檔案
                    media = MediaFileUpload(
                        str(temp_path), mimetype="text/markdown"
                    )
                    file = self.service.files().update(
                        fileId=existing_id, media_body=media
                    ).execute()
                    file_id = existing_id
                    logger.info(f"已更新 Google Drive 檔案: {filename} (ID: {file_id})")
                else:
                    # 建立新檔案
                    media = MediaFileUpload(
                        str(temp_path), mimetype="text/markdown"
                    )
                    file = self.service.files().create(
                        body=file_metadata, media_body=media, fields="id"
                    ).execute()
                    file_id = file.get("id")
                    logger.info(f"已上傳至 Google Drive: {filename} (ID: {file_id})")

                # 上傳成功，刪除暫存檔
                temp_path.unlink(missing_ok=True)
                return file_id

            except Exception as e:
                logger.error(f"Google Drive 上傳失敗 (第 {attempt} 次): {e}")
                if attempt >= max_retries:
                    logger.error(f"已達最大重試次數，日記保留在本地: {temp_path}")
                    return None

        return None

    def _find_existing_file(self, filename: str) -> Optional[str]:
        """在目標資料夾中搜尋是否已存在同名檔案"""
        try:
            query = (
                f"name = '{filename}' and '{self.folder_id}' in parents "
                f"and trashed = false"
            )
            results = self.service.files().list(
                q=query, fields="files(id)"
            ).execute()
            files = results.get("files", [])
            return files[0]["id"] if files else None
        except Exception:
            return None

    def _save_local_backup(self, filename: str, content: str) -> str:
        """儲存到本地暫存目錄"""
        backup_dir = Path(LOCAL_BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        filepath = backup_dir / filename
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"日記已本地暫存: {filepath}")
        return str(filepath)
