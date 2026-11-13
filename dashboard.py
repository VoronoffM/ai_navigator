import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os
import threading
import requests
import urllib.parse
import warnings
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from t_tech.invest.schemas import OrderDirection, MoneyValue
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX

# ИМПОРТ АГЕНТОВ
from market_agent import MarketAgent
from quant_agent import QuantAgent
from execution_agent import ExecutionAgent
from orchestrator_agent import OrchestratorAgent 

warnings.filterwarnings("ignore")
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

st.set_page_config(page_title="AI-Navigator Terminal", layout="wide")
st.title("📈 AI-Штурман: Мульти-Агентный Терминал")

if "logs" not in st.session_state: st.session_state.logs = []
if "selected_ticker" not in st.session_state: st.session_state.selected_ticker = "GAZP"

market = MarketAgent(TOKEN)
quant = QuantAgent()
executor = ExecutionAgent(TOKEN)
orchestrator = OrchestratorAgent()

def add_log(text):
    time_str = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{time_str}] {text}")
    if len(st.session_state.logs) > 15: st.session_state.logs.pop(0)

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
    instruments_map = market.get_instruments_info(TICKERS.keys()) 
    
    market_data = {}
    for t in TICKERS:
        if t in instruments_map:
            df = market.get_candles(instruments_map[t]["figi"], days=7)
            if not df.empty:
                market_data[t] = quant.calculate_metrics(df)
    return market_data, instruments_map, positions, cash, acc_id

with st.spinner("Агенты синхронизируются с биржей..."):
    market_data, instruments_map, portfolio_positions, cash, acc_id = get_market_data()

if not market_data:
    st.error("Нет данных от API.")
    st.stop()

action_plan = []
total_assets_value = 0 
total_equity = cash    

for ticker, df in market_data.items():
    last_z = df['z_score'].iloc[-1]
    last_price = df['close'].iloc[-1]
    signal_visual = quant.get_signal(last_z)
    
    pos_info = portfolio_positions.get(ticker, {"count": 0, "current_price": 0})
    pos_val = pos_info["count"] * last_price
    
    total_assets_value += pos_val
    total_equity += pos_val
    
    action_plan.append({
        "Тикер": ticker, "Название": TICKERS[ticker], "Цена": round(last_price, 2),
        "Z-Score": round(last_z, 2) if pd.notna(last_z) else 0.0,
        "Сигнал": signal_visual, "В портфеле": pos_info["count"], "Стоимость": round(pos_val, 2)
    })

df_plan = pd.DataFrame(action_plan)

# ЛЕВОЕ МЕНЮ
with st.sidebar:
    st.header("💼 Ваш Портфель")
    st.metric("Общий Капитал (RUB)", f"{total_equity:,.2f}")
    st.metric("Стоимость активов", f"{total_assets_value:,.2f}")
    st.metric("Свободный Кэш (RUB)", f"{cash:,.2f}")
    
    if st.button("💳 Пополнить на 100k", width='stretch'):
        with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
            client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
        st.cache_data.clear(); st.rerun()

    st.divider()
    st.markdown("### 🎯 Выбор актива")
    selected_ticker = st.radio(
        "Акция для детального анализа:",
        list(TICKERS.keys()),
        format_func=lambda x: f"{x} ({TICKERS[x]})",
        index=list(TICKERS.keys()).index(st.session_state.selected_ticker)
    )
    if selected_ticker != st.session_state.selected_ticker:
        st.session_state.selected_ticker = selected_ticker
        st.rerun()

    st.divider()
    st.markdown("### 🦾 Режим работы")
    autopilot = st.toggle("🤖 АВТОПИЛОТ (ВСЕ БУМАГИ)", value=False)
    
    st.divider()
    st.markdown("### 📰 Симуляция новостей")
    news_scenario = st.selectbox("Фон для теста NLP:", ["Нейтрально", "Паника толпы", "Фундаментальный негатив"])
    if news_scenario == "Фундаментальный негатив":
        news_text = "Газпром объявил дефолт!"
    elif news_scenario == "Паника толпы":
        news_text = "На рынке паника и обвал!"
    else:
        news_text = "Обычный день, новостей нет."

