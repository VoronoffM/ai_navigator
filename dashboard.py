import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import threading
import requests
import urllib.parse
import warnings
from datetime import datetime
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from t_tech.invest.schemas import OrderDirection, MoneyValue
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX

# ИМПОРТ НАШИХ АГЕНТОВ
from market_agent import MarketAgent
from quant_agent import QuantAgent
from nlp_agent import NLPAgent
from risk_agent import RiskAgent
from execution_agent import ExecutionAgent

warnings.filterwarnings("ignore")
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

st.set_page_config(page_title="AI-Navigator Terminal", layout="wide")
st.title("📈 AI-Штурман: Мульти-Агентный Терминал")
st_autorefresh(interval=30000, key="data_refresh")

# Инициализация агентов
market = MarketAgent(TOKEN)
quant = QuantAgent()
nlp = NLPAgent()
risk = RiskAgent()
executor = ExecutionAgent(TOKEN)

if "logs" not in st.session_state: st.session_state.logs = []
if "selected_ticker" not in st.session_state: st.session_state.selected_ticker = "GAZP"

def add_log(text):
    time_str = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{time_str}] {text}")
    if len(st.session_state.logs) > 10: st.session_state.logs.pop(0)

def send_tg_worker(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage?chat_id={TG_CHAT_ID}&text={urllib.parse.quote(text)}"
        requests.get(url, timeout=5)
    except Exception as e: print(f"TG Error: {e}")

def send_tg_alert(text):
    threading.Thread(target=send_tg_worker, args=(text,)).start()

TICKERS = {"GAZP": "Газпром", "SBER": "Сбербанк", "LKOH": "Лукойл", "YDEX": "Яндекс", "T": "Т-Технологии", "GMKN": "Норникель"}

@st.cache_data(ttl=60)
def get_market_data():
    cash, positions, acc_id = market.get_portfolio_and_account()
    figi_map = market.get_figi_map(TICKERS.keys())
    
    market_data = {}
    for t in TICKERS:
        if t in figi_map:
            df = market.get_candles(figi_map[t], days=7)
            if not df.empty:
                market_data[t] = quant.calculate_metrics(df)
    return market_data, figi_map, positions, cash, acc_id

with st.spinner("Агенты синхронизируются с биржей..."):
    market_data, figi_map, portfolio_positions, cash, acc_id = get_market_data()

if not market_data:
    st.error("Нет данных от API.")
    st.stop()

action_plan = []
total_equity = cash

for ticker, df in market_data.items():
    last_z = df['z_score'].iloc[-1]
    last_price = df['close'].iloc[-1]
    signal = quant.get_signal(last_z)
    
    pos_info = portfolio_positions.get(ticker, {"count": 0, "current_price": 0})
    pos_val = pos_info["count"] * last_price
    total_equity += pos_val
    
    action_plan.append({
        "Тикер": ticker, "Название": TICKERS[ticker], "Цена": round(last_price, 2),
        "Z-Score": round(last_z, 2) if pd.notna(last_z) else 0.0,
        "Сигнал": signal, "В портфеле": pos_info["count"], "Стоимость": round(pos_val, 2)
    })

df_plan = pd.DataFrame(action_plan)

# ВЕРХНЯЯ ПАНЕЛЬ
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Общий Капитал (RUB)", f"{total_equity:,.2f}")
col_m2.metric("Свободный Кэш (RUB)", f"{cash:,.2f}")
col_m3.metric("Активов в портфеле", f"{len(portfolio_positions)} шт.")
if col_m4.button("💳 Пополнить на 100k", width='stretch'):
    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
    st.cache_data.clear(); st.rerun()

st.divider()

# СКРИНЕР
st.subheader("📊 Скринер рынка (Агент: Quant)")
cols = st.columns(len(TICKERS))
for i, row in df_plan.iterrows():
    with cols[i]:
        color = "green" if row["Сигнал"] == "BUY" else ("red" if row["Сигнал"] == "SELL" else "gray")
        st.markdown(f"#### :{color}[{row['Тикер']}]")
        st.caption(row["Название"])
        st.write(f"**{row['Цена']} ₽** | Z: {row['Z-Score']}")
        
        spark_df = market_data[row["Тикер"]].tail(24)
        fig_spark = go.Figure(go.Scatter(x=spark_df['time'], y=spark_df['close'], mode='lines', line=dict(color='#FFD700', width=2)))
        fig_spark.update_layout(height=80, margin=dict(l=0, r=0, t=0, b=0), xaxis=dict(visible=False), yaxis=dict(visible=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_spark, width='stretch', config={'displayModeBar': False})
        
        if st.button(f"Открыть {row['Тикер']}", key=f"btn_{row['Тикер']}", width='stretch'):
            st.session_state.selected_ticker = row['Тикер']
            st.rerun()

st.divider()

# ДЕТАЛЬНЫЙ ГРАФИК
sel = st.session_state.selected_ticker
sel_df = market_data[sel]
sel_info = df_plan[df_plan['Тикер'] == sel].iloc[0]

col_chart, col_ctrl = st.columns([3, 1])
with col_chart:
    st.subheader(f"График {sel} - 1H (Агент: Quant)")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=sel_df['time'], open=sel_df['open'], high=sel_df['high'], low=sel_df['low'], close=sel_df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['upper_band'], line=dict(color='rgba(255, 82, 82, 0.5)', width=1, dash='dot'), name='Верхняя'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['lower_band'], line=dict(color='rgba(38, 166, 154, 0.5)', width=1, dash='dot'), name='Нижняя'))
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, b=0, t=0))
    st.plotly_chart(fig, width='stretch')

