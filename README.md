# 📔 Telegram 日記助理 Bot

每天隨時透過文字或語音記錄生活片段，每晚自動彙整成結構化 Markdown 日記，並同步儲存至 Google Drive。

## 功能

- **隨時記錄**：傳送文字或語音訊息，自動存入資料庫
- **定時提醒**：每天 09:00 / 12:00 / 15:00 / 18:00 / 21:00 提醒記日記
- **23:00 結算問卷**：最重要的事 → 感恩 3 件 → 心情評分 → 補充
- **00:00 自動日記**：AI 彙整成 Markdown，回傳 Telegram + 上傳 Google Drive
- **語音轉文字**：使用 OpenAI Whisper API，正體中文

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

1. 複製 `.env.example` 為 `.env`，填入你的 API 金鑰
2. 設定 Google Drive Service Account（選用）

## 啟動

```bash
python main.py
```

## Bot 指令

| 指令     | 說明                 |
|----------|---------------------|
| /start   | 開始使用             |
| /today   | 查看今天的記錄數量   |
| /score   | 查看近 7 天心情趨勢  |
| /diary   | 手動產出今天的日記   |
| /status  | 查看 Bot 運作狀態    |
| /survey  | 手動開始問卷         |
