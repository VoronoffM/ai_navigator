import unittest
import pandas as pd
from quant_agent import QuantAgent
from risk_agent import RiskAgent
from nlp_agent import NLPAgent

class TestAIshтурман(unittest.TestCase):
    def setUp(self):
        self.quant = QuantAgent()
        self.risk = RiskAgent(max_position_size_rub=50000)
        self.nlp = NLPAgent()

    def test_quant_signals(self):
        # Создаем фейковые данные, где последняя цена резко упала
        df = pd.DataFrame({"close": [100]*19 + [80]}) 
        df = self.quant.calculate_metrics(df)
        z_score = df['z_score'].iloc[-1]
        signal = self.quant.get_signal(z_score)
        self.assertEqual(signal, "BUY", "Ошибка QuantAgent: Не выдал BUY при сильном падении")

    def test_risk_blocks_buy_if_position_exists(self):
        # Проверяем, что RiskAgent не даст купить вторую позицию
        is_safe, msg = self.risk.validate_buy_order(cash=100000, shares_count=10, price=100, lot_size=10)
        self.assertFalse(is_safe, "Ошибка RiskAgent: Разрешил покупку при наличии позиции")
        self.assertEqual(msg, "Уже есть открытая позиция")

    def test_risk_allows_valid_buy(self):
        # Проверяем, что RiskAgent разрешает покупку с нуля
        is_safe, msg = self.risk.validate_buy_order(cash=100000, shares_count=0, price=100, lot_size=10)
        self.assertTrue(is_safe, "Ошибка RiskAgent: Заблокировал валидную покупку")

    def test_nlp_blocks_fundamental_bad_news(self):
        res = self.nlp.analyze_news("Газпром объявил дефолт")
        self.assertFalse(res["allow_trade"], "Ошибка NLPAgent: Не заблокировал сделку при дефолте")

    def test_nlp_allows_panic_news(self):
        res = self.nlp.analyze_news("На рынке паника и слив")
        self.assertTrue(res["allow_trade"], "Ошибка NLPAgent: Заблокировал вход при панике толпы")

if __name__ == "__main__":
    print("🤖 Запуск QA-Агента...")
    unittest.main()