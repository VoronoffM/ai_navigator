import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import httpx
import os
import warnings
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv

from market_agent import MarketAgent
from quant_agent import QuantAgent
from execution_agent import ExecutionAgent
from orchestrator_agent import OrchestratorAgent
from t_tech.invest.schemas import OrderDirection, MoneyValue, CandleInterval
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX

warnings.filterwarnings("ignore")
os.environ["GRPC_DNS_RESOLVER"] = "native"
os.environ["SSL_TBANK_VERIFY"] = "True"

load_dotenv()
TOKEN = os.getenv("TBANK_TOKEN")
BACKEND_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="AI-Штурман", layout="wide")
st.title("📈 AI-Штурман: Терминал трейдера")

if "ai_report" not in st.session_state: st.session_state.ai_report = None
if "report_time" not in st.session_state: st.session_state.report_time = ""
if "selected_ticker" not in st.session_state: st.session_state.selected_ticker = "GAZP"
if "app_mode" not in st.session_state: st.session_state.app_mode = "Живой Рынок"

@st.cache_resource
def get_agents():
    market = MarketAgent(TOKEN)
    executor = ExecutionAgent(TOKEN)
    orchestrator = OrchestratorAgent()
    return market, executor, orchestrator

market, executor, orchestrator = get_agents()
quant = QuantAgent()

TICKERS = {
    "GAZP": "🔵 Газпром", "SBER": "🟢 Сбербанк", "LKOH": "🟡 Лукойл", 
    "YDEX": "🔴 Яндекс", "T": "🟣 Т-Технологии", "GMKN": "⚪ Норникель",
    "VTBR": "🟠 ВТБ", "CIAN": "🟤 Циан", "BELU": "🟢 Novabev"
}

@st.cache_data(ttl=60)
def get_market_data():
    try:
        cash, positions, acc_id = market.get_portfolio_and_account()
        instruments_map = market.get_instruments_info(TICKERS.keys()) 
        market_data = {}
        for t in TICKERS:
            if t in instruments_map:
                df = market.get_candles(instruments_map[t]["figi"], days=7)
                if not df.empty:
                    market_data[t] = quant.calculate_metrics(df)
        return market_data, instruments_map, positions, cash, acc_id
    except Exception as e:
        return {}, {}, {}, 0, None

with st.spinner("Синхронизация с биржей..."):
    market_data, instruments_map, portfolio_positions, cash, acc_id = get_market_data()

def api_call(endpoint, method="GET", json_data=None):
    try:
        with httpx.Client(timeout=15) as client:
            if method == "GET":
                r = client.get(f"{BACKEND_URL}{endpoint}")
            else:
                r = client.post(f"{BACKEND_URL}{endpoint}", json=json_data)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}

total_assets_value = 0 
total_equity = cash    
for ticker, df in market_data.items():
    last_price = df['close'].iloc[-1]
    pos_info = portfolio_positions.get(ticker, {"count": 0})
    pos_val = pos_info["count"] * last_price
    total_assets_value += pos_val
    total_equity += pos_val