with col_ctrl:
    st.subheader("Управление (Агент: Execution)")
    st.metric("Цена", f"{sel_info['Цена']} RUB")
    st.metric("Z-Score", f"{sel_info['Z-Score']} σ", delta=sel_info['Сигнал'])
    
    st.divider()
    autopilot = st.toggle("🤖 АВТОПИЛОТ (Сканер рынка)", value=False)
    
    st.markdown("**Ручная торговля**")
    c1, c2 = st.columns(2)
    if c1.button(f"🟢 КУПИТЬ", width='stretch'):
        p, q, s = executor.place_order(figi_map[sel], acc_id, OrderDirection.ORDER_DIRECTION_BUY)
        if s == "FILLED":
            add_log(f"🛒 Куплено {q} лотов {sel} по {p:.2f}")
            send_tg_alert(f"🛒 Ручная покупка {sel} по {p:.2f}")
            st.cache_data.clear(); st.rerun()
        else:
            add_log(f"❌ Ошибка: {s}")

    if c2.button(f"🔴 ПРОДАТЬ", width='stretch'):
        if sel_info['В портфеле'] > 0:
            p, q, s = executor.place_order(figi_map[sel], acc_id, OrderDirection.ORDER_DIRECTION_SELL, sel_info['В портфеле'])
            if s == "FILLED":
                add_log(f"💸 Продано {q} лотов {sel} по {p:.2f}")
                send_tg_alert(f"💸 Ручная продажа {sel} по {p:.2f}")
                st.cache_data.clear(); st.rerun()

st.divider()
col_log, col_plan = st.columns([1, 2])
with col_plan:
    st.subheader("🎯 План Действий")
    st.dataframe(df_plan[["Тикер", "Название", "Цена", "Z-Score", "Сигнал", "В портфеле", "Стоимость"]], width='stretch', hide_index=True)
with col_log:
    st.subheader("📜 Логи")
    if not st.session_state.logs: st.info("Агенты ожидают сигналов...")
    for log in reversed(st.session_state.logs): st.code(log, language="bash")

# АВТОПИЛОТ (Сканирует все бумаги)
if autopilot:
    for _, row in df_plan.iterrows():
        t, sig, pos_count = row["Тикер"], row["Сигнал"], row["В портфеле"]
        if sig == "BUY" and pos_count == 0:
            is_safe, msg = risk.validate_buy_order(cash, 0, row["Цена"], 10)
            if is_safe:
                p, q, s = executor.place_order(figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_BUY)
                if s == "FILLED":
                    add_log(f"✅ АВТОПИЛОТ КУПИЛ {t} по {p:.2f}")
                    send_tg_alert(f"🤖 Купил {t} по {p:.2f}")
                    st.cache_data.clear(); st.rerun()
        elif sig == "SELL" and pos_count > 0:
            p, q, s = executor.place_order(figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_SELL, pos_count)
            if s == "FILLED":
                add_log(f"✅ АВТОПИЛОТ ПРОДАЛ {t} по {p:.2f}")
                send_tg_alert(f"🤖 Продал {t} по {p:.2f}")
                st.cache_data.clear(); st.rerun()