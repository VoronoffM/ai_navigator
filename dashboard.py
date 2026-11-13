import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import threading
import requests
import urllib.parse
import warnings
import uuid
import time
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, OrderDirection, OrderType, MoneyValue, OrderExecutionReportStatus
from t_tech.invest.exceptions import RequestError
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

from risk_agent import RiskAgent
from nlp_agent import NLPAgent

warnings.filterwarnings("ignore")
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

st.set_page_config(page_title="AI-Navigator Terminal", layout="wide")

# --- АГЕНТСКИЕ КЛАССЫ ---
nlp = NLPAgent()
risk = RiskAgent()

if "logs" not in st.session_state: st.session_state.logs = []
if "selected_ticker" not in st.session_state: st.session_state.selected_ticker = "GAZP"

def add_log(text):
    time_str = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{time_str}] {text}")
    if len(st.session_state.logs) > 10: st.session_state.logs.pop(0)

def get_price(q): return q.units + q.nano / 1e9

def send_tg_worker(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage?chat_id={TG_CHAT_ID}&text={urllib.parse.quote(text)}"
        requests.get(url, timeout=5)
    except Exception as e: print(f"TG Error: {e}")

def send_tg_alert(text):
    threading.Thread(target=send_tg_worker, args=(text,)).start()

def safe_api_call(func, *args, **kwargs):
    for attempt in range(3):
        try: return func(*args, **kwargs)
        except RequestError as e:
            if e.status_code == 429: time.sleep(2)
            elif attempt == 2: raise e
            else: time.sleep(1)

# Список бумаг для скринера
TICKERS = {
    "GAZP": "Газпром", "SBER": "Сбербанк", "LKOH": "Лукойл", 
    "YDEX": "Яндекс", "T": "Т-Технологии", "GMKN": "Норникель"
}

@st.cache_data(ttl=300)
def get_cached_candles(figi):
    """Кэшируем свечи на 5 минут, чтобы не спамить API"""
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        now = datetime.utcnow()
        candles = safe_api_call(
            client.market_data.get_candles, 
            figi=figi, from_=now - timedelta(days=7), to=now, 
            interval=CandleInterval.CANDLE_INTERVAL_HOUR
        )
        data = [{"time": c.time, "open": get_price(c.open), "high": get_price(c.high), "low": get_price(c.low), "close": get_price(c.close)} for c in candles.candles if c.is_complete]
        return pd.DataFrame(data)

@st.cache_data(ttl=20)
def fetch_market_and_portfolio():
    if not TOKEN: return {}, {}, None, 0
    
    market_data, figi_map = {}, {}
    
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        accounts = safe_api_call(client.users.get_accounts)
        if not accounts.accounts:
            acc_id = client.sandbox.open_sandbox_account().account_id
            client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
        else:
            acc_id = accounts.accounts[0].id
        
        portfolio = safe_api_call(client.operations.get_portfolio, account_id=acc_id)
        cash, positions = 0, {}
        for pos in portfolio.positions:
            if pos.instrument_type == "currency" and pos.figi == "RUB000UTSTOM":
                cash = pos.quantity.units
            elif pos.ticker in TICKERS:
                positions[pos.ticker] = {"count": pos.quantity.units, "current_price": get_price(pos.current_price)}

        shares = safe_api_call(client.instruments.shares)
        for ticker in TICKERS:
            share_info = next((s for s in shares.instruments if s.ticker == ticker), None)
            if share_info:
                figi_map[ticker] = share_info.figi
                df = get_cached_candles(share_info.figi)
                if not df.empty: market_data[ticker] = df

    return market_data, figi_map, positions, cash, acc_id

def place_order(client, figi, acc_id, direction, qty_lots=1):
    req_id = str(uuid.uuid4())
    resp = safe_api_call(client.orders.post_order, instrument_id=figi, quantity=qty_lots, account_id=acc_id, direction=direction, order_type=OrderType.ORDER_TYPE_MARKET, order_id=req_id)
    if resp.execution_report_status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL:
        return get_price(resp.executed_order_price), resp.lots_executed, "FILLED"
    return None, resp.lots_executed, "PENDING/REJECTED"

# --- ИНИЦИАЛИЗАЦИЯ ДАННЫХ ---
with st.spinner("Синхронизация с биржей..."):
    market_data, figi_map, portfolio_positions, cash, acc_id = fetch_market_and_portfolio()

if not market_data:
    st.error("Нет данных от API. Проверьте токен.")
    st.stop()

# --- СЧИТАЕМ МЕТРИКИ И СИГНАЛЫ ---
action_plan = []
total_equity = cash

for ticker, df in market_data.items():
    if len(df) < 20: continue
    df['mean'] = df['close'].rolling(window=20).mean()
    df['std'] = df['close'].rolling(window=20).std()
    df['z_score'] = (df['close'] - df['mean']) / df['std']
    
    last_z, last_price = df['z_score'].iloc[-1], df['close'].iloc[-1]
    signal = "HOLD"
    if pd.notna(last_z):
        if last_z <= -1.5: signal = "BUY"
        elif last_z >= 1.5: signal = "SELL"
        
    pos_info = portfolio_positions.get(ticker, {"count": 0, "current_price": 0})
    pos_val = pos_info["count"] * last_price
    total_equity += pos_val
    
    action_plan.append({
        "Тикер": ticker, "Название": TICKERS[ticker], "Цена": round(last_price, 2),
        "Z-Score": round(last_z, 2) if pd.notna(last_z) else 0.0,
        "Сигнал": signal, "В портфеле": pos_info["count"], "Стоимость": round(pos_val, 2)
    })

df_plan = pd.DataFrame(action_plan)

# --- ВЕРХНЯЯ ПАНЕЛЬ (МЕТРИКИ) ---
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Общий Капитал (RUB)", f"{total_equity:,.2f}")
col_m2.metric("Свободный Кэш (RUB)", f"{cash:,.2f}")
col_m3.metric("Активов в портфеле", f"{len(portfolio_positions)} шт.")
if col_m4.button("💳 Пополнить на 100k", width='stretch'):
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
    st.cache_data.clear(); st.rerun()

st.divider()

# --- СЕТКА БУМАГ (WATCHLIST) ---
st.subheader("📊 Скринер рынка (Выберите актив для детального графика)")
cols = st.columns(len(TICKERS))

for i, row in df_plan.iterrows():
    with cols[i]:
        # Цвет заголовка в зависимости от сигнала
        color = "green" if row["Сигнал"] == "BUY" else ("red" if row["Сигнал"] == "SELL" else "gray")
        st.markdown(f"#### :{color}[{row['Тикер']}]")
        st.caption(row["Название"])
        st.write(f"**{row['Цена']} ₽** | Z: {row['Z-Score']}")
        
        # Мини-график (Спарклайн) за неделю
        spark_df = market_data[row["Тикер"]].tail(24) # Последние 24 часа
        fig_spark = go.Figure(go.Scatter(x=spark_df['time'], y=spark_df['close'], mode='lines', line=dict(color='#FFD700', width=2)))
        fig_spark.update_layout(
            height=80, margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_spark, width='stretch', config={'displayModeBar': False})
        
        if st.button(f"Открыть {row['Тикер']}", key=f"btn_{row['Тикер']}", width='stretch'):
            st.session_state.selected_ticker = row['Тикер']
            st.rerun()

st.divider()

# --- ДЕТАЛЬНЫЙ ГРАФИК И ТОРГОВЛЯ ---
sel = st.session_state.selected_ticker
sel_df = market_data[sel]
sel_info = df_plan[df_plan['Тикер'] == sel].iloc[0]

col_chart, col_ctrl = st.columns([3, 1])

with col_chart:
    st.subheader(f"График {sel} ({TICKERS[sel]}) - 1H")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=sel_df['time'], open=sel_df['open'], high=sel_df['high'], low=sel_df['low'], close=sel_df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, b=0, t=0))
    st.plotly_chart(fig, width='stretch')