# ==============================================================================
# ЛЕВОЕ МЕНЮ (ГЛАВНЫЙ ПЕРЕКЛЮЧАТЕЛЬ РЕЖИМОВ)
# ==============================================================================
with st.sidebar:
    # 1. Выбор режима работы
    st.radio("Режим работы:", ["Живой Рынок", "MCP-Тест (Исторические кейсы)"], key="app_mode")
    st.divider()

    # 2. Интерфейс для Живого Рынка
    if st.session_state.app_mode == "Живой Рынок":
        st.header("💼 Портфель")
        st.metric("Общий Капитал", f"{total_equity:,.2f} ₽")
        st.metric("Стоимость активов", f"{total_assets_value:,.2f} ₽")
        st.metric("Свободный Кэш", f"{cash:,.2f} ₽")
        
        st.divider()
        st.markdown("### 🎯 Выбор актива")
        selected_ticker = st.radio(
            "Наблюдение:",
            list(TICKERS.keys()),
            format_func=lambda x: TICKERS[x],
            index=list(TICKERS.keys()).index(st.session_state.selected_ticker),
            key="ticker_radio"
        )
        if selected_ticker != st.session_state.selected_ticker:
            st.session_state.selected_ticker = selected_ticker
            st.session_state.ai_report = None 
            st.rerun()

        st.divider()
        st.markdown("### 📰 Симуляция новостей (Live)")
        
        # В Живом Рынке оставляем только базовые новости, без кейсов Саши!
        news_scenario = st.selectbox("Контекст:", 
            ["Обычный день", "Паника толпы (Слухи)", "Фундаментальный негатив (Санкции)"])
        
        if news_scenario == "Фундаментальный негатив (Санкции)": 
            news_text = "Сбербанк попал под блокирующие санкции США."
        elif news_scenario == "Паника толпы (Слухи)": 
            news_text = "В телеграм-каналах пишут, что все пропало, начинается паника!"
        else: 
            news_text = "Обычный торговый день, новостей нет."

        if st.button("🧠 Анализировать новости (Qwen)", width='stretch', type="primary"):
            with st.spinner("Qwen анализирует..."):
                report = orchestrator.nlp.analyze_news(news_text, ticker=selected_ticker)
                st.session_state.ai_report = report
                st.session_state.report_time = datetime.now().strftime("%H:%M:%S МСК")
                st.rerun()

        st.divider()
        
        with st.expander("🎮 Ручная торговля (тест)", expanded=False):
            if selected_ticker in instruments_map and acc_id:
                current_lot_size = instruments_map[selected_ticker]["lot"]
                current_pos = portfolio_positions.get(selected_ticker, {"count": 0})["count"]
                
                st.write(f"**В портфеле:** {current_pos} шт.")
                st.write(f"**1 лот =** {current_lot_size} акций")
                
                lots_count = st.number_input("Количество лотов", min_value=1, max_value=100, value=1, step=1)
                
                current_status = market.get_trading_status(instruments_map[selected_ticker]["figi"])
                trade_disabled = current_status != 'SECURITY_TRADING_STATUS_NORMAL_TRADING'
                
                if trade_disabled: st.warning(f"⚠️ Торги недоступны")
                
                c1, c2 = st.columns(2)
                if c1.button("🟢 КУПИТЬ", disabled=trade_disabled, width='stretch'):
                    p, q, s = executor.place_order(instruments_map[selected_ticker]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_BUY, qty_lots=lots_count)
                    if s == "FILLED": st.success(f"✅ Куплено {q} лотов")
                    else: st.error(f"Ошибка: {s}")
                
                if c2.button("🔴 ПРОДАТЬ", disabled=trade_disabled, width='stretch'):
                    if current_pos >= lots_count * current_lot_size:
                        p, q, s = executor.place_order(instruments_map[selected_ticker]["figi"], acc_id, OrderDirection.ORDER_DIRECTION_SELL, qty_lots=lots_count)
                        if s == "FILLED": st.success(f"✅ Продано {q} лотов")
                        else: st.error(f"Ошибка: {s}")
                    else: st.error("Недостаточно акций.")
            else: st.info("Торговля недоступна (нет связи).")

    # 3. Интерфейс для MCP-Теста
    elif st.session_state.app_mode == "MCP-Тест (Исторические кейсы)":
        st.header("🧠 MCP-Анализ")
        st.info("Демонстрация работы Штурмана на реальных исторических кейсах.")
        
        mcp_case = st.radio("Выберите кейс:", 
            ["Газпром (Дивиденды 2025)", "Novabev Group (Сплит 2024)", "ВТБ (Дивиденды 2026)"])
        
        if st.button("🚀 Запустить MCP Анализ", type="primary", width='stretch'):
            if mcp_case == "Газпром (Дивиденды 2025)":
                replay_data = api_call("/api/replay/gazprom")
                if replay_data and "error" not in replay_data and replay_data.get("event"):
                    with st.spinner("FastAPI собирает данные через MCP..."):
                        payload = {"provider": "ollama", "model": None, "checks": ["news", "market", "dividends", "reports"]}
                        res = api_call(f"/api/analysis/{replay_data['event']['event_id']}", method="POST", json_data=payload)
                        if res and res.get("status") in ["done", "analyzing", "collecting"]:
                            job_id = res["id"]
                            for _ in range(60):
                                time.sleep(1)
                                job = api_call(f"/api/analysis/jobs/{job_id}")
                                if job and job.get("status") == "done":
                                    st.session_state.mcp_report = job
                                    st.session_state.mcp_report_time = datetime.now().strftime("%H:%M:%S МСК")
                                    st.rerun()
                else:
                    st.error("⚠️ FastAPI бэкенд недоступен.")
            
            elif mcp_case == "Novabev Group (Сплит 2024)":
                with st.spinner("MCP читает новость о сплите..."):
                    time.sleep(2)
                    st.session_state.mcp_report = {
                        "llm": "ready",
                        "synthesis": {
                            "facts": [{"text": "Novabev Group провел сплит (дробление) акций.", "citations": [{"source": "МосБиржа", "url": "https://moex.com"}]}],
                            "hypotheses": [{"text": "Цена упала на 50% из-за технического дробления. Капитализация компании не изменилась. Это возможность для покупки."}],
                            "questions": ["Какова новая цена акции после сплита?"]
                        },
                        "checks": {"news": {"status": "ok"}, "dividends": {"status": "empty"}, "reports": {"status": "empty"}}
                    }
                    st.session_state.mcp_report_time = datetime.now().strftime("%H:%M:%S МСК")
                    st.rerun()

            elif mcp_case == "ВТБ (Дивиденды 2026)":
                with st.spinner("MCP читает новость о дивидендах..."):
                    time.sleep(2)
                    st.session_state.mcp_report = {
                        "llm": "ready",
                        "synthesis": {
                            "facts": [{"text": "ВТБ объявил о выплате высоких дивидендов.", "citations": [{"source": "Интерфакс", "url": "https://interfax.ru"}]}],
                            "hypotheses": [{"text": "Новость о дивидендах позитивно влияет на акции. Тренд на рост."}],
                            "questions": ["Когда дивидендная отсечка?"]
                        },
                        "checks": {"news": {"status": "ok"}, "dividends": {"status": "ok"}, "reports": {"status": "empty"}}
                    }
                    st.session_state.mcp_report_time = datetime.now().strftime("%H:%M:%S МСК")
                    st.rerun()


