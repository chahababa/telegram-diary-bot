# Changelog

All notable changes to this project will be documented in this file.

## [2026-04-25] Google Drive Diagnostics Hardening

### Summary

Google Drive upload was still falling back to local storage in production. This update makes
Drive auth failures visible in `/status` and supports safer OAuth credential validation.

### Changes

- `config.py` / `.env.example`
  - Add `GOOGLE_OAUTH_TOKEN_JSON`
- `services/gdrive_service.py`
  - Add `DriveStatus` diagnostics
  - Parse OAuth token using `Credentials.from_authorized_user_info`
  - Require refresh-capable OAuth fields: `refresh_token`, `client_id`, `client_secret`
  - Detect accidental OAuth client-secret JSON pasted into `GOOGLE_OAUTH_TOKEN_JSON`
  - Validate scopes and refresh expired OAuth tokens
  - Add `supportsAllDrives=True` to Drive create/update/list calls
  - Add optional remote folder validation for `/status`
- `handlers/command_handlers.py`
  - `/status` now shows Google Drive auth type and actionable configuration errors

### Verification

- Python compile check: OK
- Local Drive status with no local credentials now reports a clear missing-credentials error

### Deployment Notes

After deploying, run `/status`. If Google Drive still shows a warning, update Zeabur's
`GOOGLE_OAUTH_TOKEN_JSON` with an authorized-user token JSON that includes:

```
refresh_token
client_id
client_secret
token_uri
scopes
```

---

## [2026-04-25] Zeabur Production Deployment Verified

### Summary

The latest GitHub `main` was deployed to Zeabur and verified through the live Telegram bot.
Notion sync is now working in production.

### Deployment

- Zeabur build triggered: `69ec81d4...`
- Service state: Running
- Environment variables verified:
  - `NOTION_TOKEN` set as a private variable
  - `NOTION_DIARY_DB_ID=33f6f4831a6180149b6cef91d820981e`
  - `NOTION_DIARY_DATA_SOURCE_ID=33f6f483-1a61-807a-b9c4-000bfafd2d49`

### Live Verification

- `/status`: OK
  - Bot online
  - Notion: connected
  - Google Drive: connected
  - 8 scheduled jobs registered
- `/diary`: OK
  - Generated the 2026-04-25 diary in Markdown
- `/sync`: OK
  - `2026-04-25` diary successfully synced to Notion

### Known Issue

- Google Drive upload still fell back to local storage:
  - `/app/backup_diaries/diary-2026-04-25.md`
- This appears to be the existing Google OAuth token issue and is separate from the Notion deployment.
- Next step: inspect and update `GOOGLE_OAUTH_TOKEN_JSON` / Google Drive auth flow.

---

## [2026-04-25] Notion Sync Hardening + Google Drive Recovery

### Summary

GitHub `main` is now up to date with the latest Notion sync work and recent Google Drive fixes.
The Notion database `日記庫DB` was connected and verified end to end.

### Changes

- `services/notion_service.py`
  - Support Notion's newer data source API via `NOTION_DIARY_DATA_SOURCE_ID`
  - Create new diary pages with `data_source_id` instead of legacy `database_id`
  - Add Notion schema validation for `標題`, `日期`, `心情分數`, and `標籤`
  - Add retry/backoff handling for Notion `429` and `5xx` responses
  - Query Notion by diary date when local `notion_sync_log` is missing, reducing duplicate pages
  - Page through existing blocks before replacing content, instead of only deleting the first page of blocks
- `handlers/command_handlers.py`
  - `/status` now reports Notion connection/schema status
- `config.py` / `.env.example`
  - Add `NOTION_DIARY_DATA_SOURCE_ID`
- Google Drive fixes already on `main`
  - OAuth token support for Google Drive upload
  - Indentation fix in `gdrive_service.py`

### Verification

- Local dependency install: OK (`numpy`, `notion-client`)
- Python compile check: OK
- Notion schema validation: OK
- End-to-end Notion create/read/archive test: OK
- Embedding storage test: OK (`embedding_rows: 3`)
- GitHub push: OK (`4949e24 feat: harden Notion diary sync`)

### Deployment Notes

Set these variables in Zeabur, then restart/redeploy the service:

```
NOTION_TOKEN=<rotated Notion integration token>
NOTION_DIARY_DB_ID=33f6f4831a6180149b6cef91d820981e
NOTION_DIARY_DATA_SOURCE_ID=33f6f483-1a61-807a-b9c4-000bfafd2d49
```

The Notion token used during setup was pasted in chat, so rotate it before production use.

---

## [2026-04-11] Sprint 0 — Notion 同步 + 語意搜尋環境建置

### Changes

- `requirements.txt`：新增 `notion-client>=2.2.1` 與 `numpy>=1.26.0`
- `config.py`：新增 `NOTION_TOKEN` 與 `NOTION_DIARY_DB_ID` 環境變數（預設空字串）
- `.env.example`：新增 Notion 相關變數說明（`NOTION_TOKEN`、`NOTION_DIARY_DB_ID`）
- `models/database.py`：新增兩張資料表
  - `diary_embeddings`：儲存日記向量嵌入（分段）
  - `notion_sync_log`：記錄 Notion 推送歷史（防止重複建立頁面）

## [2026-04-11] Sprint 1 — Notion 推送服務

### Changes