# ЦЕНТРАЛЬНАЯ ЧАСТЬ: СКРИНЕР
st.subheader("📊 Скринер рынка")
cols = st.columns(len(TICKERS))
for i, row in df_plan.iterrows():
    with cols[i]:
        color = "green" if row["Сигнал"] == "BUY" else ("red" if row["Сигнал"] == "SELL" else "gray")
        st.markdown(f"#### :{color}[{row['Тикер']}]")
        st.write(f"**{row['Цена']} ₽** | Z: {row['Z-Score']}")
        
        spark_df = market_data[row["Тикер"]].tail(24)
        fig_spark = go.Figure(go.Scatter(x=spark_df['time'], y=spark_df['close'], mode='lines', line=dict(color='#FFD700', width=1.5)))
        fig_spark.update_layout(height=50, margin=dict(l=0, r=0, t=0, b=0), xaxis=dict(visible=False), yaxis=dict(visible=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_spark, width='stretch', config={'displayModeBar': False})

st.divider()
st.subheader("🎯 План Действий (Резюме по бумагам)")
st.dataframe(df_plan[["Тикер", "Название", "Цена", "Z-Score", "Сигнал", "В портфеле", "Стоимость"]], width='stretch', hide_index=True)
st.divider()

# НИЖНЯЯ ЧАСТЬ: ГРАФИК И УПРАВЛЕНИЕ
sel = st.session_state.selected_ticker
sel_df = market_data[sel]
sel_info = df_plan[df_plan['Тикер'] == sel].iloc[0]

col_chart, col_controls = st.columns([2.5, 1])
with col_chart:
    st.subheader(f"График {sel} - 1H")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=sel_df['time'], open=sel_df['open'], high=sel_df['high'], low=sel_df['low'], close=sel_df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['upper_band'], line=dict(color='rgba(255, 82, 82, 0.5)', width=1, dash='dot'), name='Верхняя'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['lower_band'], line=dict(color='rgba(38, 166, 154, 0.5)', width=1, dash='dot'), name='Нижняя'))
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, b=0, t=0))
    st.plotly_chart(fig, width='stretch')

with col_controls:
    st.subheader("🎮 Управление")
    current_lot_size = instruments_map[sel]["lot"]
    current_pos = sel_info['В портфеле']
    
    st.info(f"1 лот = {current_lot_size} акций.")
    max_lots_to_sell = max(1, current_pos // current_lot_size)
    lots_to_trade = st.number_input("Кол-во лотов", min_value=1, max_value=max(100, max_lots_to_sell), value=1, step=1)
    
    estimated_cost = sel_info['Цена'] * current_lot_size * lots_to_trade
    st.write(f"Оценочно: **{estimated_cost:,.2f} RUB**")

    # Проверка статуса (защита от 30079)
    current_status = market.get_trading_status(instruments_map[sel]["figi"])
    if current_status != 'SECURITY_TRADING_STATUS_NORMAL_TRADING':
        st.warning(f"⚠️ Торги недоступны (Статус: {current_status})")
        c1_disabled, c2_disabled = True, True
    else:
        c1_disabled, c2_disabled = False, False

    c1, c2 = st.columns(2)
    if c1.button(f"🟢 КУПИТЬ", width='stretch', disabled=c1_disabled):
        p, q, s = executor.place_order(instruments_map[sel]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_BUY, qty_lots=lots_to_trade)
        if s == "FILLED":
            total_sum = q * current_lot_size * p
            msg = f"🛒 Ручная покупка {q} лот(ов) {sel} по {p:.2f} ₽ | Сумма: {total_sum:,.2f} ₽"
            add_log(msg)
            send_tg_alert(msg)
            st.cache_data.clear(); st.rerun()
        else:
            add_log(f"❌ Ошибка: {s}")

    if c2.button(f"🔴 ПРОДАТЬ", width='stretch', disabled=c2_disabled):
        if current_pos >= (lots_to_trade * current_lot_size):
            p, q, s = executor.place_order(instruments_map[sel]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=lots_to_trade)
            if s == "FILLED":
                total_sum = q * current_lot_size * p
                msg = f"💸 Ручная продажа {q} лот(ов) {sel} по {p:.2f} ₽ | Сумма: {total_sum:,.2f} ₽"
                add_log(msg)
                send_tg_alert(msg)
                st.cache_data.clear(); st.rerun()
        else:
            st.error("Недостаточно акций!")

    st.divider()
    st.subheader("📜 Логи операций")
    for log in reversed(st.session_state.logs):
        st.code(log, language="bash")

# АВТОПИЛОТ
if autopilot:
    for _, row in df_plan.iterrows():
        t, pos_count, price = row["Тикер"], row["В портфеле"], row["Цена"]
        last_z = market_data[t]['z_score'].iloc[-1]
        
        current_lot = instruments_map[t]["lot"]
        
        decision = orchestrator.decide_trade(
            ticker=t, last_z_score=last_z, news_text=news_text, 
            cash=cash, shares_count=pos_count, price=price, lot_size=current_lot 
        )
        
        if decision["action"] == "BUY":
            p, q, s = executor.place_order(instruments_map[t]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_BUY)
            if s == "FILLED":
                total_sum = q * current_lot * p
                msg = f"🤖 АВТОПИЛОТ КУПИЛ {q} лот(ов) {t} по {p:.2f} ₽ | Сумма: {total_sum:,.2f} ₽"
                add_log(msg)
                send_tg_alert(msg)
                st.cache_data.clear(); st.rerun()
                
        elif decision["action"] == "SELL":
            p, q, s = executor.place_order(instruments_map[t]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=pos_count // current_lot)
            if s == "FILLED":
                total_sum = q * current_lot * p
                msg = f"🤖 АВТОПИЛОТ ПРОДАЛ {q} лот(ов) {t} по {p:.2f} ₽ | Сумма: {total_sum:,.2f} ₽"
                add_log(msg)
                send_tg_alert(msg)
                st.cache_data.clear(); st.rerun()
                
        elif decision["action"] == "BLOCKED":
            add_log(f"🛡️ {t}: {decision['reason']}")