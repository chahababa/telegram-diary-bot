# SPEC — Telegram 日記助理 Bot v2

> 本規格書供 IDE AI（Claude Code / Cursor）直接讀取並執行開發。
> 專案採分階段開發，每個 Stage 結束都是一個可獨立運行的穩定版本。

---

## 1. Project Overview

為「板橋好初早餐」老闆打造的個人日記助理 Telegram Bot。使用者全天隨時透過文字或語音記錄生活片段，每晚自動觸發回顧問卷，凌晨由 GPT 彙整成結構化日記並上傳至 Google Drive。本次為 v2 全面重寫，主要改進：資料庫改用 Supabase（雲端 PostgreSQL）、新增 Web 管理儀表板、AI 日記嚴禁捏造資訊、採分階段開發確保每步可回退。

---

## 2. Target Environment

| 項目 | 規格 |
|---|---|
| 語言 | Python 3.11+ |
| Bot 框架 | python-telegram-bot 20.x（async） |
| AI 服務 | OpenAI API — Whisper（語音轉文字）、GPT-4o（日記產出） |
| 資料庫 | Supabase（PostgreSQL + REST API），使用 `supabase-py` SDK |
| 雲端儲存 | Google Drive API（Service Account） |
| 排程 | APScheduler 3.x（AsyncIOScheduler） |
| 儀表板 | Streamlit（獨立 Web 介面） |
| 時區 | Asia/Taipei（預設） |
| 部署環境 | 本地 Windows（開發）；未來可遷移至 VPS |
| 使用者數量 | 單人（不需多使用者架構） |

---

## 3. File & Folder Structure

```
telegram-diary-bot-v2/
├── .env                        # 環境變數（不進版控）
├── .env.example                # 環境變數範本
├── .gitignore
├── requirements.txt
├── README.md
├── SPEC-telegram-diary-bot-v2.md  # 本規格書
│
├── bot/                        # Telegram Bot 主程式
│   ├── __init__.py
│   ├── main.py                 # Bot 入口
│   ├── config.py               # 環境設定載入
│   │
│   ├── handlers/               # 訊息與指令處理
│   │   ├── __init__.py
│   │   ├── command_handler.py  # /start, /today, /score, /diary, /status
│   │   ├── message_handler.py  # 文字、語音、不支援的媒體
│   │   └── questionnaire_handler.py  # 問卷對話流程
│   │
│   ├── services/               # 商業邏輯
│   │   ├── __init__.py
│   │   ├── voice_service.py    # 語音下載 + Whisper 轉文字
│   │   ├── diary_service.py    # AI 日記產出
│   │   ├── gdrive_service.py   # Google Drive 上傳
│   │   └── scheduler_service.py # 排程管理
│   │
│   ├── db/                     # 資料庫層
│   │   ├── __init__.py
│   │   └── supabase_client.py  # Supabase 連線與 CRUD
│   │
│   └── utils/                  # 工具函式
│       ├── __init__.py
│       ├── logger.py           # 統一 logging 設定
│       └── error_handler.py    # 全域錯誤處理
│
├── dashboard/                  # Streamlit 管理儀表板
│   ├── app.py                  # 儀表板入口
│   └── pages/                  # 多頁面
│       ├── settings.py         # 提醒時間、問卷範本設定
│       ├── entries.py          # 查看歷史紀錄
│       └── diaries.py         # 查看歷史日記
│
├── templates/
│   └── diary_prompt.txt        # GPT 日記產出的 Prompt 範本
│
└── tests/                      # 測試（每個 Stage 驗收用）
    ├── test_stage1_db.py
    ├── test_stage2_voice.py
    ├── test_stage3_scheduler.py
    ├── test_stage4_diary.py
    ├── test_stage5_gdrive.py
    └── test_stage6_dashboard.py
```

---

## 4. Core Features & Acceptance Criteria

### 4.1 文字紀錄
- **功能**：使用者在 Telegram 傳送文字訊息，Bot 自動存入 Supabase。
- **完成定義**：傳送一則文字後，Bot 回覆確認訊息，且在 Supabase `diary_entries` 表中可查到該筆資料。

