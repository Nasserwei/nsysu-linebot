# 🎓 中山大學資管系新生專屬小幫手

一個結合網路爬蟲、NLP 智慧客服與 LINE Messaging API 的互動式機器人，專為中山大學資管系大一新生設計。

---

## 📁 專案結構

```
nsysu-linebot/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 主程式 / Webhook 入口
│   ├── config.py            # 環境變數設定
│   ├── database.py          # SQLite 資料庫連線與初始化
│   ├── crawler.py           # 中山資管系官網爬蟲模組
│   ├── nlp.py               # NLP 相似度比對模組
│   ├── line_handler.py      # LINE 事件路由處理
│   ├── messages.py          # Flex Message / Template 產生器
│   └── scheduler.py         # APScheduler 定時爬蟲排程
├── data/
│   ├── qa_knowledge.json    # Q&A 知識庫
│   └── nsysu_bot.db         # SQLite 資料庫（自動生成）
├── tests/
│   ├── test_crawler.py
│   ├── test_nlp.py
│   └── test_messages.py
├── scripts/
│   └── run_crawler.py       # 手動觸發爬蟲腳本
├── .env.example             # 環境變數範本
├── requirements.txt
└── README.md
```

---

## 🚀 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入你的 LINE Bot 金鑰
```

### 3. 啟動服務

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 設定 Webhook

使用 ngrok 進行本地測試：
```bash
ngrok http 8000
# 複製 https://xxxx.ngrok.io/webhook 到 LINE Developers Console
```

---

## ⚙️ 環境變數說明

| 變數名稱 | 說明 |
|---|---|
| `LINE_CHANNEL_SECRET` | LINE Bot Channel Secret |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot Channel Access Token |
| `DATABASE_URL` | SQLite 路徑（預設 `data/nsysu_bot.db`）|
| `CRAWLER_INTERVAL_MINUTES` | 爬蟲執行間隔（預設 30 分鐘）|

---

## 🤖 功能說明

### 1. 公告推送
- 定時爬取中山資管系官網最新消息
- 去重機制避免重複推送
- 自動廣播給所有已加入的用戶

### 2. 智慧 Q&A
輸入任何問題，系統會從知識庫中找出最相似的答案：
- 🐒 校園生態（台灣獼猴相關）
- 🍖 美食雷達（燒肉、麻辣推薦）
- 💻 數位優惠（GitHub Copilot、ChatGPT 學生方案）
- 🎉 課外活動（講座、高雄旅遊）

### 3. 選課查詢
透過互動選單查詢：
- 必修課程規定
- 選修學分配置
- 通識課程說明
- 雙主修/輔系資訊
