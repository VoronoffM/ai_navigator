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
# Мы разделили логику на независимые модули (Агенты). Это позволяет тестировать
# их отдельно (через qa_agent.py) и менять один, не ломая другие.
from market_agent import MarketAgent      # Загружает котировки и портфель
from quant_agent import QuantAgent        # Считает математику (Z-Score)
from nlp_agent import NLPAgent            # Анализирует новости (AI)
from risk_agent import RiskAgent          # Проверяет лимиты и безопасность
from execution_agent import ExecutionAgent # Отправляет заявки брокеру

# ==============================================================================
# ⚙️ ИНИЦИАЛИЗАЦИЯ ОКРУЖЕНИЯ (ФИКСЫ СЕТИ И ТОКЕНОВ)
# ==============================================================================
warnings.filterwarnings("ignore") # Убираем мусорные предупреждения из консоли

# ФИКС БАГА VPN: Без этих строк Т-Банк не работает при включенном VPN (потеря DNS)
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# Настройка страницы Streamlit (расширяем на весь экран)
st.set_page_config(page_title="AI-Navigator Terminal", layout="wide")
st.title("📈 AI-Штурман: Мульти-Агентный Терминал")

# ==============================================================================
# 🧠 ИНИЦИАЛИЗАЦИЯ АГЕНТОВ И СОСТОЯНИЙ СЕССИИ
# ==============================================================================
# Streamlit перезапускает скрипт при каждом клике. session_state сохраняет 
# данные (логи, выбранный тикер) между этими перезапусками.
if "logs" not in st.session_state: st.session_state.logs = []
if "selected_ticker" not in st.session_state: st.session_state.selected_ticker = "GAZP"

market = MarketAgent(TOKEN)
quant = QuantAgent()
nlp = NLPAgent()
risk = RiskAgent()
executor = ExecutionAgent(TOKEN)

# ==============================================================================
# 🛠️ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (Логирование и Telegram)
# ==============================================================================
def add_log(text):
    """Добавляет запись в системный лог терминала."""
    time_str = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append(f"[{time_str}] {text}")
    if len(st.session_state.logs) > 10: st.session_state.logs.pop(0)

def send_tg_worker(text):
    """Фоновая функция для отправки сообщений в Телеграм (чтобы не вешать интерфейс)."""
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage?chat_id={TG_CHAT_ID}&text={urllib.parse.quote(text)}"
        requests.get(url, timeout=5)
    except Exception as e: print(f"TG Error: {e}")

def send_tg_alert(text):
    """Запускает отправку в отдельном потоке."""
    threading.Thread(target=send_tg_worker, args=(text,)).start()

# ==============================================================================
# 📊 СБОР ДАННЫХ И МАТЕМАТИКА (Вызов Агентов)
# ==============================================================================
# Список бумаг для сканера рынка. В будущем можно вынести в базу данных.
TICKERS = {"GAZP": "Газпром", "SBER": "Сбербанк", "LKOH": "Лукойл", "YDEX": "Яндекс", "T": "Т-Технологии", "GMKN": "Норникель"}

# @st.cache_data(ttl=60) — Кэшируем данные на 60 секунд. Это защита от 
# превышения лимитов API Т-Банка (Rate Limits), чтобы не забанили токен.
@st.cache_data(ttl=60)
def get_market_data():
    # 1. MarketAgent: Узнаем баланс, портфель и FIGI (ID) инструментов
    cash, positions, acc_id = market.get_portfolio_and_account()
    figi_map = market.get_figi_map(TICKERS.keys())
    
    market_data = {}
    for t in TICKERS:
        if t in figi_map:
            # 2. MarketAgent: Качаем часовые свечи за 7 дней
            df = market.get_candles(figi_map[t], days=7)
            if not df.empty:
                # 3. QuantAgent: Считаем Z-Score и скользящие средние
                market_data[t] = quant.calculate_metrics(df)
    return market_data, figi_map, positions, cash, acc_id

