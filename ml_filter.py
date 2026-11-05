import json
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

class MLNoiseFilter:
    def __init__(self):
        self.llm = ChatOllama(
            model="qwen2.5:3b", 
            base_url="http://localhost:11434",
            temperature=0.0
        )
        self.prompt_template = PromptTemplate.from_template(
            """Instruction: Analyze the text regarding the ticker '{ticker}' using FinGPT standards.

Input Text: {text}

Output ONLY a valid JSON object without any markdown tickers or extra text:
{{
  "target_ticker": "{ticker}",
  "fundamental": true/false,
  "event_family": "Dividends/Earnings/Market Dynamics/Retail Speculation",
  "sentiment": float between -1.0 and +1.0,
  "confidence": float between 0.0 and 1.0
}}

JSON Output:"""
        )

    def analyze_message(self, ticker: str, text: str) -> dict:
        try:
            response = self.llm.invoke(self.prompt_template.format(ticker=ticker, text=text))
            clean_content = response.content.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_content)
        except Exception:
            return {"target_ticker": ticker, "fundamental": False, "event_family": "Retail Speculation", "sentiment": -0.5, "confidence": 0.1}

