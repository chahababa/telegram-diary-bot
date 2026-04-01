# 📔 Telegram 日記助理 Bot v2 — 完整使用說明書

> 為「板橋好初早餐」老闆打造的個人日記助理 Telegram Bot
> 最後更新：2026-04-01

---

## 📋 目錄

1. [專案概覽](#專案概覽)
2. [系統架構](#系統架構)
3. [功能說明](#功能說明)
4. [Bot 指令一覽](#bot-指令一覽)
5. [每日使用流程](#每日使用流程)
6. [儀表板操作指南](#儀表板操作指南)
7. [技術細節](#技術細節)
8. [日後維護操作指南](#日後維護操作指南)
9. [常見問題排除](#常見問題排除)
10. [帳號與憑證清單](#帳號與憑證清單)

---

## 專案概覽

這是一個透過 Telegram 記錄每日生活片段的日記助理 Bot。你可以隨時用文字或語音傳送訊息，Bot 會自動儲存。每晚會觸發問卷回顧今天，凌晨自動產出一篇 AI 結構化日記並上傳到 Google Drive 備份。

### 核心特色

- **文字 + 語音記錄**：隨時傳訊息，Bot 自動存檔
- **語音智慧辨識**：支援「常用字」功能，辨識你的人名、地名更準確
- **每日問卷回顧**：每晚 23:00 自動觸發，也可隨時手動填寫
- **AI 日記產出**：GPT-4o 整理成結構化日記，嚴禁捏造內容
- **Google Drive 備份**：日記自動上傳雲端保存
- **Web 管理儀表板**：手機也能調整設定、查看歷史

---

## 系統架構

```
使用者（Telegram）
    ↓
Telegram Bot（Zeabur 雲端）
    ↓
Supabase（資料庫）← → Streamlit 儀表板（Zeabur 雲端）
    ↓
OpenAI Whisper（語音轉文字）
OpenAI GPT-4o（日記產出）
    ↓
Google Drive（日記備份）
```

### 服務部署位置

| 服務 | 平台 | 網址 |
|---|---|---|
| Telegram Bot | Zeabur | 透過 Telegram 使用 |
| 管理儀表板 | Zeabur | https://telemattdiarybot.zeabur.app |
| 資料庫 | Supabase | https://echljgsvumlhnbrxeopm.supabase.co |
| 程式碼 | GitHub | https://github.com/chahababa/telegram-diary-bot |

---

## 功能說明

### 1. 文字記錄
直接在 Telegram 傳文字訊息，Bot 會自動記錄並回覆「📝 已記錄（今日第 N 筆）」。

### 2. 語音記錄
傳送語音訊息，Bot 透過 OpenAI Whisper 轉成文字後儲存。會顯示轉寫結果讓你確認。

> 💡 在儀表板的「常用字」功能中加入你的常用人名、地名，可以提升語音辨識準確度。

### 3. 每日問卷
每晚 23:00 自動觸發，共 4 題：
1. 今天感恩的三件人事物
2. 今天的心情分數（-2 到 2）
3. 今天有什麼學習或想法
4. 今天有沒有非常值得記錄的時刻

也可以隨時用 `/survey` 手動填寫，不需等到 23:00。

### 4. AI 日記產出
凌晨 00:00 自動產出前一天的日記，也可用 `/diary` 手動觸發。日記格式包含：
- 📖 今日時間軸
- 📍 今日地點
- 👥 今日遇到的人
- ⭐ 今天最重要的事
- 🙏 今日感恩
- 🎭 心情指數
- 📝 補充

> ⚠️ AI 嚴格遵守「不捏造」原則：你沒提到的地點、人物、事件，日記中不會出現。

### 5. Google Drive 備份
日記產出後自動上傳至 Google Drive 指定資料夾，格式為 `diary_2026-04-01.md`。

### 6. 定時提醒
在設定的時段（預設 9, 12, 15, 18, 21 時）發送提醒，提醒你記錄生活片段。

---

## Bot 指令一覽

| 指令 | 功能 |
|---|---|
| `/start` | 啟動日記助理，顯示歡迎訊息 |
| `/today` | 查看今天所有的紀錄 |
| `/survey` | 手動填寫每日回顧問卷 |
| `/score 1` | 設定今天的心情分數（-2 到 2） |
| `/diary` | 手動產出今天的 AI 日記 |
| `/status` | 查看今日狀態摘要 |
| `/cancel` | 取消進行中的問卷 |

### 心情分數對照

| 分數 | 意義 |
|---|---|
| -2 | 😢 很差 |
| -1 | 😕 不太好 |
| 0 | 😐 普通 |
| 1 | 🙂 不錯 |
| 2 | 😄 很好 |

---

## 每日使用流程

### 白天（隨時）
1. 想到什麼就傳文字或語音給 Bot
2. 遇到提醒訊息時，記錄當下的生活片段

### 晚上（23:00 或任何時候）
1. 等 Bot 自動發送問卷，或主動按 `/survey`
2. 依序回答 4 題問卷
3. 如果來不及回答，23:50 會自動結算

### 凌晨（自動）
1. Bot 自動產出前一天的 AI 日記
2. 自動上傳至 Google Drive
3. 日記會傳送到 Telegram 讓你確認

### 隨時可做
- `/today` 查看今天記了什麼
- `/status` 確認今天的進度
- `/diary` 隨時手動產出日記

---

## 儀表板操作指南

### 存取方式
在任何裝置的瀏覽器開啟：**https://telemattdiarybot.zeabur.app**

### 頁面 1：⚙️ 設定

| 設定項目 | 說明 |
|---|---|
| 🔔 提醒時段 | 勾選 0-23 時，勾選的時段會發送提醒 |
| 📋 問卷觸發時間 | 預設 23:00 |
| 📖 日記產出時間 | 預設 00:00 |
| 🤖 GPT 模型 | 預設 gpt-4o，可選 gpt-4o-mini 省錢 |
| 📋 問卷範本 | 可新增/刪除/修改問卷題目 |
| 📝 日記 Prompt 範本 | 可自訂日記的格式和風格 |
| 🗣️ 常用字 | 語音辨識常用詞彙（每行一個） |

> 💡 修改設定後點「💾 儲存設定」，Bot 會在下次排程檢查時自動讀取新設定，不需要重啟。

### 頁面 2：📝 歷史紀錄
- 選擇日期，查看該天所有的文字和語音紀錄
- 顯示統計：總筆數、文字/語音比例

### 頁面 3：📖 歷史日記
- 選擇日期，查看 AI 產出的日記全文
- 顯示問卷回答、心情分數、上傳狀態

---

## 技術細節

### 技術架構

| 項目 | 技術 |
|---|---|
| 語言 | Python 3.12（本地）/ 3.13（雲端） |
| Bot 框架 | python-telegram-bot 22.x |
| AI 服務 | OpenAI Whisper（語音）、GPT-4o（日記） |
| 資料庫 | Supabase（PostgreSQL） |
| 雲端儲存 | Google Drive API（OAuth 2.0） |
| 排程 | APScheduler（AsyncIOScheduler） |
| 儀表板 | Streamlit |
| 部署 | Zeabur |
| 版本控制 | GitHub |

### 資料庫結構（Supabase）

| 表名 | 用途 |
|---|---|
| `diary_entries` | 每日片段紀錄（文字/語音） |
| `daily_summaries` | 每日彙整（問卷答案、心情分數、AI 日記） |
| `bot_settings` | 系統設定（提醒時段、問卷範本、常用字等） |
| `scheduler_state` | 排程狀態追蹤（避免重複發送） |

### 程式碼結構

```
telegram-diary-bot/
├── bot/                    # Telegram Bot 主程式
│   ├── main.py             # Bot 入口
│   ├── config.py           # 環境設定
│   ├── handlers/           # 訊息與指令處理
│   │   ├── command_handler.py
│   │   ├── message_handler.py
│   │   └── questionnaire_handler.py
│   ├── services/           # 商業邏輯
│   │   ├── voice_service.py
│   │   ├── diary_service.py
│   │   ├── gdrive_service.py
│   │   └── scheduler_service.py
│   ├── db/
│   │   └── supabase_client.py
│   └── utils/
│       ├── logger.py
│       └── error_handler.py
├── dashboard/              # Streamlit 儀表板
│   ├── app.py
│   └── pages/
│       ├── settings.py
│       ├── entries.py
│       └── diaries.py
└── templates/
    └── diary_prompt.txt    # AI 日記 Prompt 範本
```

### Git 版本標籤

| 標籤 | 功能 |
|---|---|
| `stage-0-complete` | 專案初始化 + Supabase 連線 |
| `stage-1-complete` | Bot 骨架 + 文字紀錄 |
| `stage-2-complete` | 語音轉文字 |
| `stage-3-complete` | 排程提醒 + 問卷流程 |
| `stage-4-complete` | AI 日記產出 |
| `stage-5-complete` | Google Drive 上傳 |
| `stage-6-complete` | Streamlit 儀表板 + 常用字功能 |

---

## 日後維護操作指南

### 情境 1：修改程式碼後部署

```bash
# 1. 在本地修改程式碼
# 2. 推到 GitHub，Zeabur 會自動重新部署
cd "c:/Users/chaha/Desktop/Vibe Coding/telegram-diary-bot"
git add .
git commit -m "描述你改了什麼"
git push
```

### 情境 2：在本地開發測試

```bash
# 先到 Zeabur 暫停 Bot 服務（避免 Token 衝突）
# 然後在本地啟動
cd "c:/Users/chaha/Desktop/Vibe Coding/telegram-diary-bot"
./venv312/Scripts/python -m bot.main

# 儀表板
./venv312/Scripts/streamlit run dashboard/app.py
```

> ⚠️ 同一個 Bot Token 只能有一個實例在跑。本地測試前一定要先暫停 Zeabur 上的 Bot 服務。

### 情境 3：更新問卷題目
1. 打開儀表板 → ⚙️ 設定
2. 在「問卷範本」表格中修改題目
3. 點「💾 儲存設定」
4. 不需要重啟 Bot

### 情境 4：新增常用字
1. 打開儀表板 → ⚙️ 設定
2. 在「🗣️ 常用字」區塊，每行輸入一個詞彙
3. 點「💾 儲存設定」

### 情境 5：調整提醒時段
1. 打開儀表板 → ⚙️ 設定
2. 勾選/取消勾選時段
3. 點「💾 儲存設定」

### 情境 6：Google Drive Token 過期
Google OAuth Token 會自動 refresh，但如果超過 6 個月沒使用可能會失效。解法：
1. 在本地執行：
```bash
cd "c:/Users/chaha/Desktop/Vibe Coding/telegram-diary-bot"
del token.json
./venv312/Scripts/python -c "from bot.services.gdrive_service import _get_drive_service; _get_drive_service()"
```
2. 瀏覽器會開啟，重新登入授權
3. 讀取新的 `token.json` 內容，更新 Zeabur 的 `GOOGLE_OAUTH_TOKEN_JSON` 環境變數
4. 重新部署

### 情境 7：回退到穩定版本

```bash
# 查看所有版本
git tag -l "stage-*"

# 回退到指定版本
git checkout stage-3-complete

# 如果要在回退版本上繼續開發
git checkout -b fix-from-stage-3
```

### 情境 8：查看 Zeabur 部署記錄
1. 登入 Zeabur → 選擇專案 → 選擇服務
2. 點「記錄」查看 Runtime Logs
3. 如果服務異常，點「重新部署」或「重啟目前版本」

---

## 常見問題排除

### Bot 沒有回應
1. 確認 Zeabur 上的 Bot 服務狀態是「運作中」
2. 確認本地沒有同時在跑 Bot（Token 衝突）
3. 到 Zeabur 記錄查看錯誤訊息

### 語音辨識不準確
1. 到儀表板 → 設定 → 常用字
2. 加入你常講的人名、地名、專有名詞
3. 儲存後，下次語音辨識就會優先使用這些字

### Google Drive 上傳失敗
1. 檢查 Zeabur 環境變數 `GOOGLE_OAUTH_TOKEN_JSON` 是否存在
2. Token 可能過期，參考「情境 6：Google Drive Token 過期」重新授權

### 問卷重複觸發或不觸發
1. 到 Supabase Dashboard → `scheduler_state` 表
2. 檢查 `last_questionnaire_sent` 欄位
3. 如需重設，把該欄位設為 NULL

### 儀表板打不開
1. 確認 Zeabur 上的儀表板服務狀態是「運作中」
2. 確認網址：https://telemattdiarybot.zeabur.app
3. 到 Zeabur 記錄查看錯誤

---

## 帳號與憑證清單

| 服務 | 帳號/位置 | 用途 |
|---|---|---|
| Telegram Bot | @你的bot名稱 | 日記助理 |
| GitHub | chahababa | 程式碼版本控制 |
| Zeabur | GitHub 登入 | 雲端部署 |
| Supabase | Supabase Dashboard | 資料庫管理 |
| Google Cloud | chahababa@gmail.com | Google Drive API |
| OpenAI | OpenAI Platform | Whisper + GPT-4o |

### 重要檔案（僅在本地，不上傳 GitHub）

| 檔案 | 用途 |
|---|---|
| `.env` | 所有 API Key 和密鑰 |
| `credentials.json` | Google Service Account 金鑰（已棄用） |
| `oauth_credentials.json` | Google OAuth 用戶端憑證 |
| `token.json` | Google OAuth 授權 Token |

### Zeabur 環境變數

| 變數名 | 用途 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `OPENAI_API_KEY` | OpenAI API 金鑰 |
| `SUPABASE_URL` | Supabase 專案 URL |
| `SUPABASE_KEY` | Supabase API Key |
| `GOOGLE_DRIVE_FOLDER_ID` | Google Drive 資料夾 ID |
| `GOOGLE_OAUTH_TOKEN_JSON` | Google OAuth Token（JSON 字串） |

---

> 📌 如果遇到任何問題，可以到 GitHub repo 的程式碼中查看，或重新開一個 Claude Code 對話協助排除。
