import pandas as pd

class QuantAgent:
    """
    Агент математического анализа.
    Отвечает за расчет индикаторов (Z-Score, Bollinger Bands).
    """
    def __init__(self, window=20):
        self.window = window

    def calculate_metrics(self, df):
        """Считает скользящую среднюю, стандартное отклонение и Z-Score."""
        if len(df) < self.window:
            return df
        
        # MA20 (Средняя за 20 часов)
        df['mean'] = df['close'].rolling(window=self.window).mean()
        # Стандартное отклонение
        df['std'] = df['close'].rolling(window=self.window).std()
        # Z-Score: на сколько сигм текущая цена отклонилась от средней
        df['z_score'] = (df['close'] - df['mean']) / df['std']
        # Границы Боллинджера (для визуализации)
        df['upper_band'] = df['mean'] + (1.5 * df['std'])
        df['lower_band'] = df['mean'] - (1.5 * df['std'])
        return df

    def get_signal(self, z_score):
        """Возвращает торговый сигнал на основе Z-Score."""
        if pd.isna(z_score):
            return "HOLD"
        if z_score <= -1.5:
            return "BUY"   # Перепроданность (аномально низкая цена)
        elif z_score >= 1.5:
            return "SELL"  # Перекупленность (аномально высокая цена)
        return "HOLD"