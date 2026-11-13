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

# Импорт наших агентов
from risk_agent import RiskAgent
from nlp_agent import NLPAgent

warnings.filterwarnings("ignore")
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

st.set_page_config(page_title="AI-Navigator", layout="wide")
st.title("📈 AI-Штурман: Терминал")
st_autorefresh(interval=15000, key="data_refresh")

# Инициализация агентов и состояний
nlp = NLPAgent()
risk = RiskAgent()

if "logs" not in st.session_state: st.session_state.logs = []
if "last_traded_candle" not in st.session_state: st.session_state.last_traded_candle = None

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
    retries = 3
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except RequestError as e:
            if e.status_code == 429:
                add_log(f"⚠️ API Rate Limit. Ждем 2 сек...")
                time.sleep(2)
            elif attempt == retries - 1:
                add_log(f"❌ API Error: {e.details}")
                raise e
            else:
                time.sleep(1)

@st.cache_data(ttl=15)
def get_cached_candles(figi):
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        now = datetime.utcnow()
        candles = safe_api_call(
            client.market_data.get_candles, 
            figi=figi, from_=now - timedelta(days=1), to=now, 
            interval=CandleInterval.CANDLE_INTERVAL_5_MIN
        )
        data = [{"time": c.time, "open": get_price(c.open), "high": get_price(c.high), "low": get_price(c.low), "close": get_price(c.close)} for c in candles.candles if c.is_complete]
        return pd.DataFrame(data)

def fetch_data():
    if not TOKEN: return pd.DataFrame(), None, None, 0, 0, 10
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        accounts = safe_api_call(client.users.get_accounts)
        if not accounts.accounts:
            acc_id = client.sandbox.open_sandbox_account().account_id
            client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
        else:
            acc_id = accounts.accounts[0].id
        
        portfolio = safe_api_call(client.operations.get_portfolio, account_id=acc_id)
        cash, shares_count = 0, 0
        for pos in portfolio.positions:
            if pos.instrument_type == "currency": cash = pos.quantity.units
            if "GAZP" in str(pos.ticker): shares_count = pos.quantity.units

        shares = safe_api_call(client.instruments.shares)
        figi = next((s.figi for s in shares.instruments if s.ticker == "GAZP"), None)
        lot_size = next((s.lot for s in shares.instruments if s.ticker == "GAZP"), 10)
    return get_cached_candles(figi), figi, acc_id, cash, shares_count, lot_size

def place_order(client, figi, acc_id, direction, qty_lots=1):
    req_id = str(uuid.uuid4())
    response = safe_api_call(client.orders.post_order, instrument_id=figi, quantity=qty_lots, account_id=acc_id, direction=direction, order_type=OrderType.ORDER_TYPE_MARKET, order_id=req_id)
    
    status = response.execution_report_status
    if status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_FILL:
        return get_price(response.executed_order_price), response.lots_executed, "FILLED"
    elif status == OrderExecutionReportStatus.EXECUTION_REPORT_STATUS_REJECTED:
        return None, 0, "REJECTED"
    else:
        return None, response.lots_executed, "PENDING"

df, figi, acc_id, cash, shares_count, lot_size = fetch_data()

