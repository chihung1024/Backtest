# src/main.py
# v3: 使用 Hono 框架重構路由和回應處理，以獲得更好的相容性和功能。

import json
import pandas as pd
import numpy as np
from io import StringIO
from hono import Hono              # 導入 Hono 框架
from hono.js_compatibility import Response # Hono 提供了與 JS Response 相容的物件
from hono.middleware import cors   # Hono 內建了強大的 CORS 中介軟體

# --- 核心計算與模擬邏輯 (此部分保持不變) ---

def calculate_metrics(portfolio_values, date_range):
    if portfolio_values.empty or portfolio_values.iloc[0] == 0:
        return {"initial_value": 0, "final_value": 0, "cagr": 0, "stdev": 0, "sharpe_ratio": 0, "max_drawdown": 0}
    initial_value = portfolio_values.iloc[0]
    final_value = portfolio_values.iloc[-1]
    days = (date_range[-1] - date_range[0]).days
    years = days / 365.25 if days > 0 else 0
    cagr = (final_value / initial_value) ** (1 / years) - 1 if years > 0 else (final_value / initial_value) - 1
    returns = portfolio_values.pct_change().dropna()
    stdev = returns.std() * np.sqrt(252) if not returns.empty else 0
    sharpe_ratio = (cagr - 0.01) / stdev if stdev > 0 else 0
    max_drawdown = (portfolio_values / portfolio_values.cummax() - 1).min()
    return {"initial_value": round(initial_value, 2), "final_value": round(final_value, 2), "cagr": round(cagr * 100, 2), "stdev": round(stdev * 100, 2), "sharpe_ratio": round(sharpe_ratio, 2), "max_drawdown": round(max_drawdown * 100, 2)}

async def get_price_from_r2(env, ticker):
    key = f"prices/{ticker}.csv"
    r2_object = await env.DATA_BUCKET.get(key)
    if r2_object is None: return None
    body = await r2_object.text()
    return pd.read_csv(StringIO(body), index_col='Date', parse_dates=True)['Close']

async def run_backtest_simulation(payload, env):
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
        if prices is None: missing_tickers.append(ticker)
        else: price_data[ticker] = prices
    
    if not price_data: return {"error": "無法載入任何有效的股票價格數據。"}

    common_index = None
    for prices in price_data.values():
        common_index = prices.index if common_index is None else common_index.intersection(prices.index)
    
    start_date, end_date = pd.to_datetime(start_date_str), pd.to_datetime(end_date_str)
    backtest_range = common_index[(common_index >= start_date) & (common_index <= end_date)]
    if backtest_range.empty: return {"error": "在指定的時間範圍內，所有資產沒有共同的交易日。"}

    aligned_prices = pd.DataFrame(index=backtest_range)
    for ticker, prices in price_data.items(): aligned_prices[ticker] = prices
    aligned_prices.ffill(inplace=True); aligned_prices.bfill(inplace=True)
    if aligned_prices.isnull().values.any(): return {"error": "數據清理後仍存在缺失值。"}

    results = {}
    for p_config in portfolios:
        portfolio_name = p_config.get('name')
        portfolio_values = pd.Series(index=backtest_range, dtype=float)
        current_cash = initial_amount
        current_holdings = {asset['ticker']: 0 for asset in p_config['assets']}
        rebalance_dates = []
        if rebalancing_period != 'never':
            current_date = backtest_range[0]
            while current_date <= backtest_range[-1]:
                rebalance_dates.append(current_date)
                if rebalancing_period == 'annually': current_date += pd.DateOffset(years=1)
                elif rebalancing_period == 'quarterly': current_date += pd.DateOffset(months=3)
                elif rebalancing_period == 'monthly': current_date += pd.DateOffset(months=1)
        if not rebalance_dates: rebalance_dates.append(backtest_range[0])
        next_rebalance_idx = 0
        for today in backtest_range:
            total_value = current_cash + sum(shares * aligned_prices.loc[today, ticker] for ticker, shares in current_holdings.items() if ticker in aligned_prices.columns and not pd.isna(aligned_prices.loc[today, ticker]))
            portfolio_values[today] = total_value
            if next_rebalance_idx < len(rebalance_dates) and today >= rebalance_dates[next_rebalance_idx]:
                current_cash = total_value
                current_holdings = {asset['ticker']: 0 for asset in p_config['assets']}
                for asset in p_config['assets']:
                    ticker, weight = asset['ticker'], asset['weight'] / 100.0
                    if ticker in aligned_prices.columns and not pd.isna(aligned_prices.loc[today, ticker]):
                        price = aligned_prices.loc[today, ticker]
                        if price > 0:
                            amount_to_invest = total_value * weight
                            shares_to_buy = amount_to_invest / price
                            current_holdings[ticker] += shares_to_buy
                            current_cash -= amount_to_invest
                next_rebalance_idx += 1
        results[portfolio_name] = portfolio_values

    if benchmark_ticker and benchmark_ticker in price_data:
        prices = aligned_prices[benchmark_ticker]
        if prices.iloc[0] > 0: results[benchmark_ticker] = (initial_amount / prices.iloc[0]) * prices
        
    final_results = {"dates": [d.strftime('%Y-%m-%d') for d in backtest_range], "portfolios": [], "warnings": [f"缺少數據: {', '.join(missing_tickers)}"] if missing_tickers else []}
    for name, values in results.items():
        metrics = calculate_metrics(values, backtest_range)
        final_results["portfolios"].append({"name": name, "values": [round(v, 2) for v in values.tolist()], "metrics": metrics})

    return final_results

# --- API 路由設定 (使用 Hono) ---

app = Hono()

# 使用 Hono 的 CORS 中介軟體，自動處理所有 /api/* 路由的跨域請求
app.use('/api/*', cors())

@app.get("/api/get_stocks")
async def handle_get_stocks(c):
    # Hono 將 env 放在 context 物件 'c' 中
    r2_object = await c.env.DATA_BUCKET.get("preprocessed_data.json")
    if r2_object is None:
        return Response.json({"error": "Preprocessed data not found in R2 bucket."}, status=404)
    data = await r2_object.json()
    return Response.json(data)

@app.post("/api/run_backtest")
async def handle_backtest(c):
    try:
        # Hono 的請求物件是 c.req
        payload = await c.req.json()
        results = await run_backtest_simulation(payload, c.env)
        return Response.json(results)
    except Exception as e:
        return Response.json({"error": str(e)}, status=500)

@app.post("/api/run_scan")
async def handle_scan(c):
    # 掃描邏輯與回測類似，此處從略。
    return Response.json({"message": "Scan endpoint not fully implemented yet."})

# --- Worker 主類別 ---
# Hono 框架本身就可以作為 fetch 處理器
class Worker:
    async def fetch(self, request, env, ctx):
        return await app.fetch(request, env, ctx)

