# Терминал: touch quant_agent.py && open -e quant_agent.py
import pandas as pd

class QuantAgent:
    """Агент математики. Считает Z-Score, средние и полосы."""
    def __init__(self, window=20):
        self.window = window

    def calculate_metrics(self, df):
        # Если данных меньше окна - вернуть как есть
        if len(df) < self.window:
            return df
        
        # Скользящая средняя за 20 часов
        df['mean'] = df['close'].rolling(window=self.window).mean()
        # Стандартное отклонение
        df['std'] = df['close'].rolling(window=self.window).std()
        # Z-Score: на сколько сигм текущая цена отклонилась от среднего
        df['z_score'] = (df['close'] - df['mean']) / df['std']
        # Полосы Боллинджера для визуализации
        df['upper_band'] = df['mean'] + (1.5 * df['std'])
        df['lower_band'] = df['mean'] - (1.5 * df['std'])
        return df

    def get_signal(self, z_score):
        # Вердикт робота на основе Z-Score
        if pd.isna(z_score):
            return "HOLD"
        if z_score <= -1.5:
            return "BUY"   # Цена сильно упала (перепроданность)
        elif z_score >= 1.5:
            return "SELL"  # Цена сильно выросла (перекупленность)
        return "HOLD"