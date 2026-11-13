# Терминал: open -e dashboard.py
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

# ==============================================================================
# 🤖 ИМПОРТ МУЛЬТИ-АГЕНТНОЙ АРХИТЕКТУРЫ
# ==============================================================================
from market_agent import MarketAgent
from quant_agent import QuantAgent
from nlp_agent import NLPAgent
from risk_agent import RiskAgent
from execution_agent import ExecutionAgent
from orchestrator_agent import OrchestratorAgent # НАШ НОВЫЙ МОЗГ

warnings.filterwarnings("ignore")
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

st.set_page_config(page_title="AI-Navigator Terminal", layout="wide")
st.title("📈 AI-Штурман: Мульти-Агентный Терминал")

# ==============================================================================
# 🧠 ИНИЦИАЛИЗАЦИЯ АГЕНТОВ И СОСТОЯНИЙ
# ==============================================================================
if "logs" not in st.session_state: st.session_state.logs = []
if "selected_ticker" not in st.session_state: st.session_state.selected_ticker = "GAZP"

market = MarketAgent(TOKEN)
quant = QuantAgent() # Нужен для отрисовки графиков (расчет средних)
executor = ExecutionAgent(TOKEN)
orchestrator = OrchestratorAgent() # Вызывается для принятия торговых решений

# ==============================================================================
# 🛠️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (Telegram и Логи)
# ==============================================================================
def add_log(text):
    """Добавляет запись в системный лог терминала (виджет внизу)."""
    time_str = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{time_str}] {text}")
    if len(st.session_state.logs) > 10: st.session_state.logs.pop(0)

def send_tg_worker(text):
    """Фоновая функция отправки в ТГ. Фоновый поток спасает UI от зависания."""
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage?chat_id={TG_CHAT_ID}&text={urllib.parse.quote(text)}"
        requests.get(url, timeout=5)
    except Exception as e: print(f"TG Error: {e}")

def send_tg_alert(text):
    """Запускает отправку в отдельном потоке (threading)."""
    threading.Thread(target=send_tg_worker, args=(text,)).start()

# ==============================================================================
# 📊 СБОР ДАННЫХ И КЭШИРОВАНИЕ
# ==============================================================================
# TTL=60 секунд защищает нас от бана API (Rate Limits), если мы будем обновлять страницу.
TICKERS = {"GAZP": "Газпром", "SBER": "Сбербанк", "LKOH": "Лукойл", "YDEX": "Яндекс", "T": "Т-Технологии", "GMKN": "Норникель"}

@st.cache_data(ttl=60)
def get_market_data():
    # MarketAgent: Получаем баланс, позиции и FIGI
    cash, positions, acc_id = market.get_portfolio_and_account()
    figi_map = market.get_figi_map(TICKERS.keys())
    
    market_data = {}
    for t in TICKERS:
        if t in figi_map:
            df = market.get_candles(figi_map[t], days=7)
            if not df.empty:
                # QuantAgent: Считаем математику для графиков
                market_data[t] = quant.calculate_metrics(df)
    return market_data, figi_map, positions, cash, acc_id

with st.spinner("Агенты синхронизируются с биржей..."):
    market_data, figi_map, portfolio_positions, cash, acc_id = get_market_data()

if not market_data:
    st.error("Нет данных от API.")
    st.stop()

# ==============================================================================
# 🎯 СБОРКА ПЛАНА ДЕЙСТВИЙ (Action Plan)
# ==============================================================================
action_plan = []
total_equity = cash

for ticker, df in market_data.items():
    last_z = df['z_score'].iloc[-1]
    last_price = df['close'].iloc[-1]
    
    # Определяем текущий статус только для визуальной таблицы (без права торговать)
    signal_visual = quant.get_signal(last_z)
    
    pos_info = portfolio_positions.get(ticker, {"count": 0, "current_price": 0})
    pos_val = pos_info["count"] * last_price
    total_equity += pos_val
    
    action_plan.append({
        "Тикер": ticker, "Название": TICKERS[ticker], "Цена": round(last_price, 2),
        "Z-Score": round(last_z, 2) if pd.notna(last_z) else 0.0,
        "Сигнал": signal_visual, "В портфеле": pos_info["count"], "Стоимость": round(pos_val, 2)
    })

df_plan = pd.DataFrame(action_plan)

# ==============================================================================
# 🖥️ ЛЕВОЕ МЕНЮ (Сайдбар с Портфелем и Тумблером)
# ==============================================================================
with st.sidebar:
    st.header("💼 Ваш Портфель")
    st.metric("Общий Капитал (RUB)", f"{total_equity:,.2f}")
    st.metric("Свободный Кэш (RUB)", f"{cash:,.2f}")
    
    if st.button("💳 Пополнить на 100k", width='stretch'):
        with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
            client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
        st.cache_data.clear(); st.rerun()

    st.divider()
    
    st.markdown("### 🦾 Режим работы")
    # Главный глобальный тумблер
    autopilot = st.toggle("🤖 АВТОПИЛОТ (ВСЕ БУМАГИ)", value=False)
    if autopilot:
        st.success("Робот сканирует весь рынок")
    else:
        st.info("Ручной режим")

    st.divider()
    st.header("📜 Логи")
    for log in reversed(st.session_state.logs): 
        st.code(log, language="bash")

