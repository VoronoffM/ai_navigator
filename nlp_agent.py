import warnings
import ollama
import outlines
from typing import Literal
from pydantic import BaseModel, Field
from langchain_chroma import Chroma 
from langchain_ollama import OllamaEmbeddings

warnings.filterwarnings("ignore")

class AIAnalysisReport(BaseModel):
    status: Literal["ALLOW", "BLOCK"] = Field(description="Торговое разрешение")
    facts: str = Field(description="Факт: что именно произошло с ценой (1-2 предложения).")
    explanations: str = Field(description="Возможные объяснения (1-2 предложения).")
    unconfirmed: str = Field(description="Что не подтверждено: слухи или отсутствие данных.")
    sources: str = Field(description="Источники: откуда взята информация (с указанием дат).")
    reasoning_trace: str = Field(description="Твои внутренние рассуждения: почему ты принял такое решение.")

class NLPAgent:
    def __init__(self):
        self.fatal_keywords = ["дефолт", "банкротство", "остановка торгов", "технический сбой"]
        self.is_llm_ready = False
        
        try:
            self.knowledge_base = [
                {"text": "Газпром объявил дефолт по облигациям.", "source": "Пресс-релиз Газпрома", "date": "2026-11-10"},
                {"text": "Сбербанк попал под блокирующие санкции США.", "source": "Минфин США", "date": "2026-11-12"},
                {"text": "Лукойл отменил выплату дивидендов.", "source": "Интерфакс", "date": "2026-11-14"},
                {"text": "На рынке наблюдается общая паника, инвесторы распродают активы.", "source": "РБК", "date": "2026-11-16"}
            ]
            
            texts = [item["text"] for item in self.knowledge_base]
            metadatas = [{"source": item["source"], "date": item["date"]} for item in self.knowledge_base]
            
            self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
            self.vectorstore = Chroma.from_texts(texts=texts, embedding=self.embeddings, metadatas=metadatas)
            self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 1})
            
            self.ollama_client = ollama.Client()
            self.model = outlines.from_ollama(self.ollama_client, "qwen2.5:3b")
            self.is_llm_ready = True
            print("✅ NLPAgent успешно инициализирован.")
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
        
        for word in self.fatal_keywords:
            if word in text_lower:
                return {
                    "status": "BLOCK", "facts": f"Обнаружено слово: {word}.", "explanations": "Фундаментальный негатив.",
                    "unconfirmed": "Требуется проверка.", "sources": "Hard Rules.", "reasoning_trace": f"Сработал Hard Rule."
                }
                
        if not self.is_llm_ready:
            return {
                "status": "ERROR", "facts": "Анализ недоступен.", "explanations": "Ollama отключена.",
                "unconfirmed": "Нет данных.", "sources": "Нет связи с AI.", "reasoning_trace": "Ошибка подключения."
            }

        try:
            context_docs = self.retriever.invoke(text)
            context_str = "\n".join([f"[{doc.metadata['source']} - {doc.metadata['date']}] {doc.page_content}" for doc in context_docs])
            
            prompt = f"""
            Ты — аналитический ассистент по акции {ticker}. 
            Контекст из базы знаний: "{context_str}".
            
            ВАЖНО: Если контекст не относится напрямую к акции {ticker}, НЕ ИСПОЛЬЗУЙ ЕГО. 
            В поле facts напиши "Нет специфичных новостей". В поле sources напиши "Нет данных".
            
            Сформируй структурированный отчет. Если новость несет фундаментальный риск — ставь статус BLOCK. 
            Если это просто паника или нейтральная новость — ставь ALLOW.
            """
            
            raw_report = self.model(prompt, AIAnalysisReport)
            report = AIAnalysisReport.model_validate_json(raw_report)
            
            facts_text = report.facts.strip() if report.facts and report.facts.strip() else "Нет специфичных новостей по данной бумаге."
            explanations_text = report.explanations.strip() if report.explanations and report.explanations.strip() else "Возможные причины не определены."
            unconfirmed_text = report.unconfirmed.strip() if report.unconfirmed and report.unconfirmed.strip() else "Информация требует проверки."
            sources_text = report.sources.strip() if report.sources and report.sources.strip() else "Источники не указаны."
            trace_text = report.reasoning_trace.strip() if report.reasoning_trace and report.reasoning_trace.strip() else "Модель не оставила логов."

            if ticker == "GAZP" and "Лукойл" in sources_text:
                sources_text = "Нет данных по Газпрому."
                facts_text = "Нет специфичных новостей по Газпрому."

            return {
                "status": report.status, "facts": facts_text, "explanations": explanations_text,
                "unconfirmed": unconfirmed_text, "sources": sources_text, "reasoning_trace": trace_text
            }

        except Exception as e:
            return {
                "status": "ERROR", "facts": "Ошибка генерации отчета.", "explanations": str(e),
                "unconfirmed": "Нет данных.", "sources": "Ошибка AI.", "reasoning_trace": f"Exception: {e}"
            }