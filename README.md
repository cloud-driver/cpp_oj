# Justus OJ (Justus Code Arena)

這是一個基於 Python Flask 框架開發的輕量級 C++ Online Judge (線上解題系統)。提供題目瀏覽、程式碼提交、即時編譯與評測功能，並包含一個簡易的後台管理介面供管理員新增與編輯題目。

## ✨ 特色功能 (Features)

* **使用者端**
* **題目列表與展示**：清楚的題目列表與詳細的題目敘述（支援圖片顯示）。
* **程式碼提交**：支援直接貼上程式碼或上傳 `.cpp` / `.txt` 檔案。
* **即時評測**：
* 編譯錯誤 (CE)
* 答案正確 (AC)
* 答案錯誤 (WA)
* 執行錯誤 (RE)
* 執行逾時 (TLE - 設定為 2 秒)
* 安全性檢查 (Dangerous - 阻擋 `system`, `rm -rf` 等危險指令)


* **頻率限制**：防止惡意洗版，同一 IP 需等待 15 秒才能再次提交。
* **範例測試**：題目頁面展示 Sample Input/Output 供使用者參考。


* **管理員後台**
* **題目管理**：新增、編輯、刪除題目。
* **測資管理**：設定公開的「範例 (Samples)」與隱藏的「評測測資 (Test Cases)」。
* **圖片上傳**：支援為題目上傳說明圖片。
* **簡易驗證**：透過固定密碼登入後台。



## 🛠️ 技術堆疊 (Tech Stack)

* **後端**：Python, Flask
* **資料庫**：SQLite (`cpp_oj.db`)
* **前端**：HTML, Bootstrap 5 (RWD 響應式設計)
* **編譯環境**：G++ (需運行於 Linux 環境或支援 G++ 路徑的系統)

## 🚀 安裝與執行 (Installation & Setup)

### 1. 環境需求

由於系統使用 `subprocess` 呼叫 `/usr/bin/g++` 進行編譯，建議於 **Linux** 環境下執行 (如 Ubuntu)。

* Python 3.x
* G++ Compiler (`sudo apt install g++`)

### 2. 安裝依賴

請確保已安裝 Flask：

```bash
pip install flask
```

### 3. 專案結構

```text
/
├── app.py              # 主程式邏輯
├── cpp_oj.db           # 資料庫 (自動生成)
├── static/
│   └── uploads/        # 題目圖片存放區
├── temp_code/          # 暫存編譯檔案 (自動生成)
├── templates/          # HTML 模板 (home, admin, edit, login...)
└── README.md

```

### 4. 啟動伺服器

執行以下指令啟動 Web Server：

```bash
python app.py
```

預設將運行於 `http://0.0.0.0:8080`。

## ⚙️ 設定 (Configuration)

您可以在 `app.py` 中修改以下重要設定：

* **管理員密碼**：
**請務必修改**以下變數以確保安全：
```python
ADMIN_PASSWORD = '您的新密碼'
```


* **Secret Key**：
用於 Session 加密，建議修改：
```python
app.secret_key = '隨機生成的複雜字串'
```


* **頻率限制**：
調整 `RATE_LIMIT_SECONDS` 可改變提交冷卻時間 (預設 15 秒)。

## 📝 使用說明

1. **首頁**：進入 `http://localhost:8080/` 瀏覽題目。
2. **後台管理**：
* 點擊導覽列的「後台管理」或前往 `/admin`。
* 輸入密碼登入。
* 在後台可以填寫題目敘述、設定 Input/Output 測資。


3. **解題**：
* 選擇題目，閱讀說明。
* 在文字框輸入 C++ 程式碼 (需包含 `main` 函式)。
* 點擊「送出並執行」，系統會自動編譯並對照隱藏測資。



## ⚠️ 安全注意事項

本系統包含基本的關鍵字過濾 (`is_safe_code`) 以防止簡單的惡意攻擊 (如 `system(`)，但**不建議**直接部署於公開且高風險的伺服器上，因為未實作完整的沙箱 (Sandbox) 隔離機制。僅適合教學或內部練習使用。

## 📄 License

本專案採用 [MIT License](./LICENSE) 授權。