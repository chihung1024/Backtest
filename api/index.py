from flask import Flask, send_from_directory
import os

# 從 routes 套件中匯入我們建立的藍圖
from .routes.backtest_route import backtest_bp
from .routes.scan_route import scan_bp

# --- 建立靜態檔案的絕對路徑 ---
# 取得目前檔案 (index.py) 所在的目錄
# 例如：/app/api/
current_dir = os.path.dirname(os.path.abspath(__file__))
# 取得專案根目錄 (api/ 的上一層)
# 例如：/app/
project_root = os.path.dirname(current_dir)
# 建立 public 資料夾的絕對路徑
# 例如：/app/public
public_folder_path = os.path.join(project_root, 'public')


# 建立 Flask 應用實例
# 並使用絕對路徑來設定靜態檔案的路徑
app = Flask(__name__, static_folder=public_folder_path, static_url_path='')

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