# ==============================================================================
# 🖥️ СКРИНЕР РЫНКА (Watchlist)
# ==============================================================================
st.subheader("📊 Скринер рынка (Агент: Quant)")
cols = st.columns(len(TICKERS))

for i, row in df_plan.iterrows():
    with cols[i]:
        color = "green" if row["Сигнал"] == "BUY" else ("red" if row["Сигнал"] == "SELL" else "gray")
        st.markdown(f"#### :{color}[{row['Тикер']}]")
        st.caption(row["Название"])
        st.write(f"**{row['Цена']} ₽** | Z: {row['Z-Score']}")
        
        # Спарклайн (мини-график) за 24 часа
        spark_df = market_data[row["Тикер"]].tail(24)
        fig_spark = go.Figure(go.Scatter(x=spark_df['time'], y=spark_df['close'], mode='lines', line=dict(color='#FFD700', width=2)))
        fig_spark.update_layout(height=80, margin=dict(l=0, r=0, t=0, b=0), xaxis=dict(visible=False), yaxis=dict(visible=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_spark, width='stretch', config={'displayModeBar': False})
        
        if st.button(f"Открыть {row['Тикер']}", key=f"btn_{row['Тикер']}", width='stretch'):
            st.session_state.selected_ticker = row['Тикер']
            st.rerun()

st.divider()

# ==============================================================================
# 📈 ДЕТАЛЬНЫЙ ГРАФИК
# ==============================================================================
sel = st.session_state.selected_ticker
sel_df = market_data[sel]
sel_info = df_plan[df_plan['Тикер'] == sel].iloc[0]

col_chart, col_ctrl = st.columns([3, 1])

with col_chart:
    st.subheader(f"График {sel} - 1H")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=sel_df['time'], open=sel_df['open'], high=sel_df['high'], low=sel_df['low'], close=sel_df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['upper_band'], line=dict(color='rgba(255, 82, 82, 0.5)', width=1, dash='dot'), name='Верхняя'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['lower_band'], line=dict(color='rgba(38, 166, 154, 0.5)', width=1, dash='dot'), name='Нижняя'))
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, b=0, t=0))
    st.plotly_chart(fig, width='stretch')

with col_ctrl:
    st.subheader("Управление")
    st.metric("Цена", f"{sel_info['Цена']} RUB")
    st.metric("Z-Score", f"{sel_info['Z-Score']} σ", delta=sel_info['Сигнал'])
    
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

# ==============================================================================
# 📋 ПЛАН ДЕЙСТВИЙ И ГЛАВНЫЙ АВТОПИЛОТ
# ==============================================================================
st.divider()
st.subheader("🎯 План Действий")
st.dataframe(df_plan[["Тикер", "Название", "Цена", "Z-Score", "Сигнал", "В портфеле", "Стоимость"]], width='stretch', hide_index=True)

# Логика глобального автопилота. Работает по всем бумагам.
if autopilot:
    for _, row in df_plan.iterrows():
        t, pos_count, price = row["Тикер"], row["В портфеле"], row["Цена"]
        last_z = market_data[t]['z_score'].iloc[-1]
        
        # В реальном проекте здесь был бы вызов LLM. Пока передаем заглушку.
        news_text = f"Новости по {t}: фон нейтральный"
        
        # ВЫЗЫВАЕМ ОРКЕСТРАТОРА ДЛЯ ПРИНЯТИЯ РЕШЕНИЯ
        decision = orchestrator.decide_trade(
            ticker=t, last_z_score=last_z, news_text=news_text, 
            cash=cash, shares_count=pos_count, price=price, lot_size=10
        )
        
        if decision["action"] == "BUY":
            p, q, s = executor.place_order(figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_BUY)
            if s == "FILLED":
                add_log(f"✅ ОРКЕСТРАТОР КУПИЛ {t} по {p:.2f}")
                send_tg_alert(f"🤖 Купил {t} по {p:.2f}")
                st.cache_data.clear(); st.rerun()
                
        elif decision["action"] == "SELL":
            p, q, s = executor.place_order(figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=pos_count)
            if s == "FILLED":
                add_log(f"✅ ОРКЕСТРАТОР ПРОДАЛ {t} по {p:.2f}")
                send_tg_alert(f"🤖 Продал {t} по {p:.2f}")
                st.cache_data.clear(); st.rerun()
                
        elif decision["action"] == "BLOCKED":
            # Если оркестратор заблокировал сделку, пишем причину в лог
            add_log(f"🛡️ {t}: {decision['reason']}")