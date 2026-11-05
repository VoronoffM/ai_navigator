import numpy as np

class QuantSignalValidator:
    def __init__(self, window_size: int = 5):
        self.window_size = window_size

    def calculate_z_score(self, price_history: list, current_price: float) -> float:
        if len(price_history) < self.window_size:
            return 0.0
        prices = np.array(price_history[-self.window_size:])
        mean = np.mean(prices)
        std = np.std(prices)
        if std == 0:
            return 0.0
        return float((current_price - mean) / std)

    def evaluate_opportunity(self, z_score: float, volume_shock: float, sentiment: float) -> dict:
        if z_score <= -2.5 and volume_shock > 2.0 and sentiment > -0.3:
            return {"decision": "BUY_RECOMMENDED"}
        return {"decision": "HOLD"}

