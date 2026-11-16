import unittest
from nlp_agent import NLPAgent

class TestRealQwenIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nlp = NLPAgent()
        if not cls.nlp.is_llm_ready:
            raise unittest.SkipTest("Ollama/Qwen недоступны. Тест пропущен.")

    @classmethod
    def tearDownClass(cls):
        cls.nlp.close()

    def test_real_qwen_unknown_news(self):
        # Текст, не содержащий жестких правил, чтобы гарантированно пройти в LLM
        text = "Инвесторы сегодня в неопределенности, объемы торгов низкие."
        res = self.nlp.analyze_news(text)
        
        # Проверяем только структуру и безопасность, не гадаем, что ответит LLM
        self.assertIn(res.get("status"), ["ALLOW", "BLOCK", "ERROR"])
        self.assertIn("reason", res)
        self.assertIsInstance(res["reason"], str)
        
        # Если сработал Outlines и RAG, то это либо ALLOW, либо BLOCK, но не ERROR (если Ollama запущена)
        if self.nlp.is_llm_ready:
            self.assertNotEqual(res["status"], "ERROR", "LLM вернула ошибку, проверьте промпты Outlines")

if __name__ == "__main__":
    unittest.main()