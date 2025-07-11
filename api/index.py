from flask import Flask, send_from_directory
import os

# 從 routes 套件中匯入我們建立的藍圖
from .routes.backtest_route import backtest_bp
from .routes.scan_route import scan_bp

# 建立 Flask 應用實例
# 並設定靜態檔案的路徑指向 'public' 資料夾
app = Flask(__name__, static_folder='../public', static_url_path='')

# 註冊藍圖，並為所有路由加上 /api 的前綴
app.register_blueprint(backtest_bp, url_prefix='/api')
app.register_blueprint(scan_bp, url_prefix='/api')

# 新增一個根路由，用來提供前端的主頁面
@app.route('/', methods=['GET'])
def serve_index():
    # 從 public 資料夾中回傳 backtest.html
    return send_from_directory(app.static_folder, 'backtest.html')

# Flask 會自動處理 static_url_path 下的靜態檔案請求
# 例如 /js/main.js 的請求會自動對應到 public/js/main.js
