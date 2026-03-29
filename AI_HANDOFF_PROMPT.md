# AI 接手 Prompt — Telegram 日記助理 Bot

> 把這整份文件貼給下一個 AI 助手（Claude、ChatGPT、Cursor 等），讓它快速了解專案現況並接手開發。

---

## 你的角色

你正在接手一個做到一半的 Telegram Bot 專案。使用者是「板橋好初早餐」的老闆（共 4 間店），他是程式初學者，請用正體中文、白話的方式跟他溝通，一步一步帶他操作。

## 專案概述

這是一個 **Telegram 日記助理 Bot**，功能是：
- 使用者隨時傳文字或語音訊息給 Bot，Bot 自動記錄
- 語音訊息用 OpenAI Whisper 轉成正體中文文字
- 每天 5 個時段提醒記日記（可自訂）
- 每晚 23:00 推送結算問卷（最重要的事、感恩三件事、心情評分、補充）
- 凌晨 00:00 用 GPT-4o 自動彙整當天所有記錄 + 問卷，產出一篇 Markdown 格式日記
- 日記上傳 Google Drive（目前尚未設定憑證，先存本地）
- 管理員可在 Telegram 裡透過指令修改設定，不需要改程式碼

## 技術棧

- **語言**：Python 3.11
- **Bot 框架**：python-telegram-bot v21.6（全 async）
- **AI**：OpenAI API — AsyncOpenAI 客戶端（Whisper + GPT-4o）
- **資料庫**：SQLite（4 張表：entries、surveys、generated_diaries、settings）
- **排程**：APScheduler AsyncIOScheduler
- **雲端儲存**：Google Drive API v3 + Service Account
- **部署**：Zeabur（東京伺服器），連結 GitHub 自動部署
- **版本控制**：Git + GitHub

## 專案結構

```
telegram-diary-bot/
├── main.py                     # 主程式進入點，初始化所有服務 + 註冊排程
├── config.py                   # 從 .env 載入環境變數
├── requirements.txt            # Python 套件清單
├── Procfile                    # Zeabur 部署用（worker: python main.py）
├── runtime.txt                 # Python 版本（python-3.11.11）
├── .env                        # 環境變數（機密，不在 Git 裡）
├── handlers/
│   ├── command_handlers.py     # /start, /today, /score, /diary, /status
│   ├── message_handlers.py     # 文字訊息 + 語音訊息處理
│   ├── survey_handlers.py      # 23:00 晚間問卷（ConversationHandler）
│   └── admin_handlers.py       # 管理員設定指令（/admin, /set_reminder 等）
├── models/
│   └── database.py             # SQLite 操作封裝（EntryRecord, SurveyRecord dataclass）
├── services/
│   ├── ai_service.py           # OpenAI Whisper 轉文字 + GPT-4o 日記生成
│   ├── drive_service.py        # Google Drive 上傳（2 次重試 + 本地備份）
│   └── scheduler_service.py    # APScheduler 排程管理
└── templates/
    └── diary_template.py       # 日記 Markdown 範本 + 提醒訊息文字
```

## 目前狀態：需要你幫忙的事

### 1. 優先事項：推送程式碼並測試語音辨識

有一批修改已寫好但可能尚未推上 GitHub：
- `ai_service.py`：從同步 `OpenAI` 改為 `AsyncOpenAI`（修復語音辨識阻塞問題）
- `ai_service.py`：`transcribe_voice()` 回傳值從 `Optional[str]` 改為 `tuple[Optional[str], Optional[str]]`（文字, 錯誤訊息）
- `message_handlers.py`：已更新為 `text, error_msg = await ai.transcribe_voice(tmp_path)`，失敗時顯示錯誤細節
- `admin_handlers.py`：全新檔案
- `database.py`：新增 settings 表 + get_setting/set_setting
- `main.py`：註冊 admin_handlers

**需要做的事**：
1. 請使用者在終端機執行 `git status` 確認是否有未提交的變更
2. 如果有 → `git add -A` → `git commit -m "描述"` → `git push`
3. 等 Zeabur 自動部署（1-2 分鐘）
4. 請使用者到 Telegram 測試語音訊息
5. 如果失敗，Bot 現在會回傳具體錯誤訊息，根據那個訊息排查

### 2. 排程熱更新（改善項目）

目前用 `/set_reminder` 或 `/set_survey_time` 改設定後，要到 Zeabur 手動 Restart 才會生效。改進方向：修改 `admin_handlers.py` 在設定儲存後，呼叫 `scheduler_service.py` 重新註冊排程任務。

### 3. Google Drive 設定（選用功能）

`drive_service.py` 程式碼已寫好，但使用者還沒設定 Google Service Account。需要引導他：
- 建立 Google Cloud 專案
- 啟用 Google Drive API
- 建立 Service Account 並下載 credentials.json
- 將 credentials.json 放到專案目錄
- 在 Zeabur 環境變數加上 `GOOGLE_DRIVE_FOLDER_ID` 和 `GOOGLE_CREDENTIALS_FILE`

### 4. 未來功能清單

短期：排程熱更新、多管理員支援、日記範本預覽
中期：照片記錄、週報月報、心情圖表、記錄分類標籤
長期：Web 後台、LINE Bot 版本、AI 智慧回饋、團隊日報

## 重要注意事項

1. **使用者是程式初學者**：每個操作都要一步一步帶，告訴他每個指令在做什麼
2. **語言**：全程使用正體中文、台灣用語（品質不是質量、影片不是視頻、專案不是項目）
3. **穩定優先**：決策權重是 穩定 40% > 成本 30% = 創新 30%
4. **部署流程**：改 code → git add → git commit → git push → Zeabur 自動部署
5. **環境變數**：機密資訊都在 .env 和 Zeabur 環境變數裡，不要寫死在程式碼中
6. **詳細文件**：專案裡有 `PROJECT_STATUS.md`，包含完整的功能清單、技術細節、踩坑紀錄，請先閱讀

## 快速上手指令

```bash
# 進入專案
cd Desktop\VibeCoding\telegram-diary-bot

# 看目前狀態
git status

# 本機測試（需要 .env 裡有 API 金鑰）
python main.py

# 推上 GitHub（Zeabur 會自動部署）
git add -A
git commit -m "你的修改描述"
git push
```
