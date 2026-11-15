import unittest
import pandas as pd
from unittest.mock import patch
from quant_agent import QuantAgent
from risk_agent import RiskAgent
from nlp_agent import NLPAgent
from orchestrator_agent import OrchestratorAgent

class TestAIShturman(unittest.TestCase):
    def setUp(self):
        self.quant = QuantAgent()
        self.risk = RiskAgent(max_position_size_rub=50000)
        self.nlp = NLPAgent()
        self.orchestrator = OrchestratorAgent()

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

    # --- НОВЫЕ ТЕСТЫ ПАКЕТА ИЗМЕНЕНИЙ ---

    def test_nlp_fail_closed_on_offline(self):
        """Проверка, что при отключенной LLM возвращается ERROR, а не ALLOW."""
        self.nlp.is_llm_ready = False
        res = self.nlp.analyze_news("Обычный день")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("AI недоступен", res["reason"])

    def test_nlp_hard_rules_block(self):
        """Проверка, что жесткие правила (дефолт) блокируют сделку."""
        res = self.nlp.analyze_news("У компании дефолт!")
        self.assertEqual(res["status"], "BLOCK")

    def test_nlp_no_auto_allow_on_panic(self):
        """Проверка, что слово 'паника' больше не дает мгновенный ALLOW без LLM."""
        self.nlp.is_llm_ready = False # Симулируем отказ LLM
        res = self.nlp.analyze_news("На рынке паника!")
        # Должно вернуться ERROR (Fail-Closed), так как LLM отключена
        self.assertEqual(res["status"], "ERROR")

    def test_orchestrator_blocks_buy_on_nlp_error(self):
        """Проверка, что Оркестратор блокирует BUY при ошибке NLP."""
        self.orchestrator.nlp.is_llm_ready = False
        res = self.orchestrator.decide_trade(
            ticker="GAZP", last_z_score=-1.6, news_text="Обычный день", 
            cash=100000, shares_count=0, price=100, lot_size=10
        )
        self.assertEqual(res["action"], "BLOCKED")
        self.assertIn("Fail-Closed", res["reason"])

    def test_orchestrator_bypasses_nlp_for_sell(self):
        """Проверка, что Оркестратор разрешает SELL, даже если NLP видит плохие новости."""
        # Заставляем NLP блокировать (эмуляция дефолта)
        self.orchestrator.nlp.fatal_keywords = ["дефолт"]
        
        # Вызываем SELL с текстом дефолта
        res = self.orchestrator.decide_trade(
            ticker="GAZP", last_z_score=1.6, news_text="Газпром дефолт", 
            cash=100000, shares_count=10, price=100, lot_size=10
        )
        # Ожидаем SELL, так как мы выходим из позиции, NLP игнорируется
        self.assertEqual(res["action"], "SELL")
        self.assertEqual(res["reason"], "Все проверки пройдены")

if __name__ == "__main__":
    unittest.main()