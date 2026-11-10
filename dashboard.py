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
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, OrderDirection, OrderType, MoneyValue
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from ml_filter import MLNoiseFilter

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

nlp = MLNoiseFilter()

if "logs" not in st.session_state:
    st.session_state.logs = []

def add_log(text):
    time_str = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{time_str}] {text}")
    if len(st.session_state.logs) > 10:
        st.session_state.logs.pop(0)

def get_price(q):
    return q.units + q.nano / 1e9

def send_tg_worker(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    safe_text = urllib.parse.quote(text)
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage?chat_id={TG_CHAT_ID}&text={safe_text}"
    try:
        requests.get(url, timeout=5)
    except Exception as e:
        print(f"TG Error: {e}")

def send_tg_alert(text):
    threading.Thread(target=send_tg_worker, args=(text,)).start()

@st.cache_data(ttl=15)
def fetch_data_and_portfolio(ticker="GAZP"):
    if not TOKEN:
        return pd.DataFrame(), None, None, 0, 0

    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        accounts = client.users.get_accounts()
        if not accounts.accounts:
            client.sandbox.open_sandbox_account()
            accounts = client.users.get_accounts()
            acc_id = accounts.accounts[0].id
            client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
        else:
            acc_id = accounts.accounts[0].id

        portfolio = client.operations.get_portfolio(account_id=acc_id)
        cash = 0
        shares_count = 0
        
        for pos in portfolio.positions:
            if pos.instrument_type == "currency" and pos.figi == "RUB000UTSTOM":
                cash = pos.quantity.units
            if ticker in str(pos.ticker):
                shares_count = pos.quantity.units

        shares = client.instruments.shares()
        figi = next((s.figi for s in shares.instruments if s.ticker == ticker), None)
        
        if not figi:
            return pd.DataFrame(), None, acc_id, cash, shares_count

        now = datetime.utcnow()
        from_time = now - timedelta(days=1) 
        candles = client.market_data.get_candles(figi=figi, from_=from_time, to=now, interval=CandleInterval.CANDLE_INTERVAL_5_MIN)

        data = []
        for c in candles.candles:
            data.append({"time": c.time, "open": get_price(c.open), "high": get_price(c.high), "low": get_price(c.low), "close": get_price(c.close), "volume": c.volume})
        return pd.DataFrame(data), figi, acc_id, cash, shares_count

def place_order(client, figi, acc_id, direction, qty=1):
    client.orders.post_order(instrument_id=figi, quantity=qty, account_id=acc_id, direction=direction, order_type=OrderType.ORDER_TYPE_MARKET)

df, figi, acc_id, cash, shares_count = fetch_data_and_portfolio("GAZP")

if not df.empty:
    window = 20
    df['mean'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['z_score'] = (df['close'] - df['mean']) / df['std']
    df['upper_band'] = df['mean'] + (1.5 * df['std'])
    df['lower_band'] = df['mean'] - (1.5 * df['std'])
    
    last_z = df['z_score'].iloc[-1]
    last_price = df['close'].iloc[-1]
    
    with st.sidebar:
        st.header("Портфель")
        st.metric("Кэш (RUB)", f"{cash:,.2f}")
        st.metric("Акции GAZP", f"{shares_count} шт.")
        
        if st.button("💳 Пополнить на 100 000 RUB"):
            with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
            st.cache_data.clear()
            st.rerun()
            
        # КНОПКА СБРОСА ПОРТФЕЛЯ ДЛЯ ДЕМО
        if shares_count > 0:
            if st.button("🗑️ Продать все акции (Сброс)"):
                with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                    place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty=shares_count)
                add_log(f"🗑️ Портфель сброшен, продано {shares_count} акций.")
                st.cache_data.clear()
                st.rerun()

        st.divider()
        st.header("Робот")
        st.metric("Цена GAZP", f"{last_price:.2f} RUB")
        st.metric("Z-Score", f"{last_z:.2f} σ" if pd.notna(last_z) else "0.00 σ")
        
        signal = "HOLD"
        if pd.notna(last_z):
            if last_z <= -1.5:
                signal = "BUY"
            elif last_z >= 1.5:
                signal = "SELL"

        force_buy = st.toggle("🧪 Принудительный сигнал BUY (Тест)", value=False)
        if force_buy:
            signal = "BUY"
            st.warning("🧪 СИМУЛЯЦИЯ: Робот видит аномалию -1.5σ!")
        else:
            if signal == "BUY": st.success("🟢 BUY (Реальная перепроданность)")
            elif signal == "SELL": st.error("🔴 SELL (Реальная перекупленность)")
            else: st.info("⚪ HOLD (Нейтрально)")

        st.divider()
        st.header("📰 Новостной фон")
        news_scenario = st.selectbox("Симуляция новостей Пульса:", ["Нейтрально", "Паника толпы", "Фундаментальный негатив"])
        
        if news_scenario == "Нейтрально":
            news_text = "Обычный торговый день."
        elif news_scenario == "Паника толпы":
            news_text = "На бирже паника, все сливают, маржин коллы!"
        else:
            news_text = "Газпром отменил дивиденды, санкции!"
            
        nlp_result = nlp.analyze_message("GAZP", news_text)
        if nlp_result["fundamental"]: st.error(f"NLP: {nlp_result['reason']}")
        elif nlp_result["sentiment"] < 0: st.warning(f"NLP: {nlp_result['reason']}")
        else: st.info(f"NLP: {nlp_result['reason']}")

        st.divider()
        autopilot = st.toggle("🤖 АВТОПИЛОТ", value=False)
        
        # УЛУЧШЕННАЯ ЛОГИКА АВТОПИЛОТА
        if autopilot and figi and acc_id:
            if signal == "BUY":
                if shares_count > 0:
                    # Не спамим логами, если уже в позиции
                    pass 
                elif nlp_result["fundamental"]:
                    # Робот заблокирован NLP
                    if not st.session_state.logs or "❌ NLP заблокировал" not in st.session_state.logs[-1]:
                        add_log("❌ NLP заблокировал покупку: фундаментальный негатив!")
                else:
                    # Покупаем
                    try:
                        with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                            place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_BUY)
                        msg = f"АВТОПИЛОТ КУПИЛ (NLP одобрил) по {last_price:.2f}"
                        send_tg_alert(f"🤖 {msg}")
                        add_log(f"✅ {msg}")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        add_log(f"❌ Ошибка: {e}")
                    
            elif signal == "SELL" and shares_count > 0:
                try:
                    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                        place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_SELL)
                    msg = f"АВТОПИЛОТ ПРОДАЛ по {last_price:.2f}"
                    send_tg_alert(f"🤖 {msg}")
                    add_log(f"✅ {msg}")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    add_log(f"❌ Ошибка: {e}")
        
        st.divider()
        st.subheader("Ручная торговля")
        
        if not figi or not acc_id:
            st.error("❌ Нет данных: проверь создан ли счет.")
        else:
            col1, col2 = st.columns(2)
            if col1.button("🟢 КУПИТЬ", key="buy_btn"):
                try:
                    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                        place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_BUY)
                    send_tg_alert(f"🛒 ПОКУПКА вручную по {last_price:.2f}")
                    add_log(f"🛒 Куплено вручную по {last_price:.2f}")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    add_log(f"❌ Ошибка покупки: {e}")
            
            if col2.button("🔴 ПРОДАТЬ", key="sell_btn"):
                try:
                    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                        place_order(client, figi, acc_id, OrderDirection.ORDER_DIRECTION_SELL)
                    send_tg_alert(f"💸 ПРОДАЖА вручную по {last_price:.2f}")
                    add_log(f"💸 Продано вручную по {last_price:.2f}")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    add_log(f"❌ Ошибка продажи: {e}")

    # ГРАФИК
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)', name='Цена'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['upper_band'], line=dict(color='rgba(255, 82, 82, 0.5)', width=1, dash='dot'), name='Верхняя'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['lower_band'], line=dict(color='rgba(38, 166, 154, 0.5)', width=1, dash='dot'), name='Нижняя'))
    buy_signals = df[df['z_score'] <= -1.5]
    fig.add_trace(go.Scatter(x=buy_signals['time'], y=buy_signals['low'] - 0.2, mode='markers', marker=dict(symbol='triangle-up', size=10, color='#26a69a'), name='BUY'))
    sell_signals = df[df['z_score'] >= 1.5]
    fig.add_trace(go.Scatter(x=sell_signals['time'], y=sell_signals['high'] + 0.2, mode='markers', marker=dict(symbol='triangle-down', size=10, color='#ef5350'), name='SELL'))
    fig.update_layout(template="plotly_dark", height=550, xaxis_rangeslider_visible=False, title="График GAZP (5 мин) за последние 24 часа")
    
    if len(df) > 50:
        fig.update_xaxes(range=[df['time'].iloc[-50], df['time'].iloc[-1]])

    st.plotly_chart(fig, width='stretch')

    st.divider()
    st.subheader("📜 Системный лог робота")
    if not st.session_state.logs:
        st.info("Робот работает. Ожидание сигналов или ручных действий...")
    else:
        for log in reversed(st.session_state.logs):
            st.code(log, language="bash")
else:
    st.warning("Нет данных для отображения")