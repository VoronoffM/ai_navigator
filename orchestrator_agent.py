# Терминал: touch orchestrator_agent.py && open -e orchestrator_agent.py
from quant_agent import QuantAgent
from nlp_agent import NLPAgent
from risk_agent import RiskAgent

class OrchestratorAgent:
    """
    Главный Оркестратор. Управляет принятием решений.
    Собирает сигналы от Математика (Quant), Аналитика (NLP) и Службы Безопасности (Risk).
    """
    def __init__(self):
        # Инициализируем всех подчиненных агентов
        self.quant = QuantAgent()
        self.nlp = NLPAgent()
        self.risk = RiskAgent()

    def decide_trade(self, ticker, last_z_score, news_text, cash, shares_count, price, lot_size):
        """
        Принимает решение о сделке на основе данных от всех агентов.
        
        Возвращает словарь:
        - action: "BUY", "SELL", "HOLD", "BLOCKED"
        - reason: Текстовое обоснование для логов
        """
        
        # ШАГ 1: Спрашиваем Математика (QuantAgent). 
        # Он смотрит на Z-Score и говорит, есть ли аномалия.
        signal = self.quant.get_signal(last_z_score)
        
        if signal == "HOLD":
            return {"action": "HOLD", "reason": "Нет математического сигнала (зона HOLD)"}

        # ШАГ 2: Спрашиваем Аналитика (NLPAgent). 
        # Если математика говорит "Покупай", мы проверяем, нет ли там плохих новостей.
        # Это спасает нас от покупки "падающих ножей".
        nlp_res = self.nlp.analyze_news(news_text)
        if not nlp_res["allow_trade"]:
            return {"action": "BLOCKED", "reason": f"NLP запретил: {nlp_res['reason']}"}

        # ШАГ 3: Спрашиваем Службу Безопасности (RiskAgent).
        # Проверяем, хватает ли денег на счету и не превышен ли лимит.
        if signal == "BUY":
            is_safe, msg = self.risk.validate_buy_order(cash, shares_count, price, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk заблокировал: {msg}"}
                
        elif signal == "SELL":
            is_safe, msg = self.risk.validate_sell_order(shares_count, lot_size)
            if not is_safe:
                return {"action": "BLOCKED", "reason": f"Risk заблокировал: {msg}"}

        # Если все три агента дали "Добро", возвращаем разрешение на сделку.
        return {"action": signal, "reason": "Все проверки пройдены"}