with col_ctrl:
    st.subheader("Управление")
    st.metric("Цена", f"{sel_info['Цена']} RUB")
    st.metric("Z-Score", f"{sel_info['Z-Score']} σ", delta=sel_info['Сигнал'])
    
    st.divider()
    autopilot = st.toggle("🤖 АВТОПИЛОТ (Все бумаги)", value=False)
    
    st.markdown("**Ручная торговля**")
    qty = st.number_input("Кол-во лотов", min_value=1, max_value=10, value=1)
    
    c1, c2 = st.columns(2)
    if c1.button(f"🟢 КУПИТЬ", width='stretch'):
        with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
            p, q, s = place_order(client, figi_map[sel], acc_id, OrderDirection.ORDER_DIRECTION_BUY, qty)
        if s == "FILLED":
            add_log(f"🛒 Куплено {q} лотов {sel} по {p:.2f}")
            send_tg_alert(f"🛒 Ручная покупка {sel} по {p:.2f}")
            st.cache_data.clear(); st.rerun()

    if c2.button(f"🔴 ПРОДАТЬ", width='stretch'):
        if sel_info['В портфеле'] > 0:
            with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                p, q, s = place_order(client, figi_map[sel], acc_id, OrderDirection.ORDER_DIRECTION_SELL, sel_info['В портфеле'])
            if s == "FILLED":
                add_log(f"💸 Продано {q} лотов {sel} по {p:.2f}")
                send_tg_alert(f"💸 Ручная продажа {sel} по {p:.2f}")
                st.cache_data.clear(); st.rerun()

# --- АВТОПИЛОТ И ЛОГИ ---
st.divider()
col_log, col_plan = st.columns([1, 2])

with col_plan:
    st.subheader("🎯 План Действий (Action Plan)")
    st.dataframe(df_plan[["Тикер", "Название", "Цена", "Z-Score", "Сигнал", "В портфеле", "Стоимость"]], width='stretch', hide_index=True)

with col_log:
    st.subheader("📜 Логи робота")
    if not st.session_state.logs: st.info("Робот ожидает сигналов...")
    for log in reversed(st.session_state.logs): st.code(log, language="bash")

# Логика автопилота (сканирует ВСЕ бумаги)
if autopilot:
    for _, row in df_plan.iterrows():
        t, sig, pos_count = row["Тикер"], row["Сигнал"], row["В портфеле"]
        
        if sig == "BUY" and pos_count == 0:
            is_safe, msg = risk.validate_buy_order(cash, 0, row["Цена"], 10)
            if is_safe:
                with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                    p, q, s = place_order(client, figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_BUY)
                if s == "FILLED":
                    add_log(f"✅ АВТОПИЛОТ КУПИЛ {t} по {p:.2f}")
                    send_tg_alert(f"🤖 Купил {t} по {p:.2f}")
                    st.cache_data.clear(); st.rerun()
                    
        elif sig == "SELL" and pos_count > 0:
            with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                p, q, s = place_order(client, figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=pos_count)
            if s == "FILLED":
                add_log(f"✅ АВТОПИЛОТ ПРОДАЛ {t} по {p:.2f}")
                send_tg_alert(f"🤖 Продал {t} по {p:.2f}")
                st.cache_data.clear(); st.rerun()