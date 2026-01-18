# Justus OJ (Justus Code Arena)

這是一個基於 **Python Flask** 與 **Docker** 開發的 C++ Online Judge (線上解題系統)。
本系統採用 **容器化沙箱技術** 來執行使用者提交的程式碼，確保伺服器安全，並具備現代化的 UI 設計與完整的後台管理功能。

## ✨ 特色功能 (Features)

### 🛡️ 安全與執行環境 (Core & Security)
* **Docker 沙箱隔離**：所有程式碼皆在獨立、用完即丟的 Docker 容器中執行。
    * **網路阻斷** (`network_disabled=True`)：防止惡意連線。
    * **資源限制**：限制 CPU、記憶體 (128MB) 與 Process 數量，防止惡意消耗資源。
* **安全性檢查**：除了沙箱外，保留基礎關鍵字過濾 (如 `system`, `rm -rf`) 作為第一道防線。
* **Cloudflare 支援**：能正確解析 `CF-Connecting-IP`，在使用 Cloudflare Tunnel 時仍能辨識真實使用者 IP。

### 💻 使用者端 (User Interface)
* **現代化首頁 (Landing Page)**：具備 Hero Banner 與卡片式題目列表的質感首頁。
* **題目瀏覽**：
    * 支援 Markdown 風格的詳細題目敘述。
    * 支援題目圖片顯示。
    * 自動捲動至執行結果。
* **程式碼提交**：支援直接貼上程式碼或上傳 `.cpp` / `.txt` 檔案。
* **即時評測狀態**：
    * `AC` (Accepted)
    * `WA` (Wrong Answer)
    * `CE` (Compilation Error)
    * `RE` (Runtime Error)
    * `TLE` (Time Limit Exceeded - 嚴格逾時強制中斷)
* **頻率限制 (Rate Limiting)**：防止惡意刷題，針對真實 IP 進行冷卻時間限制 (預設 15 秒)。
* **404 導向頁面**：當訪問不存在的題目時，顯示友善的倒數跳轉頁面。

### ⚙️ 管理員後台 (Admin Panel)
* **題目管理**：新增、編輯 (支援回填舊資料)、刪除題目。
* **測資管理**：
    * **範例 (Samples)**：顯示在前端供使用者參考。
    * **隱藏測資 (Test Cases)**：系統批改用的標準輸入/輸出 (JSON 格式儲存)。
* **Log 紀錄系統**：詳細記錄登入、提交、管理操作與錯誤訊息 (`oj_events.log`)。

## 🛠️ 技術堆疊 (Tech Stack)

* **後端**：Python 3, Flask
* **沙箱環境**：Docker Engine, Python Docker SDK
* **資料庫**：SQLite (`cpp_oj.db`)
* **前端**：HTML5, Bootstrap 5 (RWD), JavaScript
* **編譯器**：GCC (Docker image `gcc:latest`)

## 🚀 安裝與執行 (Installation & Setup)

本系統需運行於 **Linux** 環境 (如 Debian/Ubuntu)，並依賴 Docker 進行編譯。

### 1. 安裝系統套件與 Docker

```bash
# 更新並安裝 Docker
sudo apt update
sudo apt install python3-pip docker.io -y

# 啟動 Docker 並設定開機自啟
sudo systemctl start docker
sudo systemctl enable docker

# 將當前使用者加入 docker 群組 (避免 sudo)
sudo usermod -aG docker $USER
# 注意：執行完上述指令後，請登出再登入，或重啟系統以生效。
```

### 2. 準備 Docker 編譯環境

下載 GCC 官方映像檔供沙箱使用：

```bash
docker pull gcc:latest
```

### 3. 安裝 Python 依賴

```bash
pip3 install flask docker
```

### 4. 專案結構

```text
/
├── app.py              # 主程式 (包含路由、Docker 邏輯、Log 系統)
├── cpp_oj.db           # 資料庫 (自動生成)
├── oj_events.log       # 系統日誌 (自動生成)
├── static/
│   ├── uploads/        # 題目圖片存放區
│   └── favicon.ico     # 網站圖示
├── temp_code/          # 暫存原始碼與執行檔 (Docker 掛載點)
├── templates/          # HTML 模板 (home, index, admin, edit, 404...)
└── README.md
```

### 5. 啟動伺服器

```bash
python3 app.py
```

* 預設運行於 `http://0.0.0.0:8080`。
* 初次執行會自動初始化資料庫與資料表。

## ⚙️ 設定 (Configuration)

您可以在 `app.py` 中修改以下重要設定：

* **管理員密碼**：
```python
ADMIN_PASSWORD = 'Xiang520'  # 請修改為您的密碼
```


* **Secret Key**：
```python
app.secret_key = 'justus_secret_key' # 用於 Session 加密
```


* **頻率限制**：
```python
RATE_LIMIT_SECONDS = 15 # 提交冷卻時間
```


* **Docker 映像檔**：
```python
DOCKER_IMAGE = 'gcc:latest'
```


## 📝 Log 查看方式

系統會將重要事件記錄於 `oj_events.log`，格式為 `<IP> : <時間> : <事件>`。

## ⚠️ 部署注意事項

* **Cloudflare Tunnel**：本系統已針對 Cloudflare 優化 (讀取 `CF-Connecting-IP`)，建議透過 Tunnel 暴露至公網以獲得 HTTPS 保護。
* **安全性**：雖然已實作 Docker 隔離，但建議不要給予 Docker 容器 `privileged` 權限 (本程式預設已禁用網路與限制權限)。

## 📄 License

本專案採用 [MIT License](./LICENSE) 授權。