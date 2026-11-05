import streamlit as st
import pandas as pd
import json
import time

import mock_tbank_server
from mcp_guardrails import MCPTransactionValidator
from ml_filter import MLNoiseFilter
from quant_analysis import QuantSignalValidator

validator = MCPTransactionValidator()
nlp_filter = MLNoiseFilter()
quant_calc = QuantSignalValidator(window_size=5)

st.set_page_config(page_title="AI-Navigator", layout="wide")

if 'price_history' not in st.session_state:
    st.session_state.price_history = [138.0, 138.2, 137.9, 138.1, 138.0]
if 'trade_logs' not in st.session_state:
    st.session_state.trade_logs = []
if 'position' not in st.session_state:
    st.session_state.position = None
if 'cash' not in st.session_state:
    st.session_state.cash = 142500.0
if 'shares_count' not in st.session_state:
    st.session_state.shares_count = 50

# --- SIDEBAR CONTROL PANEL ---
st.sidebar.image("https://tinkoff.ru", width=120)
st.sidebar.title("Стенд")
selected_regime = st.sidebar.selectbox(
    "Сценарий:",
    ["Случайный (Авто)", "FLAT", "TREND_UP", "MARGIN_CALL", "CRASH"]
)

with open("regime.txt", "w", encoding="utf-8") as f:
    f.write(selected_regime)

st.sidebar.markdown("---")
auto_trade = st.sidebar.toggle("🤖 АВТОПИЛОТ РОБОТА", value=False)

# Считываем живую котировку из симулятора
market_packet = mock_tbank_server.get_market_data("GAZP")
current_price = market_packet["last_price"]
ticker = market_packet["ticker"]
market_regime = market_packet["market_regime"]
pulse_sample = market_packet["raw_news_feed"]

st.session_state.price_history.append(current_price)
if len(st.session_state.price_history) > 10:
    st.session_state.price_history.pop(0)

z_score = quant_calc.calculate_z_score(st.session_state.price_history[:-1], current_price)
nlp_analysis = nlp_filter.analyze_message(ticker, pulse_sample)

# --- ЛОГИКА АВТО-ВЫХОДА С АБСОЛЮТНО ПРАВИЛЬНЫМИ ОТСТУПАМИ ---
if auto_trade and st.session_state.position:
    p = st.session_state.position
    t_str = time.strftime('%H:%M:%S')
    
    if current_price >= p["tp"]:
        profit = round((current_price - p["entry"]) * 10, 2)
        st.session_state.cash += round(current_price * 10, 2)
        st.session_state.shares_count -= 10
        log_entry = f"[{t_str}] 🎯 PROFIT: SELL 10 {ticker} @ {current_price} (+{profit} R)"
        st.session_state.trade_logs.append(log_entry)
        st.session_state.position = None
        
    elif current_price <= p["sl"]:
        loss = round((p["entry"] - current_price) * 10, 2)
        st.session_state.cash += round(current_price * 10, 2)
        st.session_state.shares_count -= 10
        log_entry = f"[{t_str}] 🛡️ STOP: SELL 10 {ticker} @ {current_price} (-{loss} R)"
        st.session_state.trade_logs.append(log_entry)
        st.session_state.position = None

# Мониторинг кошелька
st.sidebar.metric("Доступный баланс", f"{st.session_state.cash:.2f} ₽")
st.sidebar.metric("Акций в портфеле", f"{st.session_state.shares_count} шт")
st.sidebar.metric(f"Цена {ticker}", f"{current_price} ₽", delta=str(f"{z_score:.2f} s"))

# --- MAIN TERMINAL ---
st.title("🤖 AI-Штурман Т-Инвестиций (Торговый Робот)")

col1, col2 = st.columns([1, 1.2])
with col1:
    st.subheader("📝 Скан Пульса моделью Qwen")
    st.info(f"Пост: {pulse_sample}")
    st.json(nlp_analysis)

with col2:
    st.subheader("📊 Сигналы и Управление Активами")
    
    if st.session_state.position:
        p = st.session_state.position
        st.warning(f"🎰 УДЕРЖАНИЕ: Вход: {p['entry']} | Цель: {p['tp']} | Стоп: {p['sl']}")
        
        if st.button("🚨 ЭКСТРЕННО ЗАКРЫТЬ ПОЗИЦИЮ (MARKET SELL)", type="primary"):
            profit = round((current_price - p["entry"]) * 10, 2)
            st.session_state.cash += round(current_price * 10, 2)
            st.session_state.shares_count -= 10
            t_str = time.strftime('%H:%M:%S')
            log_entry = f"[{t_str}] 🚨 МАРКЕТ-ВЫХОД: Продано 10 {ticker} @ {current_price} R (+{profit} R)"
            st.session_state.trade_logs.append(log_entry)
            st.session_state.position = None
            st.toast("Позиция экстренно закрыта по рынку!", icon="🚨")
            st.rerun()
    
    if z_score <= -1.5 and not nlp_analysis["fundamental"] and not st.session_state.position:
        st.success(f"🟢 СИГНАЛ: BUY (Z-Score: {z_score:.2f})")
        
        tp_level = round(current_price * 1.015, 2)
        sl_level = round(current_price * 0.992, 2)
        
        if auto_trade:
            st.session_state.cash -= round(current_price * 10, 2)
            st.session_state.shares_count += 10
            t_str = time.strftime('%H:%M:%S')
            log_entry = f"[{t_str}] 🛒 АВТО-ВХОД: BUY 10 {ticker} @ {current_price} ₽"
            st.session_state.trade_logs.append(log_entry)
            st.session_state.position = {"entry": current_price, "tp": tp_level, "sl": sl_level}
    
    elif nlp_analysis["fundamental"] and nlp_analysis["sentiment"] < 0:
        st.error("🔴 БЛОКИРОВКА: Фундаментальный негатив!")
    else:
        st.info("⚪ ИНДИКАТОР: HOLD (Сканирование рынка)")

    st.subheader("📜 Журнал баланса и торговых операций")
    if st.session_state.trade_logs:
        for log in reversed(st.session_state.trade_logs):
            st.code(log)
    else:
        st.caption("Журнал пуст. Включите тумблер Автопилота.")

if auto_trade:
    time.sleep(0.8)
    st.rerun()

