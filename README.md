# Justus OJ — Justus Code Arena

Justus OJ 是一個以 **Python Flask + Docker** 建置的輕量級 C++ Online Judge 線上解題系統。

本系統提供題目管理、C++ 程式碼編譯與評測、範例測資測試、AI 解題提示、使用者登入註冊、解題統計、後台管理，以及獨立 C++ 編輯器。所有 C++ 程式碼皆透過 Docker 沙箱執行，降低伺服器被惡意程式碼影響的風險。

---

## 專案特色

* C++ 線上解題與自動評測
* Docker 沙箱隔離執行環境
* 支援 AC / WA / CE / RE / TLE 等評測狀態
* 支援範例測資即時測試
* 支援上傳 `.cpp` / `.txt` 程式碼
* 支援 CodeMirror 程式碼編輯器
* 支援 C++ 關鍵字提示與自動補全
* 支援 AI 解題思路提示
* 支援使用者登入、註冊、登出
* 支援未登入提交時暫存程式碼，登入後自動還原
* 支援使用者解題統計：已解題數、正確率、排名
* 支援管理員後台新增、編輯、刪除題目
* 支援題目圖片上傳
* 支援範例測資與隱藏測資管理
* 支援題庫 JSON 匯出與匯入
* 支援獨立 C++ 編輯器頁面
* 支援自訂 stdin 執行程式
* 支援下載目前程式碼為 `.cpp` 檔案
* 支援 Cloudflare 真實 IP 解析
* 支援 CSRF 保護
* 支援系統事件 Log 紀錄

---

## 系統功能總覽

### 1. 使用者系統

使用者可以註冊、登入與登出。登入後可以正式提交題目，系統會記錄提交結果與程式碼。

功能包含：

* 使用者註冊
* 使用者登入
* 使用者登出
* 密碼雜湊儲存
* Session 登入狀態管理
* 管理員角色判斷
* 登入後顯示使用者名稱
* 管理員登入後可進入後台

預設管理員帳號會在資料庫初始化時自動建立，可透過環境變數設定。

---

### 2. 首頁與題目列表

首頁提供卡片式題目列表，讓使用者快速選擇題目進入解題頁。

功能包含：

* Hero Banner
* 題目卡片列表
* 題目 ID、標題、敘述摘要
* 題目圖片顯示
* 已解題題目顯示綠色勾勾
* 使用者登入後顯示：

  * 已解決題數
  * 提交正確率
  * 排名
* 快速進入 C++ 編輯器
* 登入、註冊、登出、後台管理入口
* Footer 技術資訊與聯絡資訊

---

### 3. 解題頁面

每一題都有獨立的解題頁面，使用者可以閱讀題目、查看範例測資、撰寫程式碼、測試範例、送出正式評測。

功能包含：

* 題目切換下拉選單
* 題目敘述顯示
* 題目圖片顯示
* 範例輸入 / 範例輸出顯示
* CodeMirror C++ 編輯器
* C++ 語法模式
* Dracula 編輯器主題
* 行號顯示
* 括號自動補全
* C++ 關鍵字自動提示
* `Ctrl + Space` 手動觸發 autocomplete
* 支援貼上程式碼
* 支援上傳 `.cpp` / `.txt` 檔案
* 支援範例測資測試
* 支援正式送出評測
* 顯示評測結果
* 自動捲動到執行結果區

---

### 4. C++ 程式碼評測

系統會將使用者提交的程式碼寫入暫存檔，再使用 Docker 進行編譯與執行。

評測流程：

1. 建立唯一暫存檔名
2. 將 C++ 程式碼寫入 `temp_code/`
3. 使用 Docker 中的 `gcc:latest` 執行 `g++`
4. 若編譯失敗，回傳 CE
5. 若編譯成功，逐筆執行隱藏測資
6. 比對使用者輸出與標準輸出
7. 全部通過則回傳 AC
8. 任一測資錯誤則回傳 WA
9. 執行錯誤則回傳 RE
10. 執行逾時則回傳 TLE
11. 最後清理暫存檔