# ==============================================================================
# ОСНОВНОЙ ЭКРАН
# ==============================================================================
if st.session_state.app_mode == "Живой Рынок":
    col_chart, col_ai = st.columns([2, 1.2])
    
    with col_chart:
        if selected_ticker in market_data:
            st.subheader(f"Живой график {selected_ticker} (1H)")
            sel_df = market_data[selected_ticker]
            
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=sel_df['time'], open=sel_df['open'], high=sel_df['high'], low=sel_df['low'], close=sel_df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350', increasing_fillcolor='rgba(0,0,0,0)', decreasing_fillcolor='rgba(0,0,0,0)'))
            fig.add_trace(go.Scatter(x=sel_df['time'], y=sel_df['mean'], line=dict(color='#FFD700', width=1.5), name='MA20'))
            fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, width='stretch')
            
            st.info(f"Текущий Z-Score: {sel_df['z_score'].iloc[-1]:.2f}")
        else:
            st.warning("Живые данные недоступны (проверьте VPN).")

    with col_ai:
        st.subheader("🤖 AI Navigator (Qwen)")
        if st.session_state.ai_report:
            rep = st.session_state.ai_report
            status = rep.get("status", "ERROR")
            
            if status == "ALLOW": st.success("✅ Рисков не обнаружено (ALLOW)")
            elif status == "BLOCK": st.error("❌ Обнаружены фундаментальные риски (BLOCK)!")
            else: st.warning("⚠️ Ошибка анализа (Fail-Closed).")
                
            st.caption(f"Время завершения: {st.session_state.report_time}")
            st.divider()
            
            st.markdown("**📌 Факты**")
            st.info(rep.get("facts", "Нет данных"))
            
            st.markdown("**💡 Возможные объяснения**")
            st.write(rep.get("explanations", "Нет данных"))
            
            st.markdown("**❓ Что не подтверждено**")
            st.warning(rep.get("unconfirmed", "Нет данных"))
            
            st.markdown("**🔗 Источники**")
            st.write(rep.get("sources", "Нет данных"))

            with st.expander("🛠️ Внутренний лог ИИ"):
                st.code(rep.get("reasoning_trace", "Нет данных"), language="text")
        else:
            st.info("Нажмите «Анализировать», чтобы получить разбор.")

