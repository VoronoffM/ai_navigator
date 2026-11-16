import warnings
import ollama
import outlines
from typing import Literal
from pydantic import BaseModel, Field, ValidationError
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings

warnings.filterwarnings("ignore")

class EventClassification(BaseModel):
    type: Literal["FACT", "RUMOR"] = Field(description="FACT = факт. RUMOR = слух/паника.")

class TradeDecision(BaseModel):
    action: Literal["BLOCK", "ALLOW"] = Field(description="BLOCK = запрет. ALLOW = разрешение.")
    reason: str = Field(description="Краткое объяснение на русском.")

class NLPAgent:
    def __init__(self):
        self.fatal_keywords = ["дефолт", "банкротство", "остановка торгов", "технический сбой"]
        self.is_llm_ready = False
        
        try:
            self.knowledge_base = [
                "Газпром объявил дефолт по облигациям.",
                "Сбербанк попал под блокирующие санкции США.",
                "Лукойл отменил выплату дивидендов."
            ]
            self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
            self.vectorstore = Chroma.from_texts(texts=self.knowledge_base, embedding=self.embeddings)
            self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 1})
            
            self.ollama_client = ollama.Client()
            self.model = outlines.from_ollama(self.ollama_client, "qwen2.5:3b")
            self.is_llm_ready = True
        except Exception as e:
            print(f"⚠️ LLM offline: {e}")

    def close(self):
        """Закрывает сетевые соединения для предотвращения ResourceWarning."""
        try:
            if hasattr(self, 'ollama_client'):
                self.ollama_client._client.close()
        except Exception:
            pass

    def analyze_news(self, text):
        text_lower = text.lower()
        
        # УРОВЕНЬ 1: Жесткие правила (Доказанный риск)
        for word in self.fatal_keywords:
            if word in text_lower:
                return {"status": "BLOCK", "reason": f"Hard Rule: {word}"}
                
        # УРОВЕНЬ 2: Отказ техники (Fail-Closed)
        if not self.is_llm_ready:
            return {"status": "ERROR", "reason": "AI недоступен. Безопасный режим."}

        try:
            prompt_cls = f"Прочитай новость. Это факт или слух? Новость: {text}"
            cls_raw = self.model(prompt_cls, EventClassification)
            cls_res = EventClassification.model_validate_json(cls_raw)
            
            # Неподтвержденный слух = Блокировка (в консервативном режиме)
            if cls_res.type == "RUMOR":
                return {"status": "BLOCK", "reason": "Неподтвержденный слух (нет доказательств)"}
                
            context_docs = self.retriever.invoke(text)
            context = "\n".join([doc.page_content for doc in context_docs])
            
            prompt_dec = f"Оцени риск. Контекст: {context}. Новость: {text}"
            dec_raw = self.model(prompt_dec, TradeDecision)
            dec_res = TradeDecision.model_validate_json(dec_raw)
            
            if dec_res.action == "BLOCK":
                return {"status": "BLOCK", "reason": f"LLM: {dec_res.reason}"}
            else:
                return {"status": "ALLOW", "reason": f"LLM: {dec_res.reason}"}

        except ValidationError as e:
            return {"status": "ERROR", "reason": f"Некорректный ответ LLM: {str(e)}"}
        except Exception as e:
            return {"status": "ERROR", "reason": f"Ошибка AI: {str(e)}"}