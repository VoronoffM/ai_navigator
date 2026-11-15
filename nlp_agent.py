import warnings
import ollama
import outlines
from typing import Literal
from pydantic import BaseModel, Field
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings

warnings.filterwarnings("ignore")

class EventClassification(BaseModel):
    type: Literal["FACT", "RUMOR"] = Field(description="FACT = факт. RUMOR = слух/паника.")

class TradeDecision(BaseModel):
    action: Literal["BLOCK", "ALLOW"] = Field(description="BLOCK = запрет. ALLOW = разрешение.")
    reason: str = Field(description="Краткое объяснение на русском.")

class NLPAgent:
    """
    Гибридный агент анализа новостей (Hard Rules + RAG + Qwen 2.5).
    """
    def __init__(self):
        # Оставляем только жесткие блокирующие правила
        self.fatal_keywords = ["дефолт", "банкротство", "остановка торгов", "технический сбой"]
        
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
            self.is_llm_ready = False

    def analyze_news(self, text):
        text_lower = text.lower()
        
        # УРОВЕНЬ 1: Мгновенная проверка на смертельные угрозы
        for word in self.fatal_keywords:
            if word in text_lower:
                return {"status": "BLOCK", "reason": f"Hard Rule: {word}"}
                
        # УРОВЕНЬ 2: УБРАНО АВТОМАТИЧЕСКОЕ РАЗРЕШЕНИЕ ПО ЭМОЦИЯМ
        # Слова "паника", "слив" больше не дают статус ALLOW. 
        # Они просто передаются на анализ LLM вместе с остальным текстом.

        # УРОВЕНЬ 3: Fail-Closed (если LLM недоступна, запрещаем)
        if not self.is_llm_ready:
            return {"status": "ERROR", "reason": "AI недоступен. Безопасный режим."}

        try:
            prompt_cls = f"Прочитай новость. Это факт или слух? Новость: {text}"
            cls_raw = self.model(prompt_cls, EventClassification)
            cls_res = EventClassification.model_validate_json(cls_raw)
            
            if cls_res.type == "RUMOR":
                return {"status": "ALLOW", "reason": "LLM: Слух/Паника"}
                
            context_docs = self.retriever.invoke(text)
            context = "\n".join([doc.page_content for doc in context_docs])
            
            prompt_dec = f"Оцени риск. Контекст: {context}. Новость: {text}"
            dec_raw = self.model(prompt_dec, TradeDecision)
            dec_res = TradeDecision.model_validate_json(dec_raw)
            
            if dec_res.action == "BLOCK":
                return {"status": "BLOCK", "reason": f"LLM: {dec_res.reason}"}
            else:
                return {"status": "ALLOW", "reason": f"LLM: {dec_res.reason}"}

        except Exception as e:
            # Fail-Closed при любой ошибке LLM
            return {"status": "ERROR", "reason": f"Ошибка AI: {e}"}