支援狀態：

| 狀態  | 說明                              |
| --- | ------------------------------- |
| AC  | Accepted，所有測資通過                 |
| WA  | Wrong Answer，答案錯誤               |
| CE  | Compilation Error，編譯錯誤          |
| RE  | Runtime Error，執行錯誤              |
| TLE | Time Limit Exceeded，執行逾時        |
| MLE | Memory Limit Exceeded，記憶體限制相關錯誤 |

---

### 5. 範例測資測試

在正式提交前，使用者可以先執行題目公開的 Sample Test。

功能包含：

* 不寫入正式提交紀錄
* 只執行題目範例測資
* 顯示每筆 Sample 的：

  * Input
  * Expected Output
  * Actual Output
  * Pass / Fail
* 編譯錯誤時直接顯示錯誤訊息
* 使用 AJAX 與後端 `/run_samples/<problem_id>` 溝通

這個功能適合讓使用者先確認基本輸入輸出是否正確，再送出正式評測。

---

### 6. AI 解題思路提示

系統提供 AI 解題提示功能，讓登入使用者可以針對目前題目與程式碼取得解題方向。

功能包含：

* 登入後才能使用
* 針對題目敘述產生提示
* 會參考使用者目前的程式碼
* 回覆解題思路、演算法方向、資料結構、邊界條件
* 要求 AI 不直接給完整程式碼答案
* 支援 Markdown 顯示
* 支援 MathJax 公式渲染
* AI 請求頻率限制，預設冷卻時間 30 秒
* 使用 `OLLAMA_API_URL` 設定 AI API 位址
* 預設模型名稱為 `gemini-3-flash-preview`

---

### 7. 獨立 C++ 編輯器

系統提供 `/editor` 頁面，這是一個不綁題目、不送出正式評測的 C++ 練習編輯器。

適合用途：

* 臨時寫 C++ 程式
* 測試 stdin / stdout
* 練習語法
* 下載目前程式碼為 `.cpp`
* 不想綁定題目時快速測試

功能包含：

* CodeMirror C++ 編輯器
* 行號顯示
* Dracula 主題
* 自動補括號
* C++ 關鍵字提示
* `Ctrl + Space` 自動補全
* 自訂檔名
* 下載 `.cpp` 檔案
* stdin 輸入欄位
* stdout / 錯誤訊息輸出欄位
* 執行狀態 Badge
* 清空輸出
* 使用 `/run_custom` 執行自訂程式
* 不寫入 submissions 正式提交紀錄
* 仍使用 Docker 沙箱執行
* 仍套用基本防刷頻率限制

---

### 8. 管理員後台

管理員登入後可以進入 `/admin` 管理題庫。

功能包含：

* 新增題目
* 編輯題目
* 刪除題目
* 上傳題目圖片
* 管理公開範例測資 Samples
* 管理隱藏測資 Test Cases
* 題目列表檢視
* 顯示題目是否有圖片
* 題庫 JSON 匯出
* 題庫 JSON 匯入
* 管理操作 Log 紀錄

題目資料包含：

* 題目標題
* 題目敘述
* 題目圖片
* 範例輸入
* 範例輸出
* 隱藏測資輸入
* 隱藏測資輸出

---

### 9. 題庫備份與還原

管理員可以透過後台匯出與匯入題目資料。

功能包含：

* `/admin/export`
* 匯出 `problems_backup.json`
* 匯出題目文字資料
* 匯出 Samples
* 匯出 Test Cases
* `/admin/import`
* 上傳 JSON 還原題目
* 匯入時會新增到現有題庫，不會覆蓋原本題目

注意：

題目圖片檔案不會包含在 JSON 備份中。若題目包含圖片，請另外備份：

```text
static/uploads/
```

---