### 4.2 語音紀錄
- **功能**：使用者傳送語音訊息，Bot 下載後透過 Whisper API 轉為文字，存入 Supabase。
- **完成定義**：傳送語音後，Bot 回覆轉寫結果，且 `diary_entries` 中 `source_type` 為 `voice`、`content` 為轉寫文字。

### 4.3 查看當日紀錄（/today）
- **功能**：列出今天所有已記錄的片段，含時間戳與來源圖示（🎤/📝）。
- **完成定義**：執行 `/today` 後顯示當天所有 entries，格式清晰、按時間排序。

### 4.4 心情評分（/score）
- **功能**：設定當天的心情分數（-2 到 2）。
- **完成定義**：`/score 1` 執行後，`daily_summaries` 對應日期的 `mood_score` 更新為 1，Bot 回覆確認。

### 4.5 定時提醒
- **功能**：依據 `bot_settings` 中設定的時段，主動發送提醒訊息。
- **完成定義**：在設定的時間點（預設 9, 12, 15, 18, 21 時），Bot 發送提醒；Bot 重啟後不會重複發送已發過的提醒。

### 4.6 問卷流程
- **功能**：每晚在設定時間（預設 23:00）觸發結算問卷，依照 `bot_settings.questionnaire_template` 逐題發問。
- **完成定義**：Bot 依序發出每道問題 → 使用者回覆 → 答案存入 `daily_summaries.questionnaire_answers` → 全部答完後 Bot 回覆「問卷完成」。23:50 未答完的自動結算。

### 4.7 AI 日記產出（自動 + /diary 手動）
- **功能**：凌晨在設定時間（預設 00:00）自動產出前一天的日記；或使用者手動觸發 `/diary`。
- **完成定義**：日記包含當天所有紀錄與問卷回答，發送至 Telegram。**AI 嚴禁捏造任何不存在的資訊**，若無資料則標註「未記錄」。
- **AI 約束（寫入 Prompt）**：
  - 只能使用使用者實際提供的內容來組織日記
  - 不可推測地點、人物、事件
  - 若某類別無資料，必須標註「未記錄」
  - 不可添加使用者未提及的情感判斷或建議

### 4.8 Google Drive 上傳
- **功能**：日記產出後自動上傳至指定 Google Drive 資料夾。
- **完成定義**：上傳成功後 Bot 回覆確認訊息，`daily_summaries.diary_uploaded` 設為 true。失敗時暫存本地並標記為未上傳。

### 4.9 狀態查詢（/status）
- **功能**：顯示今日的紀錄筆數、問卷進度、心情分數、日記產出狀態。
- **完成定義**：執行 `/status` 後顯示完整的當日狀態摘要。

### 4.10 Web 管理儀表板
- **功能**：Streamlit 網頁介面，可修改提醒時間、問卷範本、日記產出時間，可查看歷史紀錄與日記。
- **完成定義**：在瀏覽器開啟後能看到所有設定項，修改後儲存至 Supabase，Bot 在下次排程檢查時讀取新設定。

---

## 5. Data Structure

### 5.1 Supabase 資料表

#### `diary_entries` — 每日片段紀錄

| 欄位 | 型別 | 約束 | 說明 |
|---|---|---|---|
| id | UUID | PRIMARY KEY, DEFAULT uuid_generate_v4() | 自動產生 |
| date | DATE | NOT NULL | 紀錄日期（Asia/Taipei） |
| time | TIME | NOT NULL | 紀錄時間 |
| content | TEXT | NOT NULL | 紀錄內容 |
| source_type | TEXT | NOT NULL, CHECK IN ('text', 'voice') | 來源類型 |
| created_at | TIMESTAMPTZ | DEFAULT now() | 建立時間 |

#### `daily_summaries` — 每日彙整

| 欄位 | 型別 | 約束 | 說明 |
|---|---|---|---|
| id | UUID | PRIMARY KEY, DEFAULT uuid_generate_v4() | 自動產生 |
| date | DATE | UNIQUE, NOT NULL | 日期（每天一筆） |
| questionnaire_answers | JSONB | DEFAULT '{}' | 問卷回覆，key-value 對應 template |
| questionnaire_step | INTEGER | DEFAULT 0 | 目前回答到第幾題 |
| mood_score | INTEGER | CHECK BETWEEN -2 AND 2 | 心情分數 |
| diary_output | TEXT | | AI 產出的日記全文 |
| diary_uploaded | BOOLEAN | DEFAULT false | 是否已上傳 Google Drive |
| created_at | TIMESTAMPTZ | DEFAULT now() | 建立時間 |

