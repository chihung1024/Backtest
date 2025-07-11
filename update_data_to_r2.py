# update_data_to_r2.py
# 職責：從網路抓取財經數據，並將其上傳到 Cloudflare R2。
# 這個腳本應該在本地或在 CI/CD 環境中執行。

import pandas as pd
import yfinance as yf
import json
import os
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from botocore.exceptions import ClientError

# --- 設定 ---
# 從環境變數讀取 R2 連線資訊
# 確保在執行前已設定好這些環境變數
ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = 'backtest-data' # 確保這個名稱與您在 Cloudflare 建立的儲存桶名稱一致

# R2 的 S3 相容 API 端點
R2_ENDPOINT_URL = f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com'

# 平行下載設定
MAX_WORKERS = 20

# --- R2 上傳函式 ---
def get_r2_client():
    """初始化並返回一個 boto3 S3 客戶端"""
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=ACCESS_KEY_ID,
            aws_secret_access_key=SECRET_ACCESS_KEY,
            region_name='auto'  # 對於 R2，固定為 'auto'
        )
        return s3_client
    except Exception as e:
        print(f"Error creating R2 client: {e}")
        return None

def upload_to_r2(s3_client, key, body, content_type='text/plain'):
    """上傳一個物件到 R2"""
    try:
        s3_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=body,
            ContentType=content_type
        )
        return True
    except ClientError as e:
        print(f"  -> 上傳 {key} 到 R2 失敗: {e}")
        return False

# --- 數據獲取函式 (與原版相同) ---
def get_etf_holdings(etf_ticker):
    try:
        etf = yf.Ticker(etf_ticker)
        holdings = etf.holdings
        if holdings is not None and not holdings.empty:
            return holdings['symbol'].tolist()
        return []
    except Exception:
        return []

def get_sp500_from_wiki():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        return tables[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception:
        return []

def get_nasdaq100_from_wiki():
    try:
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        tables = pd.read_html(url)
        return tables[4]['Ticker'].tolist()
    except Exception:
        return []
        
def fetch_stock_info(ticker):
    """獲取單支股票的詳細財務資訊"""
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        if info.get('trailingPE') is None and info.get('marketCap') is None:
            return None
        return {
            'ticker': ticker, 'marketCap': info.get('marketCap'), 'sector': info.get('sector'),
            'trailingPE': info.get('trailingPE'), 'forwardPE': info.get('forwardPE'),
            'dividendYield': info.get('dividendYield'), 'returnOnEquity': info.get('returnOnEquity'),
            'revenueGrowth': info.get('revenueGrowth'), 'earningsGrowth': info.get('earningsGrowth')
        }
    except Exception:
        return None

def fetch_price_history(ticker):
    """下載單支股票的歷史價格，並返回 CSV 字串"""
    try:
        data = yf.download(ticker, start="1990-01-01", auto_adjust=True, progress=False)
        if not data.empty:
            price_df = data[['Close']].copy()
            return ticker, price_df.to_csv()
        return ticker, None
    except Exception:
        return ticker, None

# --- 主執行函式 ---
def main():
    """主執行函式"""
    print("--- 檢查 R2 連線設定 ---")
    if not all([ACCOUNT_ID, ACCESS_KEY_ID, SECRET_ACCESS_KEY]):
        print("錯誤：環境變數 CLOUDFLARE_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY 未設定。")
        return
    
    s3_client = get_r2_client()
    if not s3_client:
        return

    print("--- 開始獲取指數成分股列表 ---")
    sp500_tickers = get_etf_holdings("VOO") or get_sp500_from_wiki()
    nasdaq100_tickers = get_etf_holdings("QQQ") or get_nasdaq100_from_wiki()
    
    sp500_set = set(sp500_tickers)
    nasdaq100_set = set(nasdaq100_tickers)
    all_unique_tickers = sorted(list(sp500_set.union(nasdaq100_set)))

    if not all_unique_tickers:
        print("錯誤：所有數據來源均無法獲取任何成分股，終止執行。")
        return
    print(f"總共找到 {len(all_unique_tickers)} 支不重複的股票。")

    # --- 平行處理基本面數據 ---
    print("\n--- 步驟 1/2: 平行下載基本面數據 ---")
    all_stock_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(fetch_stock_info, ticker): ticker for ticker in all_unique_tickers}
        for future in tqdm(as_completed(future_to_ticker), total=len(all_unique_tickers), desc="獲取基本面"):
            info = future.result()
            if info:
                info['in_sp500'] = info['ticker'] in sp500_set
                info['in_nasdaq100'] = info['ticker'] in nasdaq100_set
                all_stock_data.append(info)

    # 將基本面數據上傳到 R2
    preprocessed_json_str = json.dumps(all_stock_data, ensure_ascii=False, indent=2)
    if upload_to_r2(s3_client, 'preprocessed_data.json', preprocessed_json_str, 'application/json'):
        print(f"基本面數據處理完成，共 {len(all_stock_data)} 筆有效資料已上傳至 R2。")

    # --- 平行處理歷史價格 ---
    print("\n--- 步驟 2/2: 平行下載歷史價格數據並上傳 ---")
    success_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_csv = {executor.submit(fetch_price_history, ticker): ticker for ticker in all_unique_tickers}
        for future in tqdm(as_completed(future_to_csv), total=len(all_unique_tickers), desc="下載並上傳價格"):
            ticker, csv_content = future.result()
            if csv_content:
                if upload_to_r2(s3_client, f"prices/{ticker}.csv", csv_content, 'text/csv'):
                    success_count += 1
    
    print(f"歷史價格數據更新完成，共成功下載並上傳 {success_count} 支股票。")

if __name__ == '__main__':
    main()
