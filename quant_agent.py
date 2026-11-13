import pandas as pd

class QuantAgent:
    def __init__(self, window=20):
        self.window = window

    def calculate_metrics(self, df):
        if len(df) < self.window:
            return df
        
        df['mean'] = df['close'].rolling(window=self.window).mean()
        df['std'] = df['close'].rolling(window=self.window).std()
        df['z_score'] = (df['close'] - df['mean']) / df['std']
        df['upper_band'] = df['mean'] + (1.5 * df['std'])
        df['lower_band'] = df['mean'] - (1.5 * df['std'])
        return df

    def get_signal(self, z_score):
        if pd.isna(z_score):
            return "HOLD"
        if z_score <= -1.5:
            return "BUY"
        elif z_score >= 1.5:
            return "SELL"
        return "HOLD"