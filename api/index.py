from flask import Flask

# 從 routes 套件中匯入我們建立的藍圖
from .routes.backtest_route import backtest_bp
from .routes.scan_route import scan_bp

# 建立 Flask 應用實例
app = Flask(__name__)

# 註冊藍圖，並為所有路由加上 /api 的前綴
# 例如，/backtest 會變成 /api/backtest
app.register_blueprint(backtest_bp, url_prefix='/api')
app.register_blueprint(scan_bp, url_prefix='/api')

@app.route('/', methods=['GET'])
def index():
    """
    根路由，用於健康檢查。
    這個路由保持不變，因為它不屬於任何特定功能。
    """
    return "Python backend is running."
