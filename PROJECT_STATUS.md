# 📋 專案狀態說明書 — Telegram 日記助理 Bot

> 最後更新：2026-03-29
> 擁有者：板橋好初早餐 Hoochuu
> 部署位置：Zeabur（東京伺服器）

---

## 一、這個專案是什麼？

一個 Telegram Bot，讓你每天隨時用文字或語音記錄生活，晚上自動整理成一篇結構化的 Markdown 日記，並同步到 Google Drive。

簡單說就是：**你只管記，Bot 幫你整理成日記。**

---

## 二、目前已完成的功能 ✅

### 核心功能
- [x] 文字訊息記錄（傳文字給 Bot → 自動存入資料庫）
- [x] 語音訊息記錄（傳語音給 Bot → Whisper 轉文字 → 存入資料庫）
- [x] 定時提醒記日記（預設 09:00 / 12:00 / 15:00 / 18:00 / 21:00）
- [x] 23:00 晚間問卷（最重要的事 → 感恩 3 件 → 心情評分 → 補充）
- [x] 23:50 問卷超時自動結算
- [x] 00:00 AI 自動產出 Markdown 日記（GPT-4o）
- [x] 日記上傳 Google Drive（失敗時自動本地備份）
- [x] 跨日歸屬處理（凌晨 0-5 點的記錄歸入前一天）

### Bot 指令
- [x] `/start` — 歡迎訊息 + 使用說明
- [x] `/today` — 查看今天記錄數量（文字/語音分開統計）
- [x] `/score` — 近 7 天心情趨勢圖（文字長條圖）
- [x] `/diary` — 手動產出今天的日記
- [x] `/status` — 查看 Bot 運作狀態 + 排程資訊
- [x] `/survey` — 手動開始問卷

### 管理員功能（不用改程式碼，在 Telegram 裡操作）
- [x] `/admin` — 查看所有管理員指令
- [x] `/set_admin` — 設定管理員（第一個使用的人自動成為管理員）
- [x] `/set_reminder 8 12 18` — 修改提醒時間
- [x] `/set_survey_time 22` — 修改問卷開始時間
- [x] `/get_template` / `/set_template` — 查看/修改日記範本
- [x] `/get_reminder_msg` / `/set_reminder_msg` — 查看/修改各時段提醒訊息
- [x] `/show_settings` — 顯示目前所有設定

### 基礎建設
- [x] SQLite 資料庫（entries、surveys、generated_diaries、settings 四張表）
- [x] 環境變數管理（.env 檔案）
- [x] 日誌記錄（bot.log + 終端機輸出）
- [x] Zeabur 雲端部署設定（Procfile + runtime.txt）
- [x] GitHub 版本控制

---

## 三、尚未完成 / 需要確認的事項 🔧

### 待推送的程式碼變更
> ⚠️ 以下修改已經寫好，但可能還沒推上 GitHub。需要在終端機執行：
> ```
> cd Desktop\VibeCoding\telegram-diary-bot
> git add -A
> git commit -m "fix: 修復語音辨識失敗 + 新增管理員指令"
> git push
> ```

修改內容包含：
1. **ai_service.py** — 改用 `AsyncOpenAI` 非同步客戶端（修復語音辨識卡住的問題）
2. **ai_service.py** — `transcribe_voice` 回傳格式改為 `(text, error_msg)` 元組
3. **message_handlers.py** — 配合新回傳格式，失敗時顯示具體錯誤訊息
4. **admin_handlers.py** — 全新檔案，所有管理員指令
5. **database.py** — 新增 `settings` 資料表 + `get_setting` / `set_setting` 方法
6. **main.py** — 註冊管理員指令處理器 + 更新指令選單

### 語音辨識需要驗證
- 已重寫為非同步版本，但還沒實際測試過
- 推送並部署後，需要在 Telegram 測試語音訊息
- 如果還是失敗，Bot 現在會回傳具體的錯誤訊息（之前只會說「辨識失敗」看不出原因）

### 管理員指令的限制
- `/set_reminder` 和 `/set_survey_time` 改完設定後，**需要在 Zeabur 重新啟動（Restart）才會生效**
- 因為排程是在 Bot 啟動時註冊的，目前不支援熱更新
- 未來可以改成「修改後自動重新註冊排程」就不用重啟了

### Google Drive 上傳
- 目前程式碼已寫好，但還沒設定 Google Service Account 憑證
- 沒有憑證的情況下，日記會自動備份到本地 `backup_diaries/` 資料夾
- 想啟用的話需要：建立 Google Cloud 專案 → 建立 Service Account → 下載 credentials.json → 設定環境變數

---

## 四、使用的技術清單 🛠️

| 類別 | 技術 | 用途 |
|------|------|------|
| 程式語言 | Python 3.11 | 主程式語言 |
| Bot 框架 | python-telegram-bot v21.6 | Telegram Bot API 互動 |
| AI 語音轉文字 | OpenAI Whisper API | 語音訊息 → 正體中文文字 |
| AI 日記生成 | OpenAI GPT-4o | 將記錄彙整成結構化日記 |
| 資料庫 | SQLite | 儲存記錄、問卷、日記、設定 |
| 排程器 | APScheduler (AsyncIOScheduler) | 定時提醒、問卷、日記產出 |
| 雲端儲存 | Google Drive API v3 | 上傳日記 Markdown 檔案 |
| 環境變數 | python-dotenv | 管理 API 金鑰等機密資訊 |
| 時區處理 | pytz | 台灣時區 (Asia/Taipei) |
| 雲端部署 | Zeabur | 24/7 雲端運行（東京伺服器） |
| 版本控制 | Git + GitHub | 程式碼管理與備份 |

