from quant_agent import QuantAgent
from nlp_agent import NLPAgent
from risk_agent import RiskAgent

class OrchestratorAgent:
    """
    Главный Оркестратор. Управляет логикой принятия решений.
    """
    def __init__(self):
        self.quant = QuantAgent()
        self.nlp = NLPAgent()
        self.risk = RiskAgent()

    def decide_trade(self, ticker, last_z_score, news_text, cash, shares_count, price, lot_size):
        # 1. Спрашиваем Математику
        signal = self.quant.get_signal(last_z_score)
        if signal == "HOLD":
            return {"action": "HOLD", "reason": "Нет сигнала"}

        # 2. ЛОГИКА ДЛЯ ПОКУПКИ (Вход в риск)
        if signal == "BUY":
            # Проверяем новости ТОЛЬКО перед покупкой
            nlp_res = self.nlp.analyze_news(news_text)
            if nlp_res["status"] == "ERROR":
                return {"action": "BLOCKED", "reason": f"NLP (Fail-Closed): {nlp_res['reason']}"}
            if nlp_res["status"] == "BLOCK":
                return {"action": "BLOCKED", "reason": f"NLP: {nlp_res['reason']}"}
            
            # Если новости чистые, проверяем риск
            is_safe, msg = self.risk.validate_buy_order(cash, shares_count, price, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk: {msg}"}

        # 3. ЛОГИКА ДЛЯ ПРОДАЖИ (Сокращение риска)
        elif signal == "SELL":
            # ВАЖНО: Мы НЕ вызываем NLP. Если у нас открыта позиция, 
            # плохие новости — это повод быстрее продать, а не блокировать выход.
            is_safe, msg = self.risk.validate_sell_order(shares_count, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk: {msg}"}

        return {"action": signal, "reason": "Все проверки пройдены"}