#### `bot_settings` — 系統設定（儀表板可編輯）

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY, 固定為 1 | 單人只需一列 |
| reminder_hours | JSONB | [9, 12, 15, 18, 21] | 提醒時段 |
| questionnaire_hour | INTEGER | 23 | 問卷觸發時間 |
| diary_generation_hour | INTEGER | 0 | 日記產出時間 |
| questionnaire_template | JSONB | （見下方） | 問卷範本 |
| gpt_model | TEXT | "gpt-4o" | GPT 模型 |
| diary_prompt_template | TEXT | （見 templates/diary_prompt.txt） | 日記 Prompt 範本 |
| timezone | TEXT | "Asia/Taipei" | 時區 |
| updated_at | TIMESTAMPTZ | DEFAULT now() | 最後更新時間 |

`questionnaire_template` 預設值：
```json
[
  {"key": "most_important", "question": "今天最重要的一件事是什麼？", "type": "text"},
  {"key": "gratitude", "question": "今天感恩的三件事？（用逗號分隔）", "type": "list"},
  {"key": "mood", "question": "今天的心情分數？(-2 到 2)", "type": "score"},
  {"key": "supplement", "question": "還有什麼想補充的嗎？", "type": "text"}
]
```

#### `scheduler_state` — 排程狀態追蹤

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | INTEGER | PRIMARY KEY, 固定為 1 |
| last_reminder_sent | TIMESTAMPTZ | 上次提醒發送時間 |
| last_questionnaire_sent | DATE | 上次問卷發送日期 |
| last_diary_generated | DATE | 上次日記產出日期 |

### 5.2 questionnaire_answers 範例

當問卷範本有 4 題時，完成後的 JSONB 內容如下：
```json
{
  "most_important": "完成了新菜單的定價",
  "gratitude": ["員工很配合", "客人給了好評", "天氣很好"],
  "mood": 1,
  "supplement": "明天要記得訂蛋"
}
```

---

## 6. UI/UX Description

### 6.1 Telegram Bot 介面

**歡迎訊息（/start）：**
```
👋 嗨！我是你的日記助理。
隨時傳文字或語音給我，我會幫你記下來。
每晚 23:00 我會問你幾個問題回顧今天，
凌晨會自動幫你整理成一篇完整的日記。

📌 可用指令：
/today — 查看今天的紀錄
/score — 設定心情分數
/diary — 手動產出日記
/status — 查看今日狀態
```

**紀錄確認回覆：**
- 文字：`📝 已記錄（今日第 N 筆）`
- 語音：`🎤 語音已轉文字並記錄（今日第 N 筆）：「轉寫內容前30字...」`

**問卷流程：**
- 逐題發問，格式為：`📋 問題 X/Y：\n{問題內容}`
- 全部答完：`✅ 問卷完成！今晚會幫你整理日記。`
- 超時結算：`⏰ 問卷回覆時間已截止，將以目前收集到的資料產出日記。`
- 取消問卷：使用者輸入 `/cancel` 可中止問卷流程

**不支援的訊息類型（圖片、貼圖、影片等）：**
```
⚠️ 目前只支援文字和語音訊息喔！
```

### 6.2 Streamlit 管理儀表板

**頁面 1 — 設定 (settings.py)：**
- 提醒時段：多選核取方塊（0-23 時），勾選後即為提醒時段
- 問卷觸發時間：下拉選單（0-23 時）
- 日記產出時間：下拉選單（0-23 時）
- 問卷範本編輯器：表格式介面，每一列為一道問題，可新增/刪除/修改問題文字與類型
- GPT 模型選擇：下拉選單
- 日記 Prompt 範本：多行文字輸入框
- 儲存按鈕 → 寫入 Supabase `bot_settings`

