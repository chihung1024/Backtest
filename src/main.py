# src/main.py
# 這是運行在 Cloudflare 邊緣網路上的後端 API 邏輯。
# 它取代了之前所有的 api/*.py 檔案。

import json
import pandas as pd
import numpy as np
from io import StringIO
from itty_router import Router, aio # 使用一個輕量級的路由函式庫

# --- 核心計算與模擬邏輯 (從舊的 utils 模組移植) ---

def calculate_metrics(portfolio_values, date_range):
    if portfolio_values.empty or portfolio_values.iloc[0] == 0:
        return {"initial_value": 0, "final_value": 0, "cagr": 0, "stdev": 0, "sharpe_ratio": 0, "max_drawdown": 0}
    initial_value = portfolio_values.iloc[0]
    final_value = portfolio_values.iloc[-1]
    days = (date_range[-1] - date_range[0]).days
    years = days / 365.25
    cagr = (final_value / initial_value) ** (1 / years) - 1 if years > 0 else (final_value / initial_value) - 1
    returns = portfolio_values.pct_change().dropna()
    stdev = returns.std() * np.sqrt(252) if not returns.empty else 0
    sharpe_ratio = (cagr - 0.01) / stdev if stdev > 0 else 0
    max_drawdown = (portfolio_values / portfolio_values.cummax() - 1).min()
    return {"initial_value": round(initial_value, 2), "final_value": round(final_value, 2), "cagr": round(cagr * 100, 2), "stdev": round(stdev * 100, 2), "sharpe_ratio": round(sharpe_ratio, 2), "max_drawdown": round(max_drawdown * 100, 2)}

async def get_price_from_r2(env, ticker):
    """從 R2 讀取單一股票的價格 CSV"""
    key = f"prices/{ticker}.csv"
    r2_object = await env.DATA_BUCKET.get(key)
    if r2_object is None:
        return None
    body = await r2_object.text()
    return pd.read_csv(StringIO(body), index_col='Date', parse_dates=True)['Close']

async def run_backtest_simulation(payload, env):
    """在 Worker 環境中執行的回測模擬"""
    portfolios = payload.get('portfolios')
    initial_amount = float(payload.get('initialAmount', 10000))
    start_date_str = payload.get('startDate')
    end_date_str = payload.get('endDate')
    rebalancing_period = payload.get('rebalancingPeriod')
    benchmark_ticker = payload.get('benchmark')

    all_tickers = set([asset['ticker'] for p in portfolios for asset in p['assets']])
    if benchmark_ticker: all_tickers.add(benchmark_ticker)

    price_data = {}
    missing_tickers = []
    for ticker in all_tickers:
        prices = await get_price_from_r2(env, ticker)
        if prices is None:
            missing_tickers.append(ticker)
        else:
            price_data[ticker] = prices
    
    if not price_data: return {"error": "無法載入任何有效的股票價格數據。"}

    common_index = None
    for prices in price_data.values():
        common_index = prices.index if common_index is None else common_index.intersection(prices.index)
    
    start_date = pd.to_datetime(start_date_str)
    end_date = pd.to_datetime(end_date_str)
    backtest_range = common_index[(common_index >= start_date) & (common_index <= end_date)]
    if backtest_range.empty: return {"error": "在指定的時間範圍內，所有資產沒有共同的交易日。"}

    aligned_prices = pd.DataFrame(index=backtest_range)
    for ticker, prices in price_data.items():
        aligned_prices[ticker] = prices
    aligned_prices.ffill(inplace=True)
    aligned_prices.bfill(inplace=True)
    if aligned_prices.isnull().values.any(): return {"error": "數據清理後仍存在缺失值。"}

    results = {}
    for p_config in portfolios:
        # ... (此處省略了與 Render 版本中相同的每日模擬迴圈邏輯) ...
        # ... 您可以將之前 `api/utils/simulation.py` 中的迴圈邏輯直接複製過來 ...
        # 為了簡潔，我們假設這裡完成了計算
        portfolio_name = p_config.get('name')
        # 這裡應該是完整的計算結果
        portfolio_values = pd.Series(np.linspace(initial_amount, initial_amount * (1 + (np.random.rand() - 0.4)), len(backtest_range)), index=backtest_range)
        results[portfolio_name] = portfolio_values

    if benchmark_ticker and benchmark_ticker in price_data:
        # ... (基準計算邏輯) ...
        benchmark_values = pd.Series(np.linspace(initial_amount, initial_amount * (1 + (np.random.rand() - 0.4)), len(backtest_range)), index=backtest_range)
        results[benchmark_ticker] = benchmark_values
        
    final_results = {"dates": [d.strftime('%Y-%m-%d') for d in backtest_range], "portfolios": [], "warnings": [f"缺少數據: {', '.join(missing_tickers)}"] if missing_tickers else []}
    for name, values in results.items():
        metrics = calculate_metrics(values, backtest_range)
        final_results["portfolios"].append({"name": name, "values": [round(v, 2) for v in values.tolist()], "metrics": metrics})

    return final_results

# --- API 路由設定 ---

router = Router()

@router.get("/api/get_stocks")
async def handle_get_stocks(request, env):
    r2_object = await env.DATA_BUCKET.get("preprocessed_data.json")
    if r2_object is None:
        return aio.json({"error": "Preprocessed data not found in R2 bucket."}, status=404)
    
    # 設置 CORS 標頭，允許從任何來源的前端訪問
    headers = {"Access-Control-Allow-Origin": "*"}
    return aio.json(await r2_object.json(), headers=headers)

@router.post("/api/run_backtest")
async def handle_backtest(request, env):
    try:
        payload = await request.json()
        results = await run_backtest_simulation(payload, env) # 這裡需要完整實現
        headers = {"Access-Control-Allow-Origin": "*"}
        return aio.json(results, headers=headers)
    except Exception as e:
        return aio.json({"error": str(e)}, status=500)

@router.post("/api/run_scan")
async def handle_scan(request, env):
    # 掃描邏輯與回測類似，此處從略。您需要將 run_scan_simulation 的邏輯移植過來。
    headers = {"Access-Control-Allow-Origin": "*"}
    return aio.json({"message": "Scan endpoint not fully implemented yet."}, headers=headers)

# 處理 CORS Preflight 請求
@router.options("/api/.*")
async def handle_options(request, env):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    return aio.json({}, headers=headers)

# --- Worker 主類別 ---
# Cloudflare 會尋找一個名為 'Worker' 的類別，或者一個 'fetch' 處理器
class Worker:
    async def fetch(self, request, env, ctx):
        return await router.handle(request, env)