### 10. 安全設計

本系統透過 Docker 執行使用者程式碼，並加入多層安全限制。

Docker 執行限制包含：

* 使用獨立 Docker container 執行
* 執行後自動刪除 container
* 禁用網路連線
* 限制記憶體
* 限制 CPU
* 限制 process 數量
* 限制 nproc
* 關閉額外 Linux capabilities
* 啟用 `no-new-privileges`
* 使用非 root UID / GID 執行
* 執行環境設為 read-only
* 使用唯一檔名避免衝突
* 執行完清除暫存檔

預設限制：

| 項目           | 設定           |
| ------------ | ------------ |
| 編譯記憶體        | 256MB        |
| 執行記憶體        | 128MB        |
| 執行逾時         | 2 秒          |
| Process 限制   | 30           |
| nproc 限制     | 20           |
| Docker Image | `gcc:latest` |
| 網路           | disabled     |
| 權限           | cap_drop ALL |

---

### 11. 防刷與頻率限制

系統針對使用者 IP 進行頻率限制，避免惡意連續提交或大量呼叫 AI。

目前包含：

* 正式提交冷卻時間
* 範例 / 編輯器執行冷卻限制
* AI 提示冷卻時間
* 透過 SQLite 紀錄 IP 最後操作時間
* 支援 Cloudflare 真實 IP 解析

預設：

```python
RATE_LIMIT_SECONDS = 15
AI_RATE_LIMIT_SECONDS = 30
```

---

### 12. Cloudflare 與反向代理支援

系統支援 Cloudflare Tunnel / Proxy 情境。

功能包含：

* 讀取 `CF-Connecting-IP`
* 取得真實使用者 IP
* 使用 `ProxyFix`
* 支援 HTTPS 反向代理部署
* Session Cookie 設定：

  * `SESSION_COOKIE_SECURE = True`
  * `SESSION_COOKIE_HTTPONLY = True`
  * `SESSION_COOKIE_SAMESITE = 'Lax'`

---

### 13. CSRF 保護

本系統使用 `Flask-WTF` 的 `CSRFProtect` 進行 CSRF 防護。

涵蓋範圍包含：

* 登入表單
* 註冊表單
* 題目提交表單
* 後台新增題目
* 後台匯入題庫
* AJAX 請求中的 `X-CSRFToken`

若部署網域不同，請確認 `CSRF_TRUSTED_ORIGINS` 設定是否正確。

---

### 14. Log 系統

系統會將重要事件記錄到：

```text
oj_events.log
```

紀錄格式：

```text
<IP> : <時間> : <事件>
```

紀錄事件包含：

* 新使用者註冊
* 使用者登入
* 題目提交結果
* AI 請求
* 編輯器執行結果
* 管理員新增題目
* 管理員編輯題目
* 管理員刪除題目
* 題庫匯出
* 題庫匯入

---

### 15. 404 頁面

當使用者訪問不存在的題目或錯誤路由時，系統會顯示友善 404 頁面。

功能包含：

* 顯示錯誤訊息
* 倒數自動回首頁
* 提供立即返回首頁按鈕

---

## 技術架構

### 後端

* Python 3
* Flask
* SQLite
* Docker SDK for Python
* Flask-WTF
* Werkzeug
* python-dotenv
* requests

### 前端

* HTML5
* CSS3
* Bootstrap 5
* JavaScript
* CodeMirror
* Marked.js
* MathJax

### 執行環境

* Docker Engine
* GCC Docker Image：`gcc:latest`
* Linux Server / VPS
* 可搭配 Nginx、Cloudflare Tunnel、systemd 部署

---

## 專案結構