**頁面 2 — 歷史紀錄 (entries.py)：**
- 日期選擇器
- 顯示該日所有 diary_entries，含時間、來源圖示、內容
- 簡易統計：當日筆數、文字/語音比例

**頁面 3 — 歷史日記 (diaries.py)：**
- 日期選擇器
- 顯示該日的 AI 日記全文
- 顯示問卷回答、心情分數
- 上傳狀態標示

---

## 7. Step-by-Step Implementation Plan

> ⚠️ **重要開發原則**：
> - 每個 Stage 結束時必須是一個可獨立運作的穩定版本。
> - 每個 Stage 開始前，先用 git 建立一個 tag（例如 `git tag stage-1-complete`），這樣任何時候出問題都能 `git checkout stage-X-complete` 回退到上一個穩定版本。
> - 每個 Stage 結尾都有測試步驟，測試通過才算完成。

---

### 🏗️ Stage 0：專案初始化與 Supabase 設定（預估 15 分鐘）

**目標**：建好專案骨架與雲端資料庫，確認環境可用。

**步驟：**

0.1. 建立專案資料夾 `telegram-diary-bot-v2/`，依照第 3 節的結構建立所有資料夾與空的 `__init__.py`。

0.2. 建立 `.env.example`，包含以下變數：
```
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
GOOGLE_DRIVE_FOLDER_ID=
GOOGLE_SERVICE_ACCOUNT_JSON=credentials.json
```

0.3. 建立 `.gitignore`，排除：`.env`、`venv/`、`__pycache__/`、`*.pyc`、`*.db`、`credentials.json`、`*.ogg`、`bot.log`。

0.4. 建立 `requirements.txt`：
```
python-telegram-bot[job-queue]==20.7
openai>=1.12.0
python-dotenv>=1.0.0
APScheduler>=3.10.4
google-api-python-client>=2.111.0
google-auth>=2.25.0
supabase>=2.0.0
streamlit>=1.30.0
```

0.5. 建立 `bot/config.py`，從 `.env` 載入所有環境變數。

0.6. 登入 Supabase Dashboard，建立新專案，然後在 SQL Editor 中執行以下 SQL 建立四張表（依照第 5 節的 schema）。

0.7. 建立 `bot/db/supabase_client.py`，實作：
- `get_client()` — 回傳 Supabase client 實例
- `test_connection()` — 簡單的讀寫測試

0.8. 建立 `bot/utils/logger.py`，統一 logging 設定：
- 輸出到 console + `bot.log`
- 設定 httpx logger 為 WARNING 等級（避免 Token 洩漏在 log 中）
- 設定 log rotation（每 5MB 輪轉，保留 3 個備份）

0.9. **測試**：執行 `python -c "from bot.db.supabase_client import test_connection; test_connection()"` 確認連線成功。

0.10. `git init` → `git add .` → `git commit -m "Stage 0: project init + Supabase connection"` → `git tag stage-0-complete`

---

### 🏗️ Stage 1：Bot 骨架 + 文字紀錄（預估 30 分鐘）

**目標**：Bot 能啟動、接收文字訊息、存入 Supabase、用 /today 查看。

**前置依賴**：Stage 0 完成

**步驟：**

1.1. 建立 `bot/main.py`：
- 載入 config
- 驗證 TELEGRAM_BOT_TOKEN 是否存在
- 建立 Application 實例
- 註冊 handlers（先只註冊文字相關的）
- 註冊全域 error handler
- 啟動 polling

1.2. 建立 `bot/utils/error_handler.py`：
- 實作 `async def error_handler(update, context)` 函式
- 記錄完整錯誤到 log
- 如果有 update.effective_chat，回覆使用者「發生錯誤，請稍後再試」
- 在 main.py 中用 `application.add_error_handler(error_handler)` 註冊

1.3. 建立 `bot/db/supabase_client.py` 的 CRUD 函式：
- `add_entry(date, time, content, source_type)` — 新增一筆 diary_entry
- `get_entries_by_date(date)` — 取得指定日期的所有 entries
- `count_entries_by_date(date)` — 計算指定日期的 entry 數量

1.4. 建立 `bot/handlers/command_handler.py`：
- `cmd_start(update, context)` — 回覆歡迎訊息（參照第 6.1 節）
- `cmd_today(update, context)` — 從 Supabase 讀取今天的 entries 並列出

