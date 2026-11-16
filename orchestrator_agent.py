from quant_agent import QuantAgent
from nlp_agent import NLPAgent
from risk_agent import RiskAgent

class OrchestratorAgent:
    def __init__(self):
        self.quant = QuantAgent()
        self.nlp = NLPAgent()
        self.risk = RiskAgent()

    def decide_trade(self, ticker, last_z_score, news_text, cash, shares_count, price, lot_size):
        signal = self.quant.get_signal(last_z_score)
        if signal == "HOLD":
            return {"action": "HOLD", "reason": "Нет сигнала"}

        if signal == "BUY":
            nlp_res = self.nlp.analyze_news(news_text)
            # Строгая проверка: только явный ALLOW разрешает идти дальше
            if nlp_res.get("status") != "ALLOW":
                return {"action": "BLOCKED", "reason": f"NLP ({nlp_res.get('status', 'UNKNOWN')}): {nlp_res.get('reason', 'Нет данных')}"}
            
            is_safe, msg = self.risk.validate_buy_order(cash, shares_count, price, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk: {msg}"}

        elif signal == "SELL":
            # Выход не блокируется NLP
            is_safe, msg = self.risk.validate_sell_order(shares_count, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk: {msg}"}

        return {"action": signal, "reason": "Все проверки пройдены"}