```text
cpp_oj/
├── app.py
├── README.md
├── LICENSE
├── cpp_oj.db                 # SQLite 資料庫，首次執行後自動產生
├── oj_events.log             # 系統事件紀錄，執行後自動產生
├── temp_code/                # 暫存 C++ 原始碼、輸入檔、執行檔
├── static/
│   ├── favicon.ico
│   └── uploads/              # 題目圖片存放位置
└── templates/
    ├── home.html             # 首頁與題目列表
    ├── index.html            # 解題頁面
    ├── editor.html           # 獨立 C++ 編輯器
    ├── admin.html            # 管理員後台
    ├── edit.html             # 題目編輯頁
    ├── login.html            # 登入頁
    ├── register.html         # 註冊頁
    └── 404.html              # 404 頁面
```

---

## 主要路由

| 路由                          | 方法         | 功能         |
| --------------------------- | ---------- | ---------- |
| `/`                         | GET        | 首頁與題目列表    |
| `/register`                 | GET / POST | 使用者註冊      |
| `/login`                    | GET / POST | 使用者登入      |
| `/logout`                   | GET        | 使用者登出      |
| `/problem/<problem_id>`     | GET / POST | 題目頁與正式提交   |
| `/run_samples/<problem_id>` | POST       | 執行公開範例測資   |
| `/get_hint/<problem_id>`    | POST       | AI 解題提示    |
| `/editor`                   | GET        | 獨立 C++ 編輯器 |
| `/run_custom`               | POST       | 執行編輯器自訂程式  |
| `/admin`                    | GET / POST | 管理員後台與新增題目 |
| `/admin/export`             | GET        | 匯出題庫 JSON  |
| `/admin/import`             | POST       | 匯入題庫 JSON  |
| `/edit/<problem_id>`        | GET / POST | 編輯題目       |
| `/delete/<problem_id>`      | GET        | 刪除題目       |
| `/favicon.ico`              | GET        | 網站圖示       |

---

## 安裝方式

本系統建議部署於 Linux 環境，例如 Ubuntu / Debian。

### 1. 安裝 Docker

```bash
sudo apt update
sudo apt install docker.io -y
sudo systemctl start docker
sudo systemctl enable docker
```

將目前使用者加入 Docker 群組：

```bash
sudo usermod -aG docker $USER
```

執行後請重新登入，讓群組設定生效。

---

### 2. 下載 GCC Docker Image

```bash
docker pull gcc:latest
```

---

### 3. Clone 專案

```bash
git clone https://github.com/cloud-driver/cpp_oj.git
cd cpp_oj
```

---

### 4. 建立虛擬環境

```bash
python3 -m venv venv
source venv/bin/activate
```

---

### 5. 安裝 Python 套件

```bash
pip install flask flask-wtf werkzeug python-dotenv requests docker
```

---

### 6. 建立 `.env`

建議建立 `.env` 管理敏感設定：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_admin_password
FLASK_SECRET_KEY=your_random_secret_key
OLLAMA_API_URL=http://localhost:11434/api/generate
```

請務必修改：

* `ADMIN_PASSWORD`
* `FLASK_SECRET_KEY`

不要在正式環境使用預設密碼與預設 Secret Key。

---

### 7. 啟動服務

```bash
python3 app.py
```

預設啟動於：

```text
http://0.0.0.0:8080
```

第一次啟動時，系統會自動建立：

* SQLite 資料庫
* 題目表
* 使用者表
* 提交紀錄表
* Log 表
* 預設管理員帳號
* 暫存資料夾
* 圖片上傳資料夾

---

## 使用方式

### 一般使用者

1. 進入首頁
2. 註冊帳號
3. 登入
4. 選擇題目
5. 閱讀題目敘述與範例測資
6. 撰寫 C++ 程式碼
7. 可先按「測試範例」
8. 確認基本輸出正確後按「送出評測」
9. 查看 AC / WA / CE / RE / TLE 結果

---

### 使用 C++ 編輯器

1. 點選首頁或導覽列的「C++ 編輯器」
2. 在左側編輯 C++ 程式碼
3. 在 stdin 欄位輸入測試資料
4. 按下「執行程式」
5. 在 stdout 欄位查看輸出或錯誤訊息
6. 可輸入檔名並下載 `.cpp`

此功能不綁定任何題目，也不會寫入正式提交紀錄。

---

### 管理員

1. 使用管理員帳號登入
2. 點選「後台管理」
3. 新增題目
4. 填寫題目名稱與敘述
5. 可選擇上傳題目圖片
6. 新增 Samples
7. 新增 Hidden Test Cases
8. 儲存題目
9. 可編輯、刪除既有題目
10. 可匯出 / 匯入題庫 JSON

---

## 環境變數

| 變數名稱               | 說明                       | 預設值                                   |
| ------------------ | ------------------------ | ------------------------------------- |
| `ADMIN_USERNAME`   | 管理員帳號                    | `admin`                               |
| `ADMIN_PASSWORD`   | 管理員密碼                    | `admin`                               |
| `FLASK_SECRET_KEY` | Flask Session Secret Key | `default-unsafe-key`                  |
| `OLLAMA_API_URL`   | AI API 位址                | `http://localhost:11434/api/generate` |

