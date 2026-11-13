# Терминал: touch qa_agent.py && open -e qa_agent.py
import unittest
import pandas as pd
from quant_agent import QuantAgent
from risk_agent import RiskAgent
from nlp_agent import NLPAgent

class TestAIShturman(unittest.TestCase):
    def setUp(self):
        self.quant = QuantAgent()
        self.risk = RiskAgent(max_position_size_rub=50000)
        self.nlp = NLPAgent()

    def test_quant_signals(self):
        # Симулируем резкое падение
        df = pd.DataFrame({"close": [100]*19 + [80]}) 
        df = self.quant.calculate_metrics(df)
        z_score = df['z_score'].iloc[-1]
        self.assertEqual(self.quant.get_signal(z_score), "BUY", "Ошибка: Не выдал BUY при падении")

    def test_risk_blocks_buy(self):
        # Проверяем блокировку при наличии позиции
        is_safe, msg = self.risk.validate_buy_order(cash=100000, shares_count=10, price=100, lot_size=10)
        self.assertFalse(is_safe)
        self.assertEqual(msg, "Уже есть открытая позиция")

    def test_nlp_blocks_news(self):
        # Проверяем блокировку на плохие новости
        res = self.nlp.analyze_news("Газпром объявил дефолт")
        self.assertFalse(res["allow_trade"])

if __name__ == "__main__":
    print("🤖 Запуск QA-Агента...")
    unittest.main()