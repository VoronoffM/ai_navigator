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
        """
        Возвращает решение: BUY, SELL, HOLD или BLOCKED.
        """
        # 1. Спрашиваем Математику
        signal = self.quant.get_signal(last_z_score)
        if signal == "HOLD":
            return {"action": "HOLD", "reason": "Нет сигнала"}

        # 2. Спрашиваем NLP (защита от плохих новостей)
        nlp_res = self.nlp.analyze_news(news_text)
        if not nlp_res["allow_trade"]:
            return {"action": "BLOCKED", "reason": f"NLP: {nlp_res['reason']}"}

        # 3. Спрашиваем Risk-менеджмент
        if signal == "BUY":
            is_safe, msg = self.risk.validate_buy_order(cash, shares_count, price, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk: {msg}"}
        elif signal == "SELL":
            is_safe, msg = self.risk.validate_sell_order(shares_count, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk: {msg}"}

        return {"action": signal, "reason": "Все проверки пройдены"}