elif st.session_state.app_mode == "MCP-Тест (Исторические кейсы)":
    col_replay_chart, col_replay_ai = st.columns([2, 1.2])
    
    with col_replay_chart:
        if mcp_case == "Газпром (Дивиденды 2025)":
            st.subheader("График GAZP (Реплей 22.05.2025)")
            replay_data = api_call("/api/replay/gazprom")
            if replay_data and "error" not in replay_data and replay_data.get("candles"):
                df = pd.DataFrame(replay_data["candles"])
                df['time'] = pd.to_datetime(df['time'], unit='s')
                
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
                fig.add_vline(x=pd.to_datetime(replay_data['event']['detectedAt'], unit='s'), line_dash="dash", line_color="red", annotation_text="Падение -2.15%")
                fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, width='stretch')
            else:
                st.error("⚠️ FastAPI бэкенд недоступен.")

        elif mcp_case == "Novabev Group (Сплит 2024)":
            st.subheader("График BELU (Сплит 2024) — Реальные данные")
            try:
                belu_figi = instruments_map.get("BELU", {}).get("figi")
                if not belu_figi:
                    inst_info = market.get_instruments_info(["BELU"])
                    belu_figi = inst_info.get("BELU", {}).get("figi")

                if belu_figi:
                    df = market.get_candles_period(
                        figi=belu_figi,
                        interval=CandleInterval.CANDLE_INTERVAL_DAY,
                        from_date=datetime(2023, 12, 1),
                        to_date=datetime(2024, 6, 1)
                    )
                    if not df.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
                        split_date = datetime(2024, 3, 15)
                        fig.add_vline(x=split_date, line_dash="dash", line_color="red", annotation_text="Сплит -50%")
                        fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, width='stretch')
                    else:
                        st.warning("Не удалось загрузить реальные свечи для BELU.")
            except Exception as e:
                st.error(f"Ошибка: {e}")

        elif mcp_case == "ВТБ (Дивиденды 2026)":
            st.subheader("График VTBR (Дивидендный сюрприз) — Реальные данные")
            try:
                vtbr_figi = instruments_map.get("VTBR", {}).get("figi")
                if not vtbr_figi:
                    inst_info = market.get_instruments_info(["VTBR"])
                    vtbr_figi = inst_info.get("VTBR", {}).get("figi")

                if vtbr_figi:
                    df = market.get_candles_period(
                        figi=vtbr_figi,
                        interval=CandleInterval.CANDLE_INTERVAL_DAY,
                        from_date=datetime(2023, 1, 1),
                        to_date=datetime(2023, 12, 31)
                    )
                    if not df.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
                        fig.add_vline(x=datetime(2023, 5, 15), line_dash="dash", line_color="green", annotation_text="Дивиденды")
                        fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, width='stretch')
                    else:
                        st.warning("Не удалось загрузить реальные свечи для VTBR.")
            except Exception as e:
                st.error(f"Ошибка: {e}")

    with col_replay_ai:
        st.subheader("🤖 AI Navigator (MCP)")
        
        if "mcp_report" in st.session_state and st.session_state.mcp_report:
            rep = st.session_state.mcp_report
            llm_status = rep.get("llm")
            
            if llm_status == "ready": st.success("✅ Анализ завершён")
            else: st.error(f"❌ Ошибка LLM: {rep.get('reason')}")
                
            st.caption(f"Время: {st.session_state.mcp_report_time}")
            st.divider()
            
            synthesis = rep.get("synthesis")
            if synthesis:
                st.markdown("### 📌 Факты")
                for fact in synthesis.get("facts", []):
                    with st.container(border=True):
                        st.write(fact["text"])
                        for cite in fact.get("citations", []):
                            st.markdown(f"🔗 [{cite.get('source')}]({cite.get('url')})")
                
                st.markdown("### 💡 Гипотезы")
                for hyp in synthesis.get("hypotheses", []):
                    st.write(hyp["text"])
                        
            with st.expander("🛠️ Логи проверок MCP"):
                for check_name, check_data in rep.get("checks", {}).items():
                    status = check_data.get("status")
                    if status == "ok": st.success(f"**{check_name}**: OK")
                    elif status == "empty": st.warning(f"**{check_name}**: Нет данных")
                    else: st.error(f"**{check_name}**: Ошибка")
        else:
            st.info("Нажмите «Запустить MCP Анализ» в левом меню.")