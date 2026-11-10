import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import threading
import requests
import urllib.parse
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, OrderDirection, OrderType
from dotenv import load_dotenv

# 1. НАСТРОЙКИ ДЛЯ ОБХОДА VPN-ОШИБОК
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

st.set_page_config(page_title="AI-Navigator", layout="wide")
st.title("📈 AI-Штурман: Терминал")
st.markdown("Данные с реальной песочницы T-Invest API")

def get_price(q):
    return q.units + q.nano / 1e9

# 2. ОТПРАВКА В ТЕЛЕГРАМ (В ФОНЕ)
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

# 3. ЗАГРУЗКА ДАННЫХ
@st.cache_data(ttl=60)
def fetch_data(ticker="GAZP"):
    if not TOKEN:
        return pd.DataFrame(), None, None

    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        # Получаем счет для торговли
        accounts = client.users.get_accounts()
        acc_id = accounts.accounts[0].id if accounts.accounts else None

        shares = client.instruments.shares()
        figi = next((s.figi for s in shares.instruments if s.ticker == ticker), None)
        if not figi:
            return pd.DataFrame(), None, None

        now = datetime.utcnow()
        from_time = now - timedelta(days=3)

        candles = client.market_data.get_candles(
            figi=figi, from_=from_time, to=now,
            interval=CandleInterval.CANDLE_INTERVAL_5_MIN
        )

        data = []
        for c in candles.candles:
            data.append({
                "time": c.time, "open": get_price(c.open), "high": get_price(c.high),
                "low": get_price(c.low), "close": get_price(c.close), "volume": c.volume
            })
        return pd.DataFrame(data), figi, acc_id

df, figi, acc_id = fetch_data("GAZP")

if not df.empty:
    # МАТЕМАТИКА
    window = 20
    df['mean'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['z_score'] = (df['close'] - df['mean']) / df['std']
    df['upper_band'] = df['mean'] + (1.5 * df['std'])
    df['lower_band'] = df['mean'] - (1.5 * df['std'])
    
    last_z = df['z_score'].iloc[-1]
    last_price = df['close'].iloc[-1]
    
    # САЙДБАР
    with st.sidebar:
        st.header("Управление роботом")
        st.metric("Цена GAZP", f"{last_price:.2f} RUB")
        st.metric("Z-Score", f"{last_z:.2f} σ" if pd.notna(last_z) else "0.00 σ")
        
        signal = "HOLD"
        if pd.notna(last_z):
            if last_z <= -1.5:
                st.success("🟢 BUY (Перепроданность)")
                signal = "BUY"
            elif last_z >= 1.5:
                st.error("🔴 SELL (Перекупленность)")
                signal = "SELL"
            else:
                st.info("⚪ HOLD (Нейтрально)")

        st.divider()
        autopilot = st.toggle("🤖 АВТОПИЛОТ", value=False)
        
        if autopilot and signal != "HOLD":
            st.warning(f"АВТОПИЛОТ: Отправка ордера {signal}!")
            send_tg_alert(f"🤖 АВТОПИЛОТ: Сигнал {signal}! Цена: {last_price:.2f}")
            # Здесь в будущем будет реальная отправка ордера
        
        st.divider()
        st.subheader("Ручная торговля")
        
        # Кнопки вынесены из условий, чтобы всегда быть на экране
        col1, col2 = st.columns(2)
        if col1.button("🟢 КУПИТЬ", key="buy_btn"):
            with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                client.orders.post_order(
                    figi=figi, quantity=1, account_id=acc_id,
                    direction=OrderDirection.ORDER_DIRECTION_BUY,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )
            send_tg_alert(f"🛒 РУЧНАЯ ПОКУПКА: 1 лот GAZP по {last_price:.2f}")
            st.success("Куплено!")
        
        if col2.button("🔴 ПРОДАТЬ", key="sell_btn"):
            with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
                client.orders.post_order(
                    figi=figi, quantity=1, account_id=acc_id,
                    direction=OrderDirection.ORDER_DIRECTION_SELL,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )
            send_tg_alert(f"💸 РУЧНАЯ ПРОДАЖА: 1 лот GAZP по {last_price:.2f}")
            st.error("Продано!")

    # ГРАФИК
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350', name='Цена'
    ))
    fig.add_trace(go.Scatter(x=df['time'], y=df['mean'], line=dict(color='#FFD700', width=1), name='MA20'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['upper_band'], line=dict(color='rgba(255, 82, 82, 0.4)', width=1, dash='dash'), name='Верхняя'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['lower_band'], line=dict(color='rgba(38, 166, 154, 0.4)', width=1, dash='dash'), name='Нижняя'))

    buy_signals = df[df['z_score'] <= -1.5]
    fig.add_trace(go.Scatter(x=buy_signals['time'], y=buy_signals['low'] - 0.5, mode='markers', marker=dict(symbol='triangle-up', size=12, color='#26a69a'), name='BUY'))
    sell_signals = df[df['z_score'] >= 1.5]
    fig.add_trace(go.Scatter(x=sell_signals['time'], y=sell_signals['high'] + 0.5, mode='markers', marker=dict(symbol='triangle-down', size=12, color='#ef5350'), name='SELL'))

    fig.update_layout(template="plotly_dark", height=650, xaxis_rangeslider_visible=False, title="График GAZP + Z-Score")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Нет данных для отображения")