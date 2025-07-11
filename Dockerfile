# 步驟 1: 使用官方的 Python 3.9 slim 作為基礎映像檔
FROM python:3.9-slim

# 設定環境變數，確保 Python 輸出不會被緩存
ENV PYTHONUNBUFFERED True

# 步驟 2: 在容器中建立一個工作目錄
WORKDIR /app

# 步驟 3: 複製依賴清單檔案到容器中
COPY requirements.txt requirements.txt

# 步驟 4: 安裝所有 Python 依賴套件
# --no-cache-dir 選項可以減少映像檔的大小
RUN pip install --no-cache-dir -r requirements.txt

# 步驟 5: 將您專案的所有檔案複製到容器的工作目錄中
COPY . .

# 步驟 6: 設定服務運行的 PORT
# Cloud Run 會自動將外部請求導向這個 PORT
ENV PORT 8080

# 步驟 7: 定義容器啟動時要執行的指令
# 我們使用 gunicorn 作為正式環境的 WSGI 伺服器來運行您的 Flask 應用
# --workers 4: 啟動 4 個工作程序來處理請求
# --bind 0.0.0.0:$PORT: 監聽所有網路介面指定的 PORT
# api.index:app: 指向 api/index.py 檔案中的 app 物件
CMD exec gunicorn --workers 4 --bind 0.0.0.0:$PORT api.index:app
