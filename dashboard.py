import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import httpx
from datetime import datetime
import time

BACKEND_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="AI-Штурман", layout="wide")
st.title("📈 AI-Штурман: Аналитический Терминал (MCP Powered)")

def api_call(endpoint, method="GET", json_data=None, auth_token=None):
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    try:
        with httpx.Client(timeout=15) as client:
            if method == "GET":
                r = client.get(f"{BACKEND_URL}{endpoint}", headers=headers)
            else:
                r = client.post(f"{BACKEND_URL}{endpoint}", json=json_data, headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        st.error(f"Ошибка бэкенда: {e}")
        return None

if "ai_report" not in st.session_state: st.session_state.ai_report = None
if "report_time" not in st.session_state: st.session_state.report_time = ""

quotes = api_call("/api/quotes")
if not quotes:
    st.warning("⚠️ FastAPI бэкенд не запущен. Выполните: python3 -m uvicorn backend.main:app --port 8000")
    st.stop()

replay_data = api_call("/api/replay/gazprom")
if not replay_data or not replay_data.get("event"):
    st.error("Не удалось загрузить исторический реплей.")
    st.stop()

event = replay_data["event"]
candles = replay_data["candles"]

# ЛЕВОЕ МЕНЮ
with st.sidebar:
    st.header("💼 Рыночный сканер (REST API)")
    for q in quotes:
        name = q.get("name") or q.get("ticker") or "Неизвестно"
        quote = q.get("quote") or {}
        price = quote.get("price") or "Нет данных"
        issue = q.get("issue")
        
        if price == "Нет данных" and issue:
            st.error(f"{name}: Ошибка API")
            with st.expander("Детали ошибки"):
                st.json(issue)
        else:
            st.metric(label=name, value=f"{price} ₽")

    st.divider()
    st.markdown("### 🧪 Тест ИИ-Анализа (MCP)")
    st.info("Сейчас мы анализируем **реальный исторический кейс**: 22 мая 2025 года Совет директоров Газпрома рекомендовал не выплачивать дивиденды.")
    
    provider = st.selectbox("Провайдер AI", ["ollama", "openai"])
    openai_key = ""
    if provider == "openai":
        openai_key = st.text_input("OpenAI API Key", type="password")

    if st.button("🧠 Запустить ИИ-Анализ через MCP", width='stretch'):
        if provider == "openai" and not openai_key:
            st.error("Введите OpenAI API Key или переключитесь на Ollama.")
        else:
            with st.spinner("FastAPI собирает контекст через MCP и спрашивает LLM..."):
                payload = {
                    "provider": provider,
                    "model": None,
                    "checks": ["news", "market", "dividends", "reports"]
                }
                res = api_call(f"/api/analysis/{event['event_id']}", method="POST", json_data=payload, auth_token=openai_key)
                
                if res and res.get("status") in ["done", "analyzing", "collecting"]:
                    job_id = res["id"]
                    progress_bar = st.progress(0, text="Сбор данных через MCP...")
                    
                    # Ждем до 60 секунд (на Intel Mac нейросеть может тупить)
                    for i in range(60):
                        time.sleep(1)
                        job = api_call(f"/api/analysis/jobs/{job_id}")
                        
                        progress_bar.progress((i + 1) / 60, text=f"Анализ... ({i+1} сек)")
                        
                        if job and job.get("status") == "done":
                            st.session_state.ai_report = job
                            st.session_state.report_time = datetime.now().strftime("%H:%M:%S МСК")
                            st.rerun()
                            
                    st.error(f"Таймаут ожидания ответа. Последний статус: {job.get('status') if job else 'Неизвестно'}")
                else:
                    st.error(f"Не удалось запустить анализ. Ответ: {res}")

# ЦЕНТРАЛЬНАЯ ЧАСТЬ
col_chart, col_ai = st.columns([2, 1.2])

with col_chart:
    st.subheader("График GAZP (Реплей 22 мая 2025)")
    df = pd.DataFrame(candles)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], 
                                 increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
    
    event_time = pd.to_datetime(event['detectedAt'], unit='s')
    fig.add_vline(x=event_time, line_dash="dash", line_color="red", annotation_text="Обнаружено падение -2.15%")
    
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, width='stretch')

with col_ai:
    st.subheader("🤖 AI Navigator (MCP)")
    
    if st.session_state.ai_report:
        rep = st.session_state.ai_report
        llm_status = rep.get("llm")
        
        if llm_status == "ready": st.success("✅ Анализ завершен успешно")
        elif llm_status == "skipped": st.warning("⚠️ Анализ не проводился")
        else: st.error(f"❌ Ошибка LLM: {rep.get('reason')}")
            
        st.caption(f"Время завершения: {st.session_state.report_time}")
        st.divider()
        
        synthesis = rep.get("synthesis")
        if synthesis:
            st.markdown("**📌 Факты**")
            for fact in synthesis.get("facts", []):
                st.info(fact["text"])
                for cite in fact.get("citations", []):
                    st.caption(f"Источник: {cite.get('source')} ({cite.get('url')})")
            
            st.markdown("**💡 Гипотезы**")
            for hyp in synthesis.get("hypotheses", []):
                st.write(hyp["text"])
                
            st.markdown("**❓ Вопросы для проверки**")
            for q in synthesis.get("questions", []):
                st.write(q)
                
        with st.expander("🛠️ Логи проверок MCP"):
            for check_name, check_data in rep.get("checks", {}).items():
                st.write(f"**{check_name}**: {check_data['status']} - {check_data.get('reason', '')}")
    else:
        st.info("Нажмите кнопку слева, чтобы запустить MCP-анализ.")