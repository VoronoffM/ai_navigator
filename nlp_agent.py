class NLPAgent:
    def __init__(self):
        self.fundamental_keywords = ["дефолт", "санкции", "отмена дивидендов", "банкротство"]
        self.panic_keywords = ["паника", "слив", "обвал", "маржин колл"]

    def analyze_news(self, text):
        """Возвращает вердикт: можно ли входить в сделку"""
        text_lower = text.lower()
        
        for word in self.fundamental_keywords:
            if word in text_lower:
                return {"allow_trade": False, "reason": f"Фундаментальная угроза: {word}"}
                
        for word in self.panic_keywords:
            if word in text_lower:
                return {"allow_trade": True, "reason": "Паника толпы (ложное падение)"}
                
        return {"allow_trade": True, "reason": "Нейтральный фон"}