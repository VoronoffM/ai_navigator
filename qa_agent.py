import unittest
import pandas as pd
from unittest.mock import patch, MagicMock
from quant_agent import QuantAgent
from risk_agent import RiskAgent
from nlp_agent import NLPAgent
from orchestrator_agent import OrchestratorAgent

class TestAIShturman(unittest.TestCase):
    @patch('nlp_agent.NLPAgent.__init__', return_value=None)
    def setUp(self, mock_init):
        self.quant = QuantAgent()
        self.risk = RiskAgent(max_position_size_rub=50000)
        
        # Создаем NLPAgent без вызова реального __init__ (чтобы не подключаться к Ollama)
        self.nlp = NLPAgent()
        
        # Вручную задаем нужные атрибуты, так как __init__ был пропущен
        self.nlp.fatal_keywords = ["дефолт", "банкротство", "остановка торгов", "технический сбой"]
        self.nlp.is_llm_ready = False
        self.nlp.model = MagicMock()  # Добавляем фейковый атрибут модели
        self.nlp.retriever = MagicMock()
        
        self.orchestrator = OrchestratorAgent()
        self.orchestrator.nlp = self.nlp # Подменяем реальный агент на наш мок

    def test_quant_signals(self):
        df = pd.DataFrame({"close": [100]*19 + [80]}) 
        df = self.quant.calculate_metrics(df)
        z_score = df['z_score'].iloc[-1]
        self.assertEqual(self.quant.get_signal(z_score), "BUY")

    def test_risk_dynamic_lot_size(self):
        is_safe_sber, _ = self.risk.validate_buy_order(cash=100000, shares_count=0, price=100, lot_size=10)
        self.assertTrue(is_safe_sber)
        is_safe_lkoh, _ = self.risk.validate_buy_order(cash=100000, shares_count=0, price=60000, lot_size=1)
        self.assertFalse(is_safe_lkoh)

    # --- ТЕСТЫ NLP И ОРКЕСТРАТОРА ---

    def test_nlp_fail_closed(self):
        self.nlp.is_llm_ready = False
        res = self.nlp.analyze_news("Обычный день")
        self.assertEqual(res["status"], "ERROR")

    def test_nlp_hard_rules_block(self):
        res = self.nlp.analyze_news("У компании дефолт!")
        self.assertEqual(res["status"], "BLOCK")

    def test_nlp_rumor_blocks(self):
        # Симулируем, что LLM вернула RUMOR
        self.nlp.is_llm_ready = True
        
        # Патчим метод валидации Pydantic, чтобы он вернул RUMOR
        with patch('nlp_agent.EventClassification.model_validate_json') as mock_val:
            mock_val.return_value.type = "RUMOR"
            
            # Патчим сам вызов модели (self.model), чтобы избежать реального запроса
            with patch.object(self.nlp, 'model') as mock_model:
                mock_model.return_value = "fake_json"
                
                res = self.nlp.analyze_news("На рынке паника")
                self.assertEqual(res["status"], "BLOCK")
                self.assertIn("Неподтвержденный слух", res["reason"])

    def test_orchestrator_unknown_status(self):
        with patch.object(self.nlp, 'analyze_news') as mock_nlp:
            mock_nlp.return_value = {"status": "UNKNOWN", "reason": "Something"}
            res = self.orchestrator.decide_trade("GAZP", -1.6, "text", 100000, 0, 100, 10)
            self.assertEqual(res["action"], "BLOCKED")
            self.assertIn("UNKNOWN", res["reason"])

    def test_orchestrator_missing_status(self):
        with patch.object(self.nlp, 'analyze_news') as mock_nlp:
            mock_nlp.return_value = {"reason": "No status here"}
            res = self.orchestrator.decide_trade("GAZP", -1.6, "text", 100000, 0, 100, 10)
            self.assertEqual(res["action"], "BLOCKED")
            self.assertIn("UNKNOWN", res["reason"])

    def test_orchestrator_blocks_buy_on_nlp_error(self):
        self.nlp.is_llm_ready = False
        res = self.orchestrator.decide_trade("GAZP", -1.6, "Обычный день", 100000, 0, 100, 10)
        self.assertEqual(res["action"], "BLOCKED")
        self.assertIn("ERROR", res["reason"])

    def test_orchestrator_bypasses_nlp_for_sell(self):
        with patch.object(self.nlp, 'analyze_news') as mock_nlp:
            res = self.orchestrator.decide_trade("GAZP", 1.6, "Газпром дефолт", 100000, 10, 100, 10)
            self.assertEqual(res["action"], "SELL")
            mock_nlp.assert_not_called() # Убеждаемся, что NLP не вызывался

if __name__ == "__main__":
    unittest.main()