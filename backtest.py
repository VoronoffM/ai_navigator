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
        
        retries = 3
        success = False
        while retries > 0 and not success:
            try:
                candles_response = client.market_data.get_candles(
                    figi=figi, from_=current_start, to=current_end,
                    interval=CandleInterval.CANDLE_INTERVAL_5_MIN
                )
                all_candles.extend(candles_response.candles)
                success = True
            except Exception as e:
                retries -= 1
                time.sleep(1)
                
        if not success:
            raise Exception("❌ Ошибка загрузки. Остановка.")
            
        current_start = current_end
        time.sleep(0.3)
    
    all_candles.sort(key=lambda x: x.time)
    unique_candles = []
    seen_times = set()
    for c in all_candles:
        if c.time not in seen_times:
            unique_candles.append(c)
            seen_times.add(c.time)
            
    return unique_candles

def run_backtest(ticker="GAZP", days=90, use_tp_sl=True, tariff="Trader", use_nlp=False):
    print(f"📥 Загрузка данных {ticker}... (AI-фильтр: {'ВКЛ' if use_nlp else 'ВЫКЛ'})")
    
    if tariff == "Free":
        commission = 0.003  
    else:
        commission = 0.0005 

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
    slippage = 0.0002   
    lot_size = 10
    
    equity_curve = [100000.0] 
    entry_price = 0
    tp_price = 0
    sl_price = 0
    
    for i in range(window, len(df) - 1):
        signal_z = df['z_score'].iloc[i]
        next_open = df['open'].iloc[i+1]
        
        # --- ЛОГИКА AI-ФИЛЬТРА (Симуляция NLP) ---
        # Если падение слишком сильное (Z < -2.5), значит там плохие новости. AI блокирует!
        nlp_blocks = False
        if use_nlp and signal_z < -2.5:
            nlp_blocks = True
        
        # --- ВХОД ---
        if signal_z <= -1.5 and position == 0 and not nlp_blocks:
            buy_price = next_open * (1 + slippage) 
            cost = buy_price * lot_size
            fee = cost * commission
            if balance >= cost + fee:
                balance -= (cost + fee)
                position = lot_size
                entry_price = buy_price
                
                if use_tp_sl:
                    tp_price = entry_price * 1.015 
                    sl_price = entry_price * 0.992 
        
        # --- ВЫХОД ---
        elif position > 0:
            candle_high = df['high'].iloc[i+1]
            candle_low = df['low'].iloc[i+1]
            candle_open = df['open'].iloc[i+1]
            
            exit_price = 0
            exit_triggered = False
            
            if use_tp_sl:
                if candle_low <= sl_price and candle_high >= tp_price:
                    exit_price = sl_price * (1 - slippage) if candle_open > sl_price else candle_open * (1 - slippage)
                    exit_triggered = True
                elif candle_low <= sl_price:
                    exit_price = sl_price * (1 - slippage) if candle_open > sl_price else candle_open * (1 - slippage)
                    exit_triggered = True
                elif candle_high >= tp_price:
                    exit_price = tp_price * (1 - slippage) if candle_open < tp_price else candle_open * (1 - slippage)
                    exit_triggered = True
            
            if not exit_triggered and signal_z >= 1.5:
                exit_price = next_open * (1 - slippage)
                exit_triggered = True
                
            if exit_triggered:
                revenue = exit_price * position
                fee = revenue * commission
                balance += (revenue - fee)
                position = 0
                completed_trades += 1
                
        current_close = df['close'].iloc[i+1]
        current_equity = balance + (position * current_close)
        equity_curve.append(current_equity)
        
    final_equity = equity_curve[-1]
    total_return = (final_equity - 100000) / 100000 * 100
    eq_series = pd.Series(equity_curve)
    max_drawdown = ((eq_series - eq_series.cummax()) / eq_series.cummax()).min() * 100
    
    print("\n" + "="*40)
    print(f"📊 РЕЗУЛЬТАТ (AI: {'ВКЛ' if use_nlp else 'ВЫКЛ'}, Сделок: {completed_trades})")
    print("="*40)
    print(f"Итоговый капитал:  {final_equity:,.2f} ₽")
    print(f"Доходность:        {total_return:+.2f}%")
    print(f"Макс. просадка:    {max_drawdown:.2f}%")
    print("="*40)

if __name__ == "__main__":
    # Сравниваем без AI и с AI (на тарифе Trader)
    run_backtest("GAZP", days=90, use_tp_sl=True, tariff="Trader", use_nlp=False)
    run_backtest("GAZP", days=90, use_tp_sl=True, tariff="Trader", use_nlp=True)