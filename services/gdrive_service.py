"""
Google Drive 服務模組 — 將日記上傳至 Google Drive
"""

import json
import logging
import tempfile
import os
from dataclasses import dataclass
from pathlib import Path

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import asyncio

import config

logger = logging.getLogger(__name__)

# Google Drive API 範圍
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


@dataclass
class DriveStatus:
    """Google Drive 設定/連線狀態。"""
    configured: bool
    available: bool
    auth_type: str
    message: str


def _load_json_env(value: str, name: str) -> dict:
    """解析 JSON 環境變數，並提供可讀錯誤。"""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(f"{name} 不是合法 JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} 必須是 JSON object")
    return parsed


def _build_oauth_credentials() -> OAuthCredentials | None:
    """從 GOOGLE_OAUTH_TOKEN_JSON 建立 OAuth credentials。"""
    oauth_token_json = config.GOOGLE_OAUTH_TOKEN_JSON or os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "")
    if not oauth_token_json:
        return None

    token_info = _load_json_env(oauth_token_json, "GOOGLE_OAUTH_TOKEN_JSON")
    if "installed" in token_info or "web" in token_info:
        raise ValueError(
            "GOOGLE_OAUTH_TOKEN_JSON 看起來是 OAuth client secret，不是 token。"
            "請提供 authorized-user token JSON（含 refresh_token/client_id/client_secret/token_uri）。"
        )

    missing = [
        key for key in ("refresh_token", "client_id", "client_secret")
        if not token_info.get(key)
    ]
    if missing:
        raise ValueError(
            "GOOGLE_OAUTH_TOKEN_JSON 缺少可刷新 token 必要欄位: "
            + ", ".join(missing)
        )

    creds = OAuthCredentials.from_authorized_user_info(token_info, scopes=SCOPES)
    if not creds.has_scopes(SCOPES):
        raise ValueError(f"GOOGLE_OAUTH_TOKEN_JSON scope 不足，至少需要 {SCOPES[0]}")

    if not creds.valid:
        if not creds.refresh_token:
            raise ValueError("OAuth token 已失效且沒有 refresh_token")
        creds.refresh(Request())
    return creds


def _build_service_account_credentials():
    """從 GOOGLE_CREDENTIALS_JSON 或本機 credentials.json 建立 Service Account credentials。"""
    credentials_json = config.GOOGLE_CREDENTIALS_JSON or os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    if credentials_json:
        info = _load_json_env(credentials_json, "GOOGLE_CREDENTIALS_JSON")
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    credentials_path = Path(config.GOOGLE_CREDENTIALS_FILE)
    if credentials_path.is_file():
        return service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE,
            scopes=SCOPES,
        )

    return None


def _get_drive_credentials():
    """取得 Google Drive credentials，優先使用 OAuth，再退回 Service Account。"""
    oauth_error = None
    try:
        creds = _build_oauth_credentials()
        if creds:
            return creds, "oauth"
    except Exception as e:
        oauth_error = e
        logger.warning(f"GOOGLE_OAUTH_TOKEN_JSON 無法使用: {e}")

    try:
        creds = _build_service_account_credentials()
        if creds:
            return creds, "service_account"
    except Exception as e:
        logger.warning(f"GOOGLE_CREDENTIALS_JSON / credentials file 無法使用: {e}")
        if oauth_error:
            raise RuntimeError(f"OAuth 失敗: {oauth_error}; Service Account 失敗: {e}") from e
        raise

    if oauth_error:
        raise RuntimeError(f"OAuth 設定存在但無法使用: {oauth_error}") from oauth_error
    raise RuntimeError("Google Drive 未設定 OAuth token、Service Account JSON 或 credentials.json")


def _get_drive_service():
    """建立 Google Drive API 服務實例（支援 OAuth Token 或 Service Account）"""
    creds, _auth_type = _get_drive_credentials()
    return build("drive", "v3", credentials=creds)


def has_drive_credentials() -> bool:
    """檢查 Google Drive 憑證是否真的存在且可被使用。"""
    return get_drive_status(validate_remote=False).available


def get_drive_status(validate_remote: bool = False) -> DriveStatus:
    """
    取得 Google Drive 狀態。

    validate_remote=True 時會實際呼叫 Drive API，檢查 credentials 與資料夾可否讀取。
    """
    if not config.GOOGLE_DRIVE_FOLDER_ID:
        return DriveStatus(False, False, "none", "缺少 GOOGLE_DRIVE_FOLDER_ID")

    try:
        creds, auth_type = _get_drive_credentials()
        if not validate_remote:
            return DriveStatus(True, True, auth_type, "credentials 可建立")

        service = build("drive", "v3", credentials=creds)
        folder = service.files().get(
            fileId=config.GOOGLE_DRIVE_FOLDER_ID,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        ).execute()
        if folder.get("mimeType") != "application/vnd.google-apps.folder":
            return DriveStatus(
                True,
                False,
                auth_type,
                "GOOGLE_DRIVE_FOLDER_ID 不是資料夾",
            )
        return DriveStatus(True, True, auth_type, f"資料夾可讀取: {folder.get('name')}")
    except Exception as e:
        return DriveStatus(True, False, "unknown", str(e))


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
                    supportsAllDrives=True,
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
    local_dir = Path(config.LOCAL_BACKUP_DIR)
    local_dir.mkdir(parents=True, exist_ok=True)

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
                    lambda: service.files().list(
                        q=query,
                        fields="files(id)",
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                    ).execute()
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
                        supportsAllDrives=True,
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
                        supportsAllDrives=True,
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
