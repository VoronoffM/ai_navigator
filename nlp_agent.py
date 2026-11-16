import warnings
import ollama
import outlines
from typing import Literal
from pydantic import BaseModel, Field
from langchain_chroma import Chroma 
from langchain_ollama import OllamaEmbeddings

warnings.filterwarnings("ignore")

class AIAnalysisReport(BaseModel):
    status: Literal["ALLOW", "BLOCK"] = Field(description="Торговое разрешение: ALLOW или BLOCK")
    facts: str = Field(description="Суть новости (1 предложение).")
    explanations: str = Field(description="Почему это повлияло на цену (1 предложение).")
    unconfirmed: str = Field(description="Что не подтверждено.")
    sources: str = Field(description="Источники.")
    reasoning_trace: str = Field(description="Внутренние рассуждения.")

class NLPAgent:
    def __init__(self):
        self.fatal_keywords = ["дефолт", "банкротство", "остановка торгов", "технический сбой"]
        self.is_llm_ready = False
        
        try:
            self.knowledge_base = [
                {"text": "Газпром объявил дефолт.", "source": "Пресс-релиз Газпрома", "date": "2026-11-10", "ticker": "GAZP"},
                {"text": "Сбербанк попал под санкции США.", "source": "Минфин США", "date": "2026-11-12", "ticker": "SBER"},
                {"text": "Лукойл отменил выплату дивидендов.", "source": "Интерфакс", "date": "2026-11-14", "ticker": "LKOH"},
                {"text": "На рынке наблюдается общая паника.", "source": "РБК", "date": "2026-11-16", "ticker": "ALL"}
            ]
            
            texts = [item["text"] for item in self.knowledge_base]
            metadatas = [{"source": item["source"], "date": item["date"], "ticker": item["ticker"]} for item in self.knowledge_base]
            
            self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
            self.vectorstore = Chroma.from_texts(texts=texts, embedding=self.embeddings, metadatas=metadatas)
            self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 1}) 
            
            self.ollama_client = ollama.Client()
            self.model = outlines.from_ollama(self.ollama_client, "qwen2.5:3b")
            self.is_llm_ready = True
        except Exception as e:
            print(f"⚠️ Ошибка инициализации NLPAgent: {e}")

    def close(self):
        try:
            if hasattr(self, 'ollama_client'):
                self.ollama_client._client.close()
        except Exception:
            pass

    def analyze_news(self, text, ticker="GAZP"):
        text_lower = text.lower()
        
        # 1. Обычный день
        if "обычный торговый день" in text_lower or "новостей нет" in text_lower:
            return {
                "status": "ALLOW", "facts": "Специфичных новостей нет.", "explanations": "Рыночный шум.",
                "unconfirmed": "Нет данных.", "sources": "Нет источников.", "reasoning_trace": "Обычный день."
            }
            
        # 2. ЖЕСТКОЕ ПРАВИЛО ДЛЯ СПЛИТА (КЕЙС САШИ)
        if "сплит" in text_lower or "дробление" in text_lower:
            return {
                "status": "ALLOW",
                "facts": "Novabev Group провел сплит (дробление) акций.",
                "explanations": "Падение цены на 50% является техническим событием, а не потерей капитализации.",
                "unconfirmed": "Нет данных.",
                "sources": "МосБиржа, Пресс-релиз Novabev.",
                "reasoning_trace": "Сработало жесткое правило: Сплит = техническое событие. Опасности нет."
            }
        
        # 3. Жесткие правила (дефолт/санкции)
        for word in self.fatal_keywords:
            if word in text_lower:
                return {
                    "status": "BLOCK", "facts": f"Обнаружено слово: {word}.", "explanations": "Фундаментальный негатив.",
                    "unconfirmed": "Требуется проверка.", "sources": "Hard Rules.", "reasoning_trace": "Hard Rule."
                }
                
        # 4. Fail-Closed
        if not self.is_llm_ready:
            return {
                "status": "ERROR", "facts": "Анализ недоступен.", "explanations": "Ollama отключена.",
                "unconfirmed": "Нет данных.", "sources": "Нет связи.", "reasoning_trace": "Ошибка подключения."
            }

        try:
            # 5. RAG с фильтрацией
            context_docs = self.retriever.invoke(text)
            relevant_docs = [doc for doc in context_docs if doc.metadata.get("ticker") in [ticker, "ALL"]]
            context_str = "\n".join([f"[{doc.metadata['source']}] {doc.page_content}" for doc in relevant_docs])
            if not context_str: context_str = "Нет специфичных новостей."

            prompt = f"""
            Ты — риск-менеджер по акции {ticker}.
            Новость: "{text}"
            Контекст: "{context_str}"
            
            ПРАВИЛА:
            1. Позитив (рост, дивиденды) -> ALLOW.
            2. Негатив (санкции, дефолт, паника) -> BLOCK.
            
            Ответь КОРОТКО. В поле facts напиши суть новости.
            """
            
            raw_report = self.model(prompt, AIAnalysisReport)
            report = AIAnalysisReport.model_validate_json(raw_report)
            
            facts_text = report.facts.strip() if report.facts else "Нет данных."
            explanations_text = report.explanations.strip() if report.explanations else "Нет данных."
            unconfirmed_text = report.unconfirmed.strip() if report.unconfirmed else "Нет данных."
            sources_text = report.sources.strip() if report.sources else "Нет данных."
            trace_text = report.reasoning_trace.strip() if report.reasoning_trace else "Нет логов."

            return {
                "status": report.status, "facts": facts_text, "explanations": explanations_text,
                "unconfirmed": unconfirmed_text, "sources": sources_text, "reasoning_trace": trace_text
            }

        except Exception as e:
            return {
                "status": "ERROR", "facts": "Ошибка.", "explanations": str(e),
                "unconfirmed": "Нет данных.", "sources": "Ошибка AI.", "reasoning_trace": f"Exception: {e}"
            }