- `services/notion_service.py`：新增 Notion 推送服務
  - `is_available()`：檢查 Notion Token 是否已設定
  - `extract_tags()`：用 GPT 萃取日記標籤（工作／生活／旅行／美食／健康／反思）
  - `extract_title()`：用 GPT 產出 15 字以內的精簡標題
  - `push_diary()`：推送日記到 Notion，支援更新既有頁面與建立新頁面
  - 自動記錄推送結果至 `notion_sync_log` 資料表

---

## [2026-04-10] Deployment Fix & Recovery

### Summary

Zeabur deployment was failing since Apr 7, 2026 due to a missing export in `config.py`.
The service was automatically suspended on Apr 8, 2026 after repeated crash loops.
This entry documents the full diagnosis, fix, and successful redeployment on Apr 10, 2026.

### Root Cause

The deployment from PR #1 (`Merge pull request #1 from chahababa/fix/diary-generation-bugs`)
was built from code that did **not** yet include the `validate_config`, `GPT_MODEL`, and
`LOCAL_BACKUP_DIR` exports in `config.py`. However, `main.py` (line 13) and `ai_service.py`
were already importing them:

```
from config import TELEGRAM_BOT_TOKEN, validate_config, LOCAL_BACKUP_DIR
```

This caused an immediate `ImportError` on startup:

```
ImportError: cannot import name 'validate_config' from 'config' (/app/config.py)
```

The container entered a crash loop (BackOff restart), and Zeabur eventually suspended the
service on Apr 8, 2026.

### Fix Applied (commit ca43163)

The fix was already merged in commit `ca43163` on Apr 8, 2026, which added the missing
exports to `config.py`:

- `GPT_MODEL` — GPT model name, defaults to `gpt-4o`
- `LOCAL_BACKUP_DIR` — local diary backup directory path
- `validate_config()` — startup validation function for required env vars

However, this fix was never deployed because Zeabur had already suspended the service,
and the old deployment image (from the PR #1 merge) was cached and reused on restarts.

### Deployment Recovery (Apr 10, 2026)

**Steps taken:**

- Diagnosed — Reviewed Zeabur runtime logs, confirmed `ImportError` from stale image
- Restart attempted — Clicking "Restart" reused the old cached image, same crash
- Redeploy triggered — Clicked "Redeploy" to force a fresh build from GitHub `main` branch
- Build succeeded — New Docker image built in ~3 minutes from commit `ca43163`
- Bot started successfully — All handlers registered, APScheduler jobs loaded, Telegram polling active

### Deployment Verification

Runtime logs confirmed full startup:

- Command/admin/message handlers registered
- Telegram API: `getMe`, `setMyCommands`, `deleteWebhook`, `getUpdates` all returned HTTP 200
- APScheduler: 8 scheduled jobs active (5 reminders + survey + timeout + diary generation)
- `Application started` — Bot entered polling mode

### Files Verified (no changes needed)

| File | Status | Content |
|------|--------|--------|
| `requirements.txt` | OK | Includes `sqlalchemy>=2.0.0` and all required deps |
| `Procfile` | OK | `worker: python main.py` |
| `runtime.txt` | OK | `python-3.11.11` |
| `.gitignore` | OK | Ignores `.env`, `*.db`, `credentials.json`, etc. |
| `config.py` | OK | All imports available after commit `ca43163` |
| `main.py` | OK | Entry point, no changes needed |

### Environment Variables (Zeabur)

| Variable | Status |
|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Set |
| `OPENAI_API_KEY` | Set |
| `GOOGLE_DRIVE_FOLDER_ID` | Set |
| `TIMEZONE` | Not set (defaults to `Asia/Taipei` in code) |
| `GOOGLE_CREDENTIALS_JSON` | Not set — see known issue below |

### Known Issue: Google Drive Upload

The Zeabur environment has `GOOGLE_OAUTH_TOKEN_JSON` (an OAuth2 access token), but
`config.py` reads `GOOGLE_CREDENTIALS_JSON` and `gdrive_service.py` expects a
**Service Account JSON key** (uses `from_service_account_info()`).

These are incompatible formats. Google Drive upload is currently non-functional.
The bot falls back to local backup when Drive is unavailable.

**To fix:** Create a Google Cloud Service Account, download its JSON key, and set it
as `GOOGLE_CREDENTIALS_JSON` in Zeabur variables.

---

## [2026-04-08] Bug Fixes (commit ca43163)

- Fix `auto_close_questionnaire`: use `completed` field instead of `questionnaire_step`
- Fix `get_diary_date`: use `hour < 4` instead of `hour <= 0` for early morning date attribution
- Add missing exports to `config.py`: `GPT_MODEL`, `LOCAL_BACKUP_DIR`, `validate_config`

## [2026-04-07] PR #1 — Fix Diary Generation Bugs

- Fix `gdrive_service.py`: variable name and `is_available()` logic
- Fix `command_handlers.py`: normalize indentation (IndentationError)
- Add `cmd_diary` try/except error handling

## [2026-04-05] Diary Features

- Add `/backdiary` and `/editdiary` commands
- Add diary history table and related methods
- Update README with `/add` and `/diary` date parameter docs

## [2026-03-30] Deployment Setup

- Add `sqlalchemy` dependency for APScheduler SQLAlchemyJobStore
- Add `Procfile` (`worker: python main.py`)
- Add `runtime.txt` (`python-3.11.11`)

## [2026-03-29] Initial Release

- Initialize Telegram Diary Bot
- Core features: text/voice recording, scheduled reminders, nightly survey, AI diary generation
- Google Drive upload support
- Admin commands for configuration
