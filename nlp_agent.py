# Терминал: touch nlp_agent.py && open -e nlp_agent.py
class NLPAgent:
    """Агент анализа новостей. Сейчас на ключевых словах (заглушка для AI)."""
    def __init__(self):
        # Слова, которые означают реальный крах компании
        self.fundamental_keywords = ["дефолт", "санкции", "отмена дивидендов", "банкротство", "арест"]
        # Слова, которые означают эмоциональную панику
        self.panic_keywords = ["паника", "слив", "обвал", "маржин колл"]

    def analyze_news(self, text):
        text_lower = text.lower()
        
        # 1. Проверяем на реальный негатив
        for word in self.fundamental_keywords:
            if word in text_lower:
                return {"allow_trade": False, "reason": f"Фундаментальная угроза: {word}"}
                
        # 2. Если паника - это хороший вход (отскок)
        for word in self.panic_keywords:
            if word in text_lower:
                return {"allow_trade": True, "reason": "Паника толпы (ложное падение)"}
                
        return {"allow_trade": True, "reason": "Нейтральный фон"}