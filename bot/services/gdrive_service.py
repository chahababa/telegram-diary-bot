"""Google Drive 上傳模組（OAuth 2.0 桌面認證）"""

import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from bot.config import GOOGLE_DRIVE_FOLDER_ID

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
OAUTH_CRED_FILE = "oauth_credentials.json"
TOKEN_FILE = "token.json"
MAX_RETRIES = 3


def _get_drive_service():
    """建立 Google Drive API client（OAuth 2.0）"""
    creds = None

    # 嘗試從 token.json 讀取已儲存的認證
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # 如果沒有有效的認證，執行授權流程
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CRED_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # 儲存認證供下次使用
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        logger.info("Google OAuth 認證已更新")

    return build("drive", "v3", credentials=creds)


async def upload_diary(date: str, content: str) -> str | None:
    """上傳日記 markdown 檔至 Google Drive，回傳 file_id"""
    filename = f"diary_{date}.md"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            service = _get_drive_service()
            media = MediaInMemoryUpload(
                content.encode("utf-8"),
                mimetype="text/markdown",
            )
            file_metadata = {
                "name": filename,
                "parents": [GOOGLE_DRIVE_FOLDER_ID],
            }
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
            ).execute()

            file_id = file.get("id")
            logger.info(f"日記已上傳至 Google Drive: {filename} (id={file_id})")
            return file_id

        except Exception as e:
            logger.warning(f"Google Drive 上傳第 {attempt} 次失敗: {e}")
            if attempt == MAX_RETRIES:
                logger.error(f"Google Drive 上傳失敗，已重試 {MAX_RETRIES} 次: {e}")
                return None

    return None


async def save_diary_locally(date: str, content: str) -> str:
    """上傳失敗時暫存日記至本地"""
    local_dir = "local_diaries"
    os.makedirs(local_dir, exist_ok=True)
    filepath = os.path.join(local_dir, f"diary_{date}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"日記已暫存至本地: {filepath}")
    return filepath
