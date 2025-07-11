import os
import pandas as pd
from pandas.tseries.offsets import BDay
from cachetools import cached, TTLCache
import json
import requests # 改用 requests 來獲取 JSON，更穩健

# --- 快取設定 ---
cache = TTLCache(maxsize=256, ttl=1800) # 快取 30 分鐘

@cached(cache)
def read_price_data_from_repo(tickers: tuple, start_date_str: str, end_date_str: str) -> pd.DataFrame:
    """
    從遠端 GitHub data 分支的 raw URL 讀取 CSV 檔案。
    """
    # 使用 Render 的環境變數，並更新後備值為您最新的專案名稱
    owner = os.environ.get('RENDER_GIT_REPO_OWNER', 'chihung1024') 
    repo = os.environ.get('RENDER_GIT_REPO_SLUG', 'Backtest') # <-- 確認後備值為 'Backtest'
    
    base_url = f"https://raw.githubusercontent.com/{owner}/{repo}/data/prices"
    
    all_prices = []
    print(f"--- 開始從 {base_url} 讀取價格數據 ---") # 新增日誌
    for ticker in tickers:
        file_url = f"{base_url}/{ticker}.csv"
        try:
            df = pd.read_csv(file_url, index_col='Date', parse_dates=True)
            df.rename(columns={'Close': ticker}, inplace=True)
            all_prices.append(df)
        except Exception as e:
            # (新增) 印出更詳細的錯誤日誌，告訴我們是哪個 URL 失敗了
            print(f"警告：無法從 URL [{file_url}] 讀取股票 {ticker} 的價格檔案: {e}")

    if not all_prices:
        print("--- 警告：未能讀取到任何價格數據 ---") # 新增日誌
        return pd.DataFrame()

    print(f"--- 成功讀取 {len(all_prices)} 支股票的價格數據 ---") # 新增日誌
    combined_df = pd.concat(all_prices, axis=1)
    mask = (combined_df.index >= start_date_str) & (combined_df.index <= end_date_str)
    return combined_df.loc[mask]


@cached(cache)
def get_preprocessed_data():
    """
    從遠端 GitHub data 分支的 raw URL 讀取預處理好的 JSON 數據。
    """
    # 使用 Render 的環境變數，並更新後備值為您最新的專案名稱
    owner = os.environ.get('RENDER_GIT_REPO_OWNER', 'chihung1024') 
    repo = os.environ.get('RENDER_GIT_REPO_SLUG', 'Backtest') # <-- 確認後備值為 'Backtest'
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/data/preprocessed_data.json"
    
    print(f"--- 正在從 URL [{url}] 讀取預處理數據 ---") # 新增日誌
    try:
        response = requests.get(url)
        response.raise_for_status()  # 如果請求失敗 (如 404)，會在此拋出錯誤
        return response.json()
    except Exception as e:
        # (新增) 印出詳細的錯誤日誌
        print(f"致命錯誤：無法從 URL [{url}] 讀取 preprocessed_data.json: {e}")
        return []


def validate_data_completeness(df_prices_raw, all_tickers, requested_start_date):
    """
    檢查是否有任何股票的數據起始日顯著晚於請求的起始日。
    """
    problematic_tickers = []
    for ticker in all_tickers:
        if ticker in df_prices_raw.columns:
            first_valid_date = df_prices_raw[ticker].first_valid_index()
            if first_valid_date is not None and first_valid_date > requested_start_date + BDay(5):
                problematic_tickers.append({'ticker': ticker, 'start_date': first_valid_date.strftime('%Y-%m-%d')})
    return problematic_tickers
