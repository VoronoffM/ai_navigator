import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os
import warnings
import threading
import requests
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from t_tech.invest.schemas import OrderDirection, MoneyValue
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX

from market_agent import MarketAgent
from quant_agent import QuantAgent
from execution_agent import ExecutionAgent
from orchestrator_agent import OrchestratorAgent 

warnings.filterwarnings("ignore")
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")

st.set_page_config(page_title="AI-Штурман", layout="wide")
st.title("📈 AI-Штурман: Аналитический Терминал")

if "ai_report" not in st.session_state: st.session_state.ai_report = None
if "report_time" not in st.session_state: st.session_state.report_time = ""
if "selected_ticker" not in st.session_state: st.session_state.selected_ticker = "GAZP"

# ==============================================================================
# 🔥 АВТОМАТИЧЕСКИЙ ПРОГРЕВ НЕЙРОСЕТИ (В ФОНЕ)
# ==============================================================================
def warm_up_llm():
    try:
        url = "http://localhost:11434/api/generate"
        payload = {"model": "qwen2.5:3b", "prompt": "Привет", "stream": False}
        requests.post(url, json=payload, timeout=60)
        print("🔥 Нейросеть Qwen успешно прогрета и загружена в RAM.")
    except Exception as e:
        print(f"⚠️ Не удалось прогреть нейросеть: {e}")

if "llm_warmed_up" not in st.session_state:
    threading.Thread(target=warm_up_llm, daemon=True).start()
    st.session_state.llm_warmed_up = True

# ==============================================================================
# 🤖 КЭШИРОВАНИЕ АГЕНТОВ
# ==============================================================================
@st.cache_resource
def get_agents():
    market = MarketAgent(TOKEN)
    executor = ExecutionAgent(TOKEN)
    orchestrator = OrchestratorAgent()
    return market, executor, orchestrator

market, executor, orchestrator = get_agents()
quant = QuantAgent()

# ДОБАВЛЕНЫ ВТБ И ЦИАН
TICKERS = {
    "GAZP": "🔵 Газпром", "SBER": "🟢 Сбербанк", "LKOH": "🟡 Лукойл", 
    "YDEX": "🔴 Яндекс", "T": "🟣 Т-Технологии", "GMKN": "⚪ Норникель",
    "VTBR": "🟠 ВТБ", "CIAN": "🟤 Циан"
}

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

# ==============================================================================
# РАСЧЕТ ПОРТФЕЛЯ
# ==============================================================================
total_assets_value = 0 
total_equity = cash    
for ticker, df in market_data.items():
    last_price = df['close'].iloc[-1]
    pos_info = portfolio_positions.get(ticker, {"count": 0})
    pos_val = pos_info["count"] * last_price
    total_assets_value += pos_val
    total_equity += pos_val

# ==============================================================================
# ЛЕВОЕ МЕНЮ
# ==============================================================================
with st.sidebar:
    st.header("💼 Портфель")
    st.metric("Общий Капитал (RUB)", f"{total_equity:,.2f}")
    st.metric("Стоимость активов", f"{total_assets_value:,.2f}")
    st.metric("Свободный Кэш (RUB)", f"{cash:,.2f}")
    
    st.divider()
    st.markdown("### 🎯 Выбор актива")
    selected_ticker = st.radio(
        "Наблюдение:",
        list(TICKERS.keys()),
        format_func=lambda x: TICKERS[x],
        index=list(TICKERS.keys()).index(st.session_state.selected_ticker)
    )
    if selected_ticker != st.session_state.selected_ticker:
        st.session_state.selected_ticker = selected_ticker
        st.session_state.ai_report = None 
        st.rerun()

    st.divider()
    st.markdown("### 📰 Симуляция контекста")
    news_scenario = st.selectbox("Что произошло на рынке?", 
        ["Обычный день", "Паника толпы (Слухи)", "Фундаментальный негатив (Санкции)", 
         "Кейс: ВТБ (Дивидендный сюрприз)", "Кейс: Яндекс (События 2023)", "Кейс: Циан (Выкуп Т-Банком)"])
    
    if news_scenario == "Фундаментальный негатив (Санкции)":
        news_text = "Сбербанк попал под блокирующие санкции США."
    elif news_scenario == "Паника толпы (Слухи)":
        news_text = "В телеграм-каналах пишут, что все пропало, начинается паника!"
    elif news_scenario == "Кейс: ВТБ (Дивидендный сюрприз)":
        news_text = "ВТБ объявил неожиданно высокие дивиденды, рынок отреагировал резким ростом."
    elif news_scenario == "Кейс: Яндекс (События 2023)":
        news_text = "Яндекс столкнулся с геополитическими рисками и сменой контроля, акции упали."
    elif news_scenario == "Кейс: Циан (Выкуп Т-Банком)":
        news_text = "Т-Банк объявил о выкупе акций Циан, котировки отреагировали аномальным скачком."
    else:
        news_text = "Обычный торговый день, новостей нет."

