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
        df = pd.DataFrame({"close": [100]*19 + [80]}) 
        df = self.quant.calculate_metrics(df)
        z_score = df['z_score'].iloc[-1]
        self.assertEqual(self.quant.get_signal(z_score), "BUY")

    def test_risk_dynamic_lot_size(self):
        # Сбер (лот 10): 100 руб * 10 = 1000 руб (ок)
        is_safe_sber, _ = self.risk.validate_buy_order(cash=100000, shares_count=0, price=100, lot_size=10)
        self.assertTrue(is_safe_sber)
        # Дорогая акция (лот 1): 60000 руб (превышает лимит 50к)
        is_safe_lkoh, msg = self.risk.validate_buy_order(cash=100000, shares_count=0, price=60000, lot_size=1)
        self.assertFalse(is_safe_lkoh)

if __name__ == "__main__":
    unittest.main()