1.5. 建立 `bot/handlers/message_handler.py`：
- `handle_text_message(update, context)` — 解析時間、存入 Supabase、回覆確認
- `handle_unsupported(update, context)` — 回覆「只支援文字和語音」

1.6. 在 `main.py` 中註冊所有 handlers：CommandHandler（start, today）、MessageHandler（TEXT, PHOTO 等）。

1.7. **測試**：
- 啟動 Bot → 傳送 `/start` → 收到歡迎訊息 ✅
- 傳送一則文字 → 收到「已記錄」確認 ✅
- 傳送 `/today` → 看到剛才的紀錄 ✅
- 傳送圖片 → 收到「不支援」提示 ✅
- 到 Supabase Dashboard 確認 diary_entries 有資料 ✅

1.8. `git add .` → `git commit -m "Stage 1: bot skeleton + text recording"` → `git tag stage-1-complete`

---

### 🏗️ Stage 2：語音轉文字（預估 20 分鐘）

**目標**：語音訊息能被 Whisper 轉成文字並存入資料庫。

**前置依賴**：Stage 1 完成

**步驟：**

2.1. 建立 `bot/services/voice_service.py`：
- `async download_and_transcribe(voice_file, bot)` — 從 Telegram 下載 .ogg → 呼叫 OpenAI Whisper API（language="zh"）→ 回傳轉寫文字
- 自動重試機制（最多 2 次）
- 完成後清理暫存的 .ogg 檔案

2.2. 更新 `bot/handlers/message_handler.py`：
- 新增 `handle_voice_message(update, context)` — 下載 → 轉寫 → 存入 Supabase（source_type='voice'）→ 回覆轉寫結果

2.3. 在 `main.py` 中新增 voice handler 的註冊。

2.4. **測試**：
- 傳送一段語音 → Bot 回覆轉寫結果 ✅
- `/today` 能看到語音紀錄（帶 🎤 圖示）✅
- Supabase 中 source_type 為 'voice' ✅
- 傳送語音後 Bot 工作目錄中沒有殘留的 .ogg 檔 ✅

2.5. `git add .` → `git commit -m "Stage 2: voice transcription"` → `git tag stage-2-complete`

---

### 🏗️ Stage 3：排程提醒 + 問卷流程（預估 45 分鐘）

**目標**：定時提醒、問卷觸發與回覆全部走通。

**前置依賴**：Stage 2 完成

**步驟：**

3.1. 更新 `bot/db/supabase_client.py`，新增：
- `get_settings()` — 讀取 bot_settings（id=1）
- `get_or_create_summary(date)` — 取得或建立當日 daily_summary
- `update_summary_field(date, field, value)` — 更新指定欄位
- `get_summary(date)` — 取得當日 summary
- `is_questionnaire_complete(date)` — 判斷問卷是否已完成
- `get_scheduler_state()` — 讀取排程狀態
- `update_scheduler_state(field, value)` — 更新排程狀態

3.2. 建立 `bot/services/scheduler_service.py`：
- `init_scheduler(bot)` — 初始化 APScheduler，從 `bot_settings` 讀取排程設定
- `send_reminder()` — 發送提醒，發送前檢查 `scheduler_state` 避免重複
- `send_questionnaire()` — 發送問卷第一題，同時在 context 中設定問卷狀態
- `auto_close_questionnaire()` — 23:50 超時自動結算
- `shutdown_scheduler()` — 關閉排程器
- **關鍵修正**：排程器每次觸發時重新從 Supabase 讀取 `bot_settings`，這樣儀表板改設定後不需重啟 Bot

3.3. 建立 `bot/handlers/questionnaire_handler.py`：
- 使用 `ConversationHandler` 實作問卷流程
- Entry point：由 scheduler 呼叫時透過 `context.bot.send_message` 發出第一題，並設定 `context.user_data['questionnaire_active'] = True`
- 每個 state 處理一道問題的回覆 → 存入 `daily_summaries.questionnaire_answers` → 發出下一題
- **動態問卷**：從 `bot_settings.questionnaire_template` 讀取題目，不寫死在程式中
- Fallback：`/cancel` 可中止問卷
- 問卷完成後 `questionnaire_active = False`