# ==============================================================================
# ЦЕНТРАЛЬНАЯ ЧАСТЬ
# ==============================================================================
sel = st.session_state.selected_ticker
sel_df = market_data[sel]
last_z = sel_df['z_score'].iloc[-1]
last_price = sel_df['close'].iloc[-1]
current_lot_size = instruments_map[sel]["lot"]
current_pos = portfolio_positions.get(sel, {"count": 0})["count"]

col_chart, col_ai = st.columns([2, 1.2])

with col_chart:
    st.subheader(f"График {sel} (1H)")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=sel_df['time'], open=sel_df['open'], high=sel_df['high'], low=sel_df['low'], close=sel_df['close'], 
                                 increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
                                 increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)'))
    fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, b=0, t=0))
    st.plotly_chart(fig, width='stretch')

    st.info(f"Текущий Z-Score: {last_z:.2f} (Норма: от -1.5 до 1.5)")
    
    if st.button("🧠 Запустить ИИ-Анализ", width='stretch'):
        with st.spinner("Нейросеть анализирует контекст (на Intel Mac ~15 сек)..."):
            report = orchestrator.nlp.analyze_news(news_text, ticker=sel)
            st.session_state.ai_report = report
            st.session_state.report_time = datetime.now().strftime("%H:%M:%S МСК")
            st.rerun()

with col_ai:
    st.subheader("🤖 AI Navigator")
    
    if st.session_state.ai_report:
        rep = st.session_state.ai_report
        status = rep.get("status", "ERROR")
        
        if status == "ALLOW": st.success("✅ Снижение обнаружено. Фундаментальных рисков нет.")
        elif status == "BLOCK": st.error("❌ Обнаружены фундаментальные риски!")
        else: st.warning("⚠️ Ошибка анализа (Fail-Closed).")
            
        st.caption(f"Время завершения анализа: {st.session_state.report_time}")
        st.divider()
        
        st.markdown("**📌 Факты**")
        st.info(rep.get("facts", "Нет данных"))
        
        st.markdown("**💡 Возможные объяснения**")
        st.write(rep.get("explanations", "Нет данных"))
        
        st.markdown("**❓ Что не подтверждено**")
        st.warning(rep.get("unconfirmed", "Нет данных"))
        
        st.markdown("**🔗 Источники**")
        st.write(rep.get("sources", "Нет данных"))
        
        with st.expander("🛠️ Внутренний лог ИИ (Reasoning Trace)"):
            st.code(rep.get("reasoning_trace", "Нет данных"), language="text")
    else:
        st.info("Нажмите «Запустить ИИ-Анализ», чтобы получить сводку по текущей ситуации на рынке.")

# ==============================================================================
# СКРЫТЫЙ БЛОК РУЧНОЙ ТОРГОВЛИ
# ==============================================================================
st.divider()
with st.expander("🛠️ Ручная торговля (Режим тестирования, не для питча)"):
    st.write(f"Текущая позиция: {current_pos} шт. (1 лот = {current_lot_size} акций)")
    c1, c2 = st.columns(2)
    
    current_status = market.get_trading_status(instruments_map[sel]["figi"])
    if current_status != 'SECURITY_TRADING_STATUS_NORMAL_TRADING':
        st.warning(f"⚠️ Торги недоступны (Статус: {current_status})")
        c1_disabled, c2_disabled = True, True
    else:
        c1_disabled, c2_disabled = False, False

    if c1.button("🟢 КУПИТЬ", disabled=c1_disabled):
        p, q, s = executor.place_order(instruments_map[sel]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_BUY, qty_lots=1)
        if s == "FILLED": st.success(f"Куплено по {p:.2f}")
        
    if c2.button("🔴 ПРОДАТЬ", disabled=c2_disabled):
        if current_pos >= current_lot_size:
            p, q, s = executor.place_order(instruments_map[sel]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=1)
            if s == "FILLED": st.success(f"Продано по {p:.2f}")