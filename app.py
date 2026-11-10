import streamlit as st
import pandas as pd
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import threading

import mock_tbank_server
from mcp_guardrails import MCPTransactionValidator
from quant_analysis import QuantSignalValidator

validator = MCPTransactionValidator()
quant_calc = QuantSignalValidator(window_size=5)

st.set_page_config(page_title="AI-Navigator", layout="wide")

if 'price_history' not in st.session_state:
    st.session_state.price_history = []
if 'trade_logs' not in st.session_state:
    st.session_state.trade_logs = []
if 'position' not in st.session_state:
    st.session_state.position = None
if 'cash' not in st.session_state:
    st.session_state.cash = 142500.0
if 'shares_count' not in st.session_state:
    st.session_state.shares_count = 50
if 'tg_status' not in st.session_state:
    st.session_state.tg_status = "Ожидание старта"

# Асинхронная отправка, чтобы робот никогда не зависал
def send_tg_alert_worker(text):
    # !!! СЮДА НАДО ВСТАВИТЬ НАСТОЯЩИЙ ТОКЕН ИЗ BOTFATHER (МНОГО ЦИФР И БУКВ) !!!
    token = "mtbn_bot"
    chat_id = "166589831"
    
    safe_text = urllib.parse.quote(text)
    # ИСПРАВЛЕНО: Правильный базовый URL шлюза Telegram API
    url = f"https://telegram.org{token}/sendMessage?chat_id={chat_id}&text={safe_text}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as r:
            res = json.loads(r.read().decode())
            if res.get("ok"):
                st.session_state.tg_status = "✅ Сигнал в Telegram ушёл!"
            else:
                st.session_state.tg_status = f"❌ Ошибка: {res}"
    except Exception as e:
        st.session_state.tg_status = f"❌ Сетевой сбой: {str(e)}"

def send_tg_alert(text):
    threading.Thread(target=send_tg_alert_worker, args=(text,)).start()

st.sidebar.title("Управление")
selected_regime = st.sidebar.selectbox(
    "Сценарий рынка:",
    ["Случайный (Авто)", "FLAT", "TREND_UP", "MARGIN_CALL", "CRASH"]
)

with open("regime.txt", "w", encoding="utf-8") as f:
    f.write(selected_regime)

auto_trade = st.sidebar.toggle("🤖 АВТОПИЛОТ РОБОТА", value=False)

market_packet = mock_tbank_server.get_market_data("GAZP")
current_price = market_packet["last_price"]
ticker = market_packet["ticker"]
market_regime = market_packet["market_regime"]
pulse_sample = market_packet["raw_news_feed"]

st.session_state.price_history.append(current_price)
if len(st.session_state.price_history) > 10:
    st.session_state.price_history.pop(0)

z_score = quant_calc.calculate_z_score(st.session_state.price_history[:-1], current_price)

if auto_trade and st.session_state.position:
    p = st.session_state.position
    t_str = time.strftime('%H:%M:%S')
    
    if current_price >= p["tp"]:
        profit = round((current_price - p["entry"]) * 10, 2)
        st.session_state.cash += round(current_price * 10, 2)
        st.session_state.shares_count -= 10
        st.session_state.trade_logs.append(f"[{t_str}] 🎯 PROFIT: +{profit} ₽")
        st.session_state.position = None
        send_tg_alert(f"🎯 PROFIT! Продано 10 {ticker} по {current_price}")
        
    elif current_price <= p["sl"]:
        loss = round((p["entry"] - current_price) * 10, 2)
        st.session_state.cash += round(current_price * 10, 2)
        st.session_state.shares_count -= 10
        st.session_state.trade_logs.append(f"[{t_str}] 🛡️ STOP: -{loss} ₽")
        st.session_state.position = None
        send_tg_alert(f"🛡️ СТОП-ЛОСС! Закрыто по {current_price}")

st.sidebar.metric("Баланс кошелька", f"{st.session_state.cash:.2f} ₽")
st.sidebar.metric("Акций в портфеле", f"{st.session_state.shares_count} шт")
st.sidebar.metric(f"Цена {ticker}", f"{current_price} ₽", delta=f"{z_score:.2f} σ")

st.title("🤖 AI-Штурман Т-Инвестиций")

col1, col2 = st.columns(2)
with col1:
    st.subheader("📝 Мониторинг рынка")
    st.info(f"Пост Пульса: {pulse_sample}")
    st.warning(f"Контур Telegram: {st.session_state.tg_status}")

with col2:
    st.subheader("📊 Управление позициями")
    
    if st.session_state.position:
        p = st.session_state.position
        st.warning(f"🎰 УДЕРЖАНИЕ: Вход: {p['entry']} ₽ | Тейк: {p['tp']} | Стоп: {p['sl']}")
    
    if z_score <= -1.5 and not st.session_state.position:
        st.success(f"🟢 СИГНАЛ BUY (Z-Score: {z_score:.2f})")
        if auto_trade:
            st.session_state.cash -= round(current_price * 10, 2)
            st.session_state.shares_count += 10
            t_str = time.strftime('%H:%M:%S')
            st.session_state.trade_logs.append(f"[{t_str}] 🛒 BUY 10 @ {current_price} ₽")
            # Строки укорочены, разрывы исключены
            tp_l = round(current_price * 1.015, 2)
            sl_l = round(current_price * 0.992, 2)
            st.session_state.position = {"entry": current_price, "tp": tp_l, "sl": sl_l}
            send_tg_alert(f"🟢 BUY! Куплено 10 {ticker} по {current_price} руб.")
            st.rerun()
    else:
        st.info("⚪ ИНДИКАТОР: HOLD")

    st.subheader("📜 Логи операций")
    if st.session_state.trade_logs:
        for log in reversed(st.session_state.trade_logs):
            st.code(log)

if auto_trade:
    time.sleep(1.0)
    st.rerun()

