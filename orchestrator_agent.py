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
            return {"action": "HOLD", "report": None, "reason": "Нет сигнала"}

        if signal == "BUY":
            nlp_res = self.nlp.analyze_news(news_text, ticker=ticker)
            
            if nlp_res.get("status") != "ALLOW":
                return {"action": "BLOCKED", "report": nlp_res, "reason": f"AI: {nlp_res.get('explanations', 'Запрет')}"}
            
            is_safe, msg = self.risk.validate_buy_order(cash, shares_count, price, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "report": nlp_res, "reason": f"Risk: {msg}"}

            return {"action": "BUY", "report": nlp_res, "reason": "Разрешено"}

        elif signal == "SELL":
            return {"action": "SELL", "report": None, "reason": "Выход из позиции"}

        return {"action": signal, "report": None, "reason": "OK"}