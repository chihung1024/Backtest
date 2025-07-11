from flask import Flask, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/')
def home():
    """
    根路徑，提供歡迎訊息。
    """
    return "歡迎來到 Backtest 服務！請使用 /run_backtest 來啟動回測。"

@app.route('/run_backtest')
def run_backtest():
    """
    觸發 main.py 腳本的回測功能。
    注意：在網頁應用程式中執行長時間運行的子進程可能不是最佳實踐，
    特別是在免費層級的服務中，因為可能會遇到請求超時或資源限制。
    對於實際應用，建議將 main.py 的核心邏輯重構為可調用的函數，
    或考慮使用 Render 的「背景工作」服務來執行長時間任務。
    """
    try:
        # 確保當前工作目錄是專案根目錄，以便 main.py 能找到其依賴檔案
        # 這假設 main.py 位於專案根目錄
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 執行 main.py 腳本
        # capture_output=True 會捕獲標準輸出和標準錯誤
        # text=True 會將輸出解碼為文字
        # check=True 會在命令返回非零退出碼時引發 CalledProcessError
        process = subprocess.run(
            ['python', os.path.join(current_dir, 'main.py')],
            capture_output=True,
            text=True,
            check=True
        )
        
        return jsonify({
            "status": "成功",
            "輸出": process.stdout,
            "錯誤": process.stderr
        })
    except subprocess.CalledProcessError as e:
        # 處理腳本執行失敗的情況
        return jsonify({
            "status": "錯誤",
            "訊息": "回測腳本執行失敗。",
            "標準輸出": e.stdout,
            "標準錯誤": e.stderr,
            "返回碼": e.returncode
        }), 500
    except Exception as e:
        # 處理其他意外錯誤
        return jsonify({
            "status": "錯誤",
            "訊息": str(e)
        }), 500

if __name__ == '__main__':
    # 當在 Render 上部署時，Gunicorn 會負責運行應用程式。
    # 這段代碼主要用於本地測試。
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