---

## 重要系統設定

可在 `app.py` 中調整：

```python
RATE_LIMIT_SECONDS = 15
AI_RATE_LIMIT_SECONDS = 30
AI_MODEL = "gemini-3-flash-preview"
DOCKER_IMAGE = "gcc:latest"
OJ_RUNNER_UID = "999"
OJ_RUNNER_GID = "986"
```

若伺服器不存在 UID `999` 或 GID `986`，請依照實際環境調整。

---

## 部署建議

正式部署時建議使用：

* Gunicorn
* Nginx
* systemd
* Cloudflare Tunnel / HTTPS
* `.env` 管理環境變數
* 定期備份 `cpp_oj.db`
* 定期備份 `static/uploads/`

---

### systemd 範例

可建立：

```bash
sudo nano /etc/systemd/system/justus-oj.service
```

範例內容：

```ini
[Unit]
Description=Justus OJ Flask Service
After=network.target docker.service
Requires=docker.service

[Service]
User=YOUR_USER
WorkingDirectory=/path/to/cpp_oj
Environment="PATH=/path/to/cpp_oj/venv/bin"
ExecStart=/path/to/cpp_oj/venv/bin/python /path/to/cpp_oj/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

啟用服務：

```bash
sudo systemctl daemon-reload
sudo systemctl enable justus-oj
sudo systemctl start justus-oj
```

查看狀態：

```bash
sudo systemctl status justus-oj
```

重啟服務：

```bash
sudo systemctl restart justus-oj
```

---

## 備份建議

建議定期備份：

```text
cpp_oj.db
static/uploads/
.env
```

若只需要備份題目文字與測資，可使用後台的 JSON 匯出功能。

---

## 安全注意事項

本系統雖然使用 Docker 沙箱限制使用者程式碼，但仍不建議直接以高權限裸露在公開網路。

建議：

* 不要使用 root 身分執行 Flask 服務
* 不要讓 Docker container 使用 privileged mode
* 不要移除 network disabled
* 不要移除 CPU / memory / process 限制
* 正式環境務必修改管理員密碼
* 正式環境務必修改 `FLASK_SECRET_KEY`
* 建議放在 Nginx 或 Cloudflare Tunnel 後方
* 定期檢查 `oj_events.log`
* 定期備份資料庫與圖片

---

## 目前限制

* 目前主要支援 C++
* 題庫圖片不會包含在 JSON 匯出中
* AI 提示需要另外準備可用的 AI API
* Docker 需要在伺服器上正確安裝並啟動
* Windows 原生環境部署較不建議，推薦 Linux VPS
* 評測目前以標準輸入輸出比對為主
* 尚未提供完整的排行榜頁面，首頁僅顯示登入使用者目前排名

---

## License

本專案採用 [MIT License](./LICENSE) 授權。