3.4. 更新 `bot/handlers/message_handler.py`：
- `handle_text_message` 增加檢查：如果問卷正在進行中，不要重複記錄為一般 entry（交給 ConversationHandler 處理）

3.5. 更新 `bot/handlers/command_handler.py`：
- 新增 `cmd_score(update, context)` — 設定心情分數
- 新增 `cmd_status(update, context)` — 顯示今日狀態

3.6. 更新 `main.py`：
- 註冊 questionnaire_handler（注意：ConversationHandler 的優先順序要在一般 MessageHandler 之前）
- 註冊 score、status 指令
- 在 post_init 中呼叫 init_scheduler
- 在 post_shutdown 中呼叫 shutdown_scheduler

3.7. **測試**：
- 等到提醒時間（或暫時把提醒時間改成當前時間）→ 收到提醒 ✅
- 重啟 Bot → 不會重複發送同一個提醒 ✅
- 問卷觸發 → 依序回答 4 題 → 收到「問卷完成」✅
- Supabase `daily_summaries.questionnaire_answers` 有正確的 JSONB 資料 ✅
- `/score 1` → 確認分數已更新 ✅
- `/status` → 看到正確的狀態摘要 ✅
- `/cancel` → 問卷中止 ✅

3.8. `git add .` → `git commit -m "Stage 3: scheduler + questionnaire"` → `git tag stage-3-complete`

---

### 🏗️ Stage 4：AI 日記產出（預估 30 分鐘）

**目標**：GPT 能根據當日紀錄與問卷，產出結構化日記。

**前置依賴**：Stage 3 完成

**步驟：**

4.1. 建立 `templates/diary_prompt.txt`，內容為 GPT 的系統 Prompt：
```
你是一位私人日記整理助手。請根據以下使用者提供的「當日紀錄」與「問卷回答」，整理成一篇結構化日記。

## 嚴格規則
- 只能使用使用者實際提供的內容，嚴禁推測、捏造或補充任何不存在的資訊。
- 若某類別（如地點、人物）使用者未提及，該欄位必須標註「未記錄」，不得自行填入。
- 不可添加使用者未表達的情感判斷、建議或評論。
- 日記語氣應為中性、忠實記錄，使用正體中文。

## 日記格式
### 📅 {日期} {星期}

#### 📖 今日時間軸
（按時間排列使用者的紀錄，保留原意，可適度潤飾語句但不改變事實）

#### 📍 今日地點
（僅列出使用者明確提及的地點，未提及則寫「未記錄」）

#### 👥 今日遇到的人
（僅列出使用者明確提及的人物，未提及則寫「未記錄」）

#### ⭐ 今天最重要的事
（來自問卷回答，若未回答則寫「未記錄」）

#### 🙏 今日感恩
（來自問卷回答，若未回答則寫「未記錄」）

#### 🎭 心情指數
（來自問卷回答或 /score 指令，若未設定則寫「未記錄」）

#### 📝 補充
（來自問卷回答，若未回答則寫「無」）
```

4.2. 建立 `bot/services/diary_service.py`：
- `async generate_diary(date)` — 主函式
  - 從 Supabase 讀取當天的 entries + summary
  - 如果 entries 為 0 筆且問卷未完成 → 回傳「今天沒有任何紀錄」
  - 如果 entries < 2 筆且問卷未完成 → 產出精簡版日記（純條列，不經 GPT）
  - 否則 → 組合 Prompt（讀取 templates/diary_prompt.txt + 當日資料）→ 呼叫 GPT → 回傳日記
- GPT 呼叫設定：temperature=0.3（降低創意度以避免捏造），max_tokens=2000
- 失敗時 fallback 到精簡版日記
- 產出後將日記寫入 `daily_summaries.diary_output`

4.3. 更新 `bot/handlers/command_handler.py`：
- 新增 `cmd_diary(update, context)` — 手動觸發日記產出
- 日記超過 4096 字元時分段傳送（每段 4000 字元）

