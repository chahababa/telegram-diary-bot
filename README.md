# 📔 Telegram 日記助理 Bot

每天隨時透過文字或語音記錄生活片段，每晚自動彙整成結構化 Markdown 日記，並同步儲存至 Google Drive。

> 專為「板橋好初早餐」老闆打造的個人日記工具。

## 功能

- **隨時記錄**：傳送文字或語音訊息，自動存入資料庫
- **語音轉文字**：使用 OpenAI Whisper API，支援正體中文
- **定時提醒**：每天 09:00 / 12:00 / 15:00 / 18:00 / 21:00 提醒記日記
- **23:00 結算問卷**：最重要的事 → 感恩 3 件 → 心情評分 → 補充
- **00:00 自動日記**：AI (GPT-4o) 彙整成 Markdown，回傳 Telegram + 上傳 Google Drive
- **管理員指令**：在 Telegram 裡直接修改設定，不需要改程式碼

## 安裝

```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 安裝套件
pip install -r requirements.txt
```

## 設定

1. 複製 `.env.example` 為 `.env`，填入你的 API 金鑰：
   ```
   TELEGRAM_BOT_TOKEN=你的Telegram Bot Token
   OPENAI_API_KEY=你的OpenAI API Key
   GOOGLE_DRIVE_FOLDER_ID=Google Drive 資料夾 ID（選用）
   GOOGLE_CREDENTIALS_FILE=credentials.json（選用）
   ```
2. Google Drive 上傳為選用功能，不設定的話日記會自動備份到本地 `backup_diaries/` 資料夾

## 啟動

```bash
python main.py
```

## Bot 指令

| 指令 | 說明 |
|------|------|
| `/start` | 開始使用日記助理 |
| `/today` | 查看今天的記錄數量 |
| `/score` | 查看近 7 天心情趨勢 |
| `/diary` | 手動產出今天的日記 |
| `/status` | 查看 Bot 運作狀態 |
| `/survey` | 手動開始問卷 |

## 管理員指令

第一次使用 `/set_admin` 的人會自動成為管理員。

| 指令 | 說明 |
|------|------|
| `/admin` | 查看所有管理員指令 |
| `/set_admin` | 設定管理員 |
| `/set_reminder 9 12 18` | 修改提醒時間 |
| `/set_survey_time 22` | 修改問卷開始時間 |
| `/get_template` | 查看目前的日記範本 |
| `/set_template` | 修改日記範本 |
| `/get_reminder_msg` | 查看各時段提醒訊息 |
| `/set_reminder_msg 9 早安！` | 修改某時段的提醒訊息 |
| `/show_settings` | 顯示目前所有設定 |

## 部署

目前部署在 [Zeabur](https://zeabur.com)（東京伺服器），連結 GitHub 後會自動偵測更新並重新部署。

```
Procfile:    worker: python main.py
runtime.txt: python-3.11.11
```

## 技術架構

- Python 3.11 + python-telegram-bot v21 (async)
- OpenAI API：Whisper（語音轉文字）+ GPT-4o（日記生成）
- SQLite（本地資料庫）
- APScheduler（非同步排程）
- Google Drive API v3（日記上傳）

## 詳細專案狀態

請參考 [PROJECT_STATUS.md](./PROJECT_STATUS.md)，裡面有完整的功能清單、待辦事項、技術細節和踩坑紀錄。