if not df.empty and len(df) >= 20:
    window = 20
    df['mean'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['z_score'] = (df['close'] - df['mean']) / df['std']
    df['upper_band'] = df['mean'] + (1.5 * df['std'])
    df['lower_band'] = df['mean'] - (1.5 * df['std'])
    
    last_z = df['z_score'].iloc[-1]
    last_price = df['close'].iloc[-1]
    last_candle_time = df['time'].iloc[-1]
    
    # --- САЙДБАР ---
    with st.sidebar:
        st.header("Портфель")
        st.metric("Кэш (RUB)", f"{cash:,.2f}")
        st.metric("Акции GAZP", f"{shares_count} шт.")
        
        # Возвращаем кнопку пополнения
        if st.button("💳 Пополнить на 100 000 RUB"):
            with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
            st.cache_data.clear()
            st.rerun()
            
        # Возвращаем кнопку сброса
        if shares_count > 0:
            if st.button("🗑️ Продать все акции (Сброс)"):
                lots_to_sell = shares_count // lot_size 
                if lots_to_sell > 0:
                    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                        p, q, s = place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=lots_to_sell)
                    add_log(f"🗑️ Сброс: {s}, продано {q} лотов.")
                    st.cache_data.clear()
                    st.rerun()

        st.divider()
        st.header("Робот")
        st.metric("Цена", f"{last_price:.2f} RUB")
        st.metric("Z-Score", f"{last_z:.2f} σ" if pd.notna(last_z) else "0.00 σ")
        
        signal = "HOLD"
        if pd.notna(last_z) and df['std'].iloc[-1] > 0:
            if last_z <= -1.5: signal = "BUY"
            elif last_z >= 1.5: signal = "SELL"

        force_buy = st.toggle("🧪 Принудительный сигнал BUY", value=False)
        if force_buy:
            signal = "BUY"
            st.warning("🧪 СИМУЛЯЦИЯ: Робот видит аномалию -1.5σ!")
        else:
            if signal == "BUY": st.success("🟢 BUY (Реальная перепроданность)")
            elif signal == "SELL": st.error("🔴 SELL (Реальная перекупленность)")
            else: st.info("⚪ HOLD (Нейтрально)")

        st.divider()
        st.header("📰 Новости (NLP)")
        news_scenario = st.selectbox("Симуляция:", ["Нейтрально", "Паника толпы", "Фундаментальный негатив"])
        news_text = "Санкции и дефолт!" if news_scenario == "Фундаментальный негатив" else ("Паника и слив!" if news_scenario == "Паника толпы" else "Обычный день")
        
        nlp_res = nlp.analyze_news(news_text)
        if not nlp_res["allow_trade"]: st.error(f"NLP: {nlp_res['reason']}")
        else: st.info(f"NLP: {nlp_res['reason']}")

        st.divider()
        autopilot = st.toggle("🤖 АВТОПИЛОТ", value=False)
        
        # Агентная логика
        if autopilot and figi and acc_id and st.session_state.last_traded_candle != last_candle_time:
            if signal == "BUY":
                if not nlp_res["allow_trade"]:
                    add_log(f"❌ NLP блок: {nlp_res['reason']}")
                    st.session_state.last_traded_candle = last_candle_time
                else:
                    is_safe, msg = risk.validate_buy_order(cash, shares_count, last_price, lot_size)
                    if not is_safe:
                        add_log(f"🛡️ Risk блок: {msg}")
                    else:
                        with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                            p, q, s = place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_BUY)
                        if s == "FILLED":
                            add_log(f"✅ АВТОПИЛОТ КУПИЛ {q} лот(а) по {p:.2f}")
                            send_tg_alert(f"🤖 Купил GAZP по {p:.2f}")
                            st.session_state.last_traded_candle = last_candle_time
                            st.cache_data.clear(); st.rerun()
                            
            elif signal == "SELL" and shares_count > 0:
                is_safe, msg = risk.validate_sell_order(shares_count, lot_size)
                if is_safe:
                    lots = shares_count // lot_size
                    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                        p, q, s = place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=lots)
                    if s == "FILLED":
                        add_log(f"✅ АВТОПИЛОТ ПРОДАЛ {q} лотов по {p:.2f}")
                        send_tg_alert(f"🤖 Продал GAZP по {p:.2f}")
                        st.session_state.last_traded_candle = last_candle_time
                        st.cache_data.clear(); st.rerun()

        # Ручная торговля (возвращаем кнопки)
        st.divider()
        st.subheader("Ручная торговля")
        col1, col2 = st.columns(2)
        if col1.button("🟢 КУПИТЬ", key="buy_btn"):
            with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                p, q, s = place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_BUY)
            if s == "FILLED":
                add_log(f"🛒 Куплено {q} лота вручную по {p:.2f}")
                send_tg_alert(f"🛒 Ручная покупка по {p:.2f}")
                st.cache_data.clear(); st.rerun()
                
        if col2.button("🔴 ПРОДАТЬ", key="sell_btn"):
            lots_to_sell = shares_count // lot_size
            if lots_to_sell > 0:
                with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                    p, q, s = place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=lots_to_sell)
                if s == "FILLED":
                    add_log(f"💸 Продано {q} лотов вручную по {p:.2f}")
                    send_tg_alert(f"💸 Ручная продажа по {p:.2f}")
                    st.cache_data.clear(); st.rerun()

    # --- ГРАФИК (Возвращаем красоту) ---
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)', name='Цена'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['upper_band'], line=dict(color='rgba(255, 82, 82, 0.5)', width=1, dash='dot'), name='Верхняя'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['lower_band'], line=dict(color='rgba(38, 166, 154, 0.5)', width=1, dash='dot'), name='Нижняя'))
    
    fig.update_layout(template="plotly_dark", height=550, xaxis_rangeslider_visible=False, title="График GAZP (5 мин)")
    if len(df) > 50: 
        fig.update_xaxes(range=[df['time'].iloc[-50], df['time'].iloc[-1]]) # Возвращаем зум на 50 свечей
        
    st.plotly_chart(fig, width='stretch')

    st.divider()
    st.subheader("📜 Системный лог робота")
    for log in reversed(st.session_state.logs): 
        st.code(log, language="bash")
else:
    st.warning("Недостаточно данных для отображения (нужно минимум 20 завершенных свечей).")