4.4. 更新 `bot/services/scheduler_service.py`：
- 在 `trigger_diary_generation()` 中呼叫 `generate_diary()` → 傳送至 Telegram
- 檢查 `scheduler_state.last_diary_generated` 避免重複產出

4.5. 更新 `main.py`，註冊 `/diary` 指令。

4.6. **測試**：
- 先錄幾筆紀錄 + 完成問卷 → `/diary` → 收到 AI 日記 ✅
- 日記中不包含任何你沒提過的地點、人物、事件 ✅
- 只有 1 筆紀錄 + 沒有問卷 → 產出精簡版日記 ✅
- 0 筆紀錄 → 收到「今天沒有紀錄」✅
- 暫時關掉 OpenAI Key → 仍能產出精簡版日記（fallback）✅
- Supabase `daily_summaries.diary_output` 有日記全文 ✅

4.7. `git add .` → `git commit -m "Stage 4: AI diary generation"` → `git tag stage-4-complete`

---

### 🏗️ Stage 5：Google Drive 上傳（預估 20 分鐘）

**目標**：日記自動備份至 Google Drive。

**前置依賴**：Stage 4 完成

**步驟：**

5.1. 建立 `bot/services/gdrive_service.py`：
- `_get_drive_service()` — 建立 Google Drive API client，支援環境變數（雲端部署）與 credentials.json（本地開發）
- `async upload_diary(date, content)` — 上傳 markdown 檔至指定資料夾，自動重試（最多 3 次），回傳 file_id
- `async save_diary_locally(date, content)` — 失敗時暫存至 `local_diaries/` 資料夾

5.2. 更新 `bot/services/scheduler_service.py`：
- `trigger_diary_generation()` 中，日記產出後呼叫 `upload_diary()`
- 上傳成功 → 更新 `diary_uploaded = True` + 通知使用者
- 上傳失敗 → 本地暫存 + 通知使用者

5.3. 更新 `bot/handlers/command_handler.py`：
- `cmd_diary` 中也加入上傳邏輯

5.4. **測試**：
- `/diary` → 日記產出 + 上傳成功 → 收到 Google Drive 確認訊息 ✅
- Google Drive 指定資料夾中有對應的 .md 檔案 ✅
- 暫時改壞 credentials → 收到「上傳失敗，已暫存本地」✅
- `local_diaries/` 資料夾中有暫存檔 ✅

5.5. `git add .` → `git commit -m "Stage 5: Google Drive upload"` → `git tag stage-5-complete`

---

### 🏗️ Stage 6：Streamlit 管理儀表板（預估 40 分鐘）

**目標**：Web 介面可管理所有設定、查看歷史資料。

**前置依賴**：Stage 5 完成

**步驟：**

6.1. 建立 `dashboard/app.py`：
- Streamlit 多頁面應用程式入口
- 側邊欄顯示頁面導覽：設定、歷史紀錄、歷史日記
- 頁面標題：「📔 日記助理管理後台」

6.2. 建立 `dashboard/pages/settings.py`：
- 從 Supabase 讀取 `bot_settings`（id=1）
- 提醒時段：24 個核取方塊（0-23 時），已勾選的高亮顯示
- 問卷觸發時間：數字輸入或下拉
- 日記產出時間：數字輸入或下拉
- 問卷範本編輯器：用 `st.data_editor` 呈現表格，欄位為 key、question、type，可新增/刪除列
- GPT 模型：下拉選單（gpt-4o、gpt-4o-mini 等）
- 日記 Prompt 範本：`st.text_area`，可直接編輯
- 「儲存設定」按鈕 → 更新 Supabase `bot_settings`

6.3. 建立 `dashboard/pages/entries.py`：
- 日期選擇器（預設今天）
- 從 Supabase 讀取該日 `diary_entries`
- 以卡片或表格形式顯示：時間 | 來源圖示 | 內容
- 底部統計：筆數、文字/語音比例

6.4. 建立 `dashboard/pages/diaries.py`：
- 日期選擇器
- 從 Supabase 讀取 `daily_summaries`
- 顯示：AI 日記全文、問卷回答、心情分數、上傳狀態
- 若日記未產出，顯示「尚未產出」

