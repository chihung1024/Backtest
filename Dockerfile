# 步驟 1: 使用官方的 Python 3.9 slim 作為基礎映像檔
FROM python:3.9-slim

# 設定環境變數
ENV PYTHONUNBUFFERED True
ENV FLASK_APP=api.index:app
ENV FLASK_ENV=development

# 步驟 2: 在容器中建立一個工作目錄
WORKDIR /app

# 步驟 3: 複製依賴清單檔案到容器中
COPY requirements.txt requirements.txt

# 步驟 4: 安裝所有 Python 依賴套件
RUN pip install --no-cache-dir -r requirements.txt

# 步驟 5: 將您專案的所有檔案複製到容器的工作目錄中
COPY . .

# 步驟 6: 設定服務運行的 PORT
ENV PORT 8080

# 步驟 7: 定義容器啟動時要執行的指令
# (偵錯模式) 使用 Flask 內建的開發伺服器，它會提供最詳細的錯誤日誌
CMD exec flask run --host=0.0.0.0 --port=$PORT
