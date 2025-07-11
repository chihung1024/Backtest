# 步驟 1: 使用官方的 Python 3.9 slim 作為基礎映像檔
FROM python:3.9-slim

# 設定環境變數，確保 Python 輸出不會被緩存
ENV PYTHONUNBUFFERED True

# 步驟 2: 在容器中建立一個工作目錄
WORKDIR /app

# 步驟 3: 複製依賴清單檔案到容器中
COPY requirements.txt requirements.txt

# 步驟 4: 安裝所有 Python 依賴套件
RUN pip install --no-cache-dir -r requirements.txt

# 步驟 5: 將您專案的所有檔案複製到容器的工作目錄中
COPY . .

# 步驟 6: 設定服務運行的 PORT
# Cloud Run 會自動將外部請求導向這個 PORT
ENV PORT 8080

# 步驟 7: 定義容器啟動時要執行的指令
# (已修改) 移除 --workers 參數，讓 Cloud Run 自動管理
# 這是在 Cloud Run 環境下的最佳實踐
CMD exec gunicorn --bind 0.0.0.0:$PORT api.index:app