6.5. **測試**：
- 執行 `streamlit run dashboard/app.py` → 瀏覽器開啟 ✅
- 修改提醒時段 → 儲存 → Supabase 中 bot_settings 已更新 ✅
- 新增一道問卷問題 → 儲存 → 下次問卷流程會多一題 ✅
- 歷史紀錄頁面能看到之前的 entries ✅
- 歷史日記頁面能看到之前產出的日記 ✅

6.6. `git add .` → `git commit -m "Stage 6: Streamlit dashboard"` → `git tag stage-6-complete`

---

## 8. Edge Cases & Error Handling

| # | 情境 | 處理方式 | 所屬 Stage |
|---|---|---|---|
| E1 | Supabase 連線失敗 | 啟動時檢查連線，失敗則 log 錯誤並退出，提示使用者檢查 .env | Stage 0 |
| E2 | Telegram Bot Token 無效 | 啟動時驗證，無效則 log 錯誤並退出 | Stage 1 |
| E3 | 使用者傳送不支援的訊息類型 | 回覆「只支援文字和語音」 | Stage 1 |
| E4 | 語音轉文字失敗（Whisper API 錯誤） | 重試 2 次，仍失敗則回覆使用者「語音轉寫失敗，請改用文字」，不寫入 entry | Stage 2 |
| E5 | 暫存 .ogg 檔案清理失敗 | log warning，不影響主流程 | Stage 2 |
| E6 | Bot 重啟後重複發送提醒 | 檢查 `scheduler_state.last_reminder_sent`，同一時段不重複發送 | Stage 3 |
| E7 | 問卷進行中使用者傳送一般文字 | ConversationHandler 優先捕獲，不重複記錄為 diary_entry | Stage 3 |
| E8 | 問卷 23:50 仍未完成 | 自動結算，以已收集的回答產出日記 | Stage 3 |
| E9 | /score 輸入不合法（非 -2~2 的整數） | 回覆格式提示，不更新分數 | Stage 3 |
| E10 | 當天零紀錄 + 零問卷 | 不產出日記，發訊息告知「今天沒有紀錄」 | Stage 4 |
| E11 | GPT API 呼叫失敗 | Fallback 到精簡版日記（純條列紀錄） | Stage 4 |
| E12 | AI 日記內容超過 Telegram 4096 字元限制 | 分段傳送（每段 4000 字元） | Stage 4 |
| E13 | AI 捏造不存在的資訊 | Prompt 層嚴格約束 + temperature=0.3 降低幻覺 | Stage 4 |
| E14 | Google Drive 上傳失敗 | 暫存本地 + 標記為未上傳 + 通知使用者 | Stage 5 |
| E15 | Google credentials 無效 | log 錯誤 + 暫存本地 + 通知使用者檢查設定 | Stage 5 |
| E16 | 儀表板儲存設定後 Bot 未讀取新值 | Bot 的排程器每次觸發時重新從 Supabase 讀取設定，無需重啟 | Stage 6 |
| E17 | 全域未捕獲的例外 | `error_handler.py` 捕獲 → 記錄完整 traceback → 回覆使用者「發生錯誤」 | 全 Stage |
| E18 | Bot Token 出現在 log 中 | logger.py 中設定 httpx logger 為 WARNING 等級，不記錄 HTTP URL | 全 Stage |

---

## 附錄：回退指南

> 當某個 Stage 出問題且無法修復時，使用以下指令回退到上一個穩定版本：

```bash
# 查看所有穩定版本
git tag -l "stage-*"

# 回退到指定版本（例如回退到 Stage 3）
git checkout stage-3-complete

# 如果要在回退的版本上繼續開發
git checkout -b fix-from-stage-3
```

| 回退到 | 你仍然可以用的功能 |
|---|---|
| stage-0-complete | 專案骨架 + Supabase 連線 |
| stage-1-complete | 文字紀錄 + /today + /start |
| stage-2-complete | 上述 + 語音轉文字 |
| stage-3-complete | 上述 + 定時提醒 + 問卷 + /score + /status |
| stage-4-complete | 上述 + AI 日記產出 + /diary |
| stage-5-complete | 上述 + Google Drive 上傳 |
| stage-6-complete | 上述 + Web 管理儀表板（完整版） |