### 需要的 API 金鑰
| 金鑰 | 環境變數名稱 | 哪裡取得 |
|------|-------------|---------|
| Telegram Bot Token | `TELEGRAM_BOT_TOKEN` | @BotFather |
| OpenAI API Key | `OPENAI_API_KEY` | platform.openai.com |
| Google Drive 資料夾 ID | `GOOGLE_DRIVE_FOLDER_ID` | Google Drive 網址列 |
| Google 憑證檔案路徑 | `GOOGLE_CREDENTIALS_FILE` | Google Cloud Console |

---

## 五、專案檔案結構 📁

```
telegram-diary-bot/
├── main.py                          # 主程式進入點
├── config.py                        # 設定載入（從 .env）
├── requirements.txt                 # Python 套件清單
├── Procfile                         # Zeabur 部署設定
├── runtime.txt                      # Python 版本指定
├── .env                             # 環境變數（機密，不上傳 GitHub）
├── .gitignore                       # Git 忽略清單
├── diary.db                         # SQLite 資料庫（自動建立）
├── bot.log                          # 執行日誌
├── backup_diaries/                  # Google Drive 上傳失敗時的本地備份
├── handlers/                        # Telegram 訊息/指令處理
│   ├── __init__.py
│   ├── command_handlers.py          # /start, /today, /score 等基本指令
│   ├── message_handlers.py          # 文字訊息 + 語音訊息處理
│   ├── survey_handlers.py           # 23:00 晚間問卷流程
│   └── admin_handlers.py            # 管理員設定指令
├── models/                          # 資料模型
│   ├── __init__.py
│   └── database.py                  # SQLite 資料庫操作
├── services/                        # 外部服務串接
│   ├── __init__.py
│   ├── ai_service.py                # OpenAI Whisper + GPT-4o
│   ├── drive_service.py             # Google Drive 上傳
│   └── scheduler_service.py         # APScheduler 排程管理
└── templates/                       # 範本定義
    ├── __init__.py
    └── diary_template.py            # 日記 Markdown 範本 + 提醒訊息
```

---

## 六、未來可以做的改進 🚀

### 短期（比較簡單）
1. **排程熱更新**：修改提醒時間後不用重啟 Bot 就能生效
2. **多使用者支援**：目前架構已支援，但管理員只有一位，可以加入多管理員
3. **Google Drive 設定引導**：寫一份詳細的 Service Account 設定教學
4. **日記範本預覽**：設定新範本後，用假資料先產出一篇預覽版

### 中期（需要一些開發）
5. **照片記錄**：支援拍照傳給 Bot，自動加入日記
6. **週報 / 月報**：每週日或每月 1 號自動彙整一份總結
7. **心情圖表**：用圖片呈現心情趨勢（目前只有文字長條圖）
8. **分店日報整合**：4 間好初早餐的營運記錄整合到日記
9. **記錄分類標籤**：可以用 #工作 #生活 #靈感 分類記錄

### 長期（比較大的功能）
10. **Web 後台**：做一個網頁版後台，可以瀏覽歷史日記、統計分析
11. **LINE Bot 版本**：除了 Telegram，也做一個 LINE 版
12. **AI 智慧回饋**：根據日記內容給出生活建議或提醒
13. **團隊日報**：讓員工也能用，老闆可以看所有人的日報

---

## 七、曾經遇到的問題與解法 🐛

| 問題 | 原因 | 解法 |
|------|------|------|
| venv 建立失敗 | 掛載磁碟的權限問題 | 改用系統全域安裝 `pip install --break-system-packages` |
| git init 失敗 | `.git/config` 損壞（空白內容） | 刪除 `.git` 資料夾後重新初始化 |
| git commit 失敗 | 沒有設定 git 使用者資訊 | `git config user.email` + `user.name` |
| Bot 在沙盒環境無法啟動 | 沙盒封鎖 Telegram API | 正常現象，在本機或雲端才能執行 |
| Zeabur 部署後 Crashed | 缺少環境變數 | 在 Zeabur 後台加入 4 個環境變數 |
| 語音辨識連續失敗 3 次 | 同步 OpenAI 客戶端阻塞事件迴圈 + 錯誤訊息被吞掉 | 改用 AsyncOpenAI + 回傳錯誤細節 |

---

## 八、怎麼重新開始開發？

如果你隔了一段時間想回來改東西，照這個順序：

1. **看這份文件**：確認上次做到哪裡
2. **打開終端機**，進入專案資料夾：`cd Desktop\VibeCoding\telegram-diary-bot`
3. **檢查 Git 狀態**：`git status`（看有沒有未提交的修改）
4. **拉取最新版本**：`git pull`（如果有在其他地方改過）
5. **開始改 code**，改完後：
   ```
   git add -A
   git commit -m "描述你改了什麼"
   git push
   ```
6. **Zeabur 自動部署**：推上 GitHub 後 Zeabur 會自動偵測並重新部署

如果要在本機測試：
```
python main.py
```
（需要先在 `.env` 填好 API 金鑰）

---

*這份文件由 Claude AI 協助產出，建議每次重大更新後都來更新一下這份說明書。*
