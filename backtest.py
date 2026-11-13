import os
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")

def get_price(q):
    return q.units + q.nano / 1e9

def fetch_history_chunked(client, figi, days=90):
    now = datetime.utcnow()
    start_time = now - timedelta(days=days)
    all_candles = []
    current_start = start_time
    
    while current_start < now:
        current_end = current_start + timedelta(days=7)
        if current_end > now: current_end = now
        try:
            candles_response = client.market_data.get_candles(
                figi=figi, from_=current_start, to=current_end,
                interval=CandleInterval.CANDLE_INTERVAL_5_MIN
            )
            all_candles.extend(candles_response.candles)
        except Exception:
            pass
        current_start = current_end
        time.sleep(0.3)
    return all_candles

def run_backtest(ticker="GAZP", days=90, use_tp_sl=True, tariff="Trader"):
    print(f"📥 Загрузка данных {ticker} для тарифа {tariff}...")
    
    # Выставляем комиссию в зависимости от тарифа
    if tariff == "Free":
        commission = 0.003  # 0.3% на бесплатном
    else:
        commission = 0.0005 # 0.05% на трейдере

    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        shares = client.instruments.shares()
        figi = next((s.figi for s in shares.instruments if s.ticker == ticker), None)
        if not figi: return

        raw_candles = fetch_history_chunked(client, figi, days)
        data = []
        for c in raw_candles:
            if not c.is_complete: continue
            data.append({"time": c.time, "open": get_price(c.open), "high": get_price(c.high), "low": get_price(c.low), "close": get_price(c.close)})
            
    df = pd.DataFrame(data)
    
    window = 20
    df['mean'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['z_score'] = (df['close'] - df['mean']) / df['std']
    
    balance = 100000.0 
    position = 0 
    completed_trades = 0
    slippage = 0.0002   # 0.02%
    
    equity_curve = [100000.0] 
    entry_price = 0
    tp_price = 0
    sl_price = 0
    
    for i in range(window, len(df) - 1):
        signal_z = df['z_score'].iloc[i]
        exec_price = df['open'].iloc[i+1] 
        
        # --- ВХОД ---
        if signal_z <= -1.5 and position == 0:
            buy_price = exec_price * (1 + slippage) 
            cost = buy_price * 10
            fee = cost * commission
            if balance >= cost + fee:
                balance -= (cost + fee)
                position = 10
                entry_price = buy_price
                
                if use_tp_sl:
                    tp_price = entry_price * 1.015 # Тейк +1.5%
                    sl_price = entry_price * 0.992 # Стоп -0.8%
        
        # --- ВЫХОД ---
        elif position > 0:
            if use_tp_sl:
                high = df['high'].iloc[i+1]
                low = df['low'].iloc[i+1]
                
                exit_price = 0
                exit_triggered = False
                
                if high >= tp_price:
                    exit_price = tp_price * (1 - slippage)
                    exit_triggered = True
                elif low <= sl_price:
                    exit_price = sl_price * (1 - slippage)
                    exit_triggered = True
                    
                if exit_triggered:
                    revenue = exit_price * position
                    fee = revenue * commission
                    balance += (revenue - fee)
                    position = 0
                    completed_trades += 1
            
            elif signal_z >= 1.5:
                sell_price = exec_price * (1 - slippage)
                revenue = sell_price * position
                fee = revenue * commission
                balance += (revenue - fee)
                position = 0
                completed_trades += 1
                
        current_equity = balance + (position * exec_price)
        equity_curve.append(current_equity)
        
    final_equity = equity_curve[-1]
    total_return = (final_equity - 100000) / 100000 * 100
    eq_series = pd.Series(equity_curve)
    max_drawdown = ((eq_series - eq_series.cummax()) / eq_series.cummax()).min() * 100
    
    print("\n" + "="*40)
    print(f"📊 РЕЗУЛЬТАТ (Тариф: {tariff}, Сделок: {completed_trades})")
    print("="*40)
    print(f"Итоговый капитал:  {final_equity:,.2f} ₽")
    print(f"Доходность:        {total_return:+.2f}%")
    print(f"Макс. просадка:    {max_drawdown:.2f}%")
    print("="*40)

if __name__ == "__main__":
    # Прогоняем только один раз для скорости (без дублей загрузки)
    run_backtest("GAZP", days=90, use_tp_sl=True, tariff="Free")
    run_backtest("GAZP", days=90, use_tp_sl=True, tariff="Trader")