with st.spinner("Агенты синхронизируются с биржей..."):
    market_data, figi_map, portfolio_positions, cash, acc_id = get_market_data()

if not market_data:
    st.error("Нет данных от API.")
    st.stop()

# ==============================================================================
# 🎯 ФОРМИРОВАНИЕ ПЛАНА ДЕЙСТВИЙ (Action Plan)
# ==============================================================================
action_plan = []
total_equity = cash

for ticker, df in market_data.items():
    last_z = df['z_score'].iloc[-1]
    last_price = df['close'].iloc[-1]
    
    # 4. QuantAgent: Получаем вердикт (BUY / SELL / HOLD) на основе Z-Score
    signal = quant.get_signal(last_z)
    
    pos_info = portfolio_positions.get(ticker, {"count": 0, "current_price": 0})
    pos_val = pos_info["count"] * last_price
    total_equity += pos_val # Считаем общий капитал (Кэш + Стоимость акций)
    
    action_plan.append({
        "Тикер": ticker, "Название": TICKERS[ticker], "Цена": round(last_price, 2),
        "Z-Score": round(last_z, 2) if pd.notna(last_z) else 0.0,
        "Сигнал": signal, "В портфеле": pos_info["count"], "Стоимость": round(pos_val, 2)
    })

df_plan = pd.DataFrame(action_plan)

# ==============================================================================
# 🖥️ ИНТЕРФЕЙС: ЛЕВОЕ МЕНЮ (Сайдбар)
# ==============================================================================
with st.sidebar:
    st.header("💼 Ваш Портфель")
    st.metric("Общий Капитал (RUB)", f"{total_equity:,.2f}")
    st.metric("Свободный Кэш (RUB)", f"{cash:,.2f}")
    
    # Кнопка пополнения виртуального счета в песочнице
    if st.button("💳 Пополнить на 100k", width='stretch'):
        with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
            client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
        st.cache_data.clear(); st.rerun()

    st.divider()
    
    # ГЛАВНЫЙ ТУМБЛЕР: Включает глобального бота, который сканирует ВСЕ бумаги
    st.markdown("### 🦾 Режим работы")
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
# 🖥️ ИНТЕРФЕЙС: СКРИНЕР РЫНКА (Watchlist со спарклайнами)
# ==============================================================================
st.subheader("📊 Скринер рынка (Агент: Quant)")
cols = st.columns(len(TICKERS))

for i, row in df_plan.iterrows():
    with cols[i]:
        # Красим тикер в зависимости от сигнала
        color = "green" if row["Сигнал"] == "BUY" else ("red" if row["Сигнал"] == "SELL" else "gray")
        st.markdown(f"#### :{color}[{row['Тикер']}]")
        st.caption(row["Название"])
        st.write(f"**{row['Цена']} ₽** | Z: {row['Z-Score']}")
        
        # Рисуем мини-график (Sparkline) за последние 24 часа
        spark_df = market_data[row["Тикер"]].tail(24)
        fig_spark = go.Figure(go.Scatter(x=spark_df['time'], y=spark_df['close'], mode='lines', line=dict(color='#FFD700', width=2)))
        fig_spark.update_layout(height=80, margin=dict(l=0, r=0, t=0, b=0), xaxis=dict(visible=False), yaxis=dict(visible=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_spark, width='stretch', config={'displayModeBar': False})
        
        # Кнопка выбора этой бумаги для детального графика
        if st.button(f"Открыть {row['Тикер']}", key=f"btn_{row['Тикер']}", width='stretch'):
            st.session_state.selected_ticker = row['Тикер']
            st.rerun()

st.divider()

# ==============================================================================
# 📈 ДЕТАЛЬНЫЙ ГРАФИК И РУЧНАЯ ТОРГОВЛЯ
# ==============================================================================
sel = st.session_state.selected_ticker
sel_df = market_data[sel]
sel_info = df_plan[df_plan['Тикер'] == sel].iloc[0]

col_chart, col_ctrl = st.columns([3, 1])

with col_chart:
    st.subheader(f"График {sel} - 1H")
    fig = go.Figure()
    # Свечи (полые для читаемости)
    fig.add_trace(go.Candlestick(x=sel_df['time'], open=sel_df['open'], high=sel_df['high'], low=sel_df['low'], close=sel_df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)'))
    # Линии Боллинджера (границы волатильности)
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
    
    # 5. ExecutionAgent: Ручная покупка
    if c1.button(f"🟢 КУПИТЬ", width='stretch'):
        p, q, s = executor.place_order(figi_map[sel], acc_id, OrderDirection.ORDER_DIRECTION_BUY)
        if s == "FILLED":
            add_log(f"🛒 Куплено {q} лотов {sel} по {p:.2f}")
            send_tg_alert(f"🛒 Ручная покупка {sel} по {p:.2f}")
            st.cache_data.clear(); st.rerun()
        else:
            add_log(f"❌ Ошибка: {s}")

    # 5. ExecutionAgent: Ручная продажа
    if c2.button(f"🔴 ПРОДАТЬ", width='stretch'):
        if sel_info['В портфеле'] > 0:
            p, q, s = executor.place_order(figi_map[sel], acc_id, OrderDirection.ORDER_DIRECTION_SELL, sel_info['В портфеле'])
            if s == "FILLED":
                add_log(f"💸 Продано {q} лотов {sel} по {p:.2f}")
                send_tg_alert(f"💸 Ручная продажа {sel} по {p:.2f}")
                st.cache_data.clear(); st.rerun()

# ==============================================================================
# 📋 ПЛАН ДЕЙСТВИЙ И АВТОПИЛОТ (ГЛОБАЛЬНЫЙ ЦИКЛ)
# ==============================================================================
st.divider()
st.subheader("🎯 План Действий")
st.dataframe(df_plan[["Тикер", "Название", "Цена", "Z-Score", "Сигнал", "В портфеле", "Стоимость"]], width='stretch', hide_index=True)

# Если тумблер в Сайдбаре включен, запускается цикл по ВСЕМ бумагам
if autopilot:
    for _, row in df_plan.iterrows():
        t, sig, pos_count = row["Тикер"], row["Сигнал"], row["В портфеле"]
        
        # Логика покупки
        if sig == "BUY" and pos_count == 0:
            # 6. RiskAgent: Проверяем, хватает ли денег и не открыта ли позиция
            is_safe, msg = risk.validate_buy_order(cash, 0, row["Цена"], 10)
            if is_safe:
                # 7. NLPAgent: (В будущем здесь будет проверка новостей Георгия)
                nlp_res = nlp.analyze_news(f"Новости по {t}: фон нейтральный")
                if nlp_res["allow_trade"]:
                    # 8. ExecutionAgent: Отправляем заявку
                    p, q, s = executor.place_order(figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_BUY)
                    if s == "FILLED":
                        add_log(f"✅ АВТОПИЛОТ КУПИЛ {t} по {p:.2f}")
                        send_tg_alert(f"🤖 Купил {t} по {p:.2f}")
                        st.cache_data.clear(); st.rerun()
                else:
                    add_log(f"❌ NLP блокировал вход в {t}: {nlp_res['reason']}")

        # Логика продажи
        elif sig == "SELL" and pos_count > 0:
            # 9. RiskAgent: Проверяем, есть ли что продавать
            is_safe, msg = risk.validate_sell_order(pos_count, 10)
            if is_safe:
                p, q, s = executor.place_order(figi_map[t], acc_id, OrderDirection.ORDER_DIRECTION_SELL, pos_count)
                if s == "FILLED":
                    add_log(f"✅ АВТОПИЛОТ ПРОДАЛ {t} по {p:.2f}")
                    send_tg_alert(f"🤖 Продал {t} по {p:.2f}")
                    st.cache_data.clear(); st.rerun()