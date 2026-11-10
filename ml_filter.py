class MLNoiseFilter:
    def __init__(self):
        self.fundamental_keywords = ["дефолт", "санкции", "отмена дивидендов", "банкротство", "суд", "арест"]
        self.panic_keywords = ["паника", "слив", "падение", "обвал", "маржин колл", "ужас", "страшно"]

    def analyze_message(self, ticker, text):
        text_lower = text.lower()
        
        for word in self.fundamental_keywords:
            if word in text_lower:
                return {"sentiment": -1.0, "fundamental": True, "reason": f"Угроза: {word}"}
                
        for word in self.panic_keywords:
            if word in text_lower:
                return {"sentiment": -0.5, "fundamental": False, "reason": "Паника толпы"}
                
        return {"sentiment": 0.0, "fundamental": False, "reason": "Нейтрально"}