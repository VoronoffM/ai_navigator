# Терминал: touch market_agent.py && open -e market_agent.py
import time
from datetime import datetime, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, MoneyValue
from t_tech.invest.exceptions import RequestError
import pandas as pd

class MarketAgent:
    """Агент для работы с API Т-Инвестиций. Отвечает за свечи и портфель."""
    def __init__(self, token):
        self.token = token

    def _get_price(self, q):
        # Конвертирует формат Quotation (units + nano) в обычный float
        return q.units + q.nano / 1e9

    def _safe_call(self, func, *args, **kwargs):
        # Защита от Rate Limit (429) и временных сбоев сети (3 попытки)
        for attempt in range(3):
            try:
                return func(*args, **kwargs)
            except RequestError as e:
                if e.status_code == 429:
                    time.sleep(2) # Ждем, если API сказал "слишком много запросов"
                elif attempt == 2:
                    raise e
                else:
                    time.sleep(1)

    def get_candles(self, figi, days=7):
        # Качает часовые свечи за указанный период
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            now = datetime.utcnow()
            candles = self._safe_call(
                client.market_data.get_candles, 
                figi=figi, from_=now - timedelta(days=days), to=now, 
                interval=CandleInterval.CANDLE_INTERVAL_HOUR
            )
            # Оставляем только завершенные свечи и формируем DataFrame
            data = [{
                "time": c.time, "open": self._get_price(c.open), "high": self._get_price(c.high), 
                "low": self._get_price(c.low), "close": self._get_price(c.close)
            } for c in candles.candles if c.is_complete]
            return pd.DataFrame(data)

    def get_portfolio_and_account(self):
        # Возвращает (кэш, позиции, id_счета). Если счета нет - создает и пополняет.
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            accounts = self._safe_call(client.users.get_accounts)
            if not accounts.accounts:
                acc_id = client.sandbox.open_sandbox_account().account_id
                client.sandbox.sandbox_pay_in(account_id=acc_id, amount=MoneyValue(currency="rub", units=100000, nano=0))
            else:
                acc_id = accounts.accounts[0].id
            
            portfolio = self._safe_call(client.operations.get_portfolio, account_id=acc_id)
            cash, positions = 0, {}
            for pos in portfolio.positions:
                if pos.instrument_type == "currency" and pos.figi == "RUB000UTSTOM":
                    cash = pos.quantity.units
                elif pos.ticker:
                    positions[pos.ticker] = {"count": pos.quantity.units, "current_price": self._get_price(pos.current_price)}
            return cash, positions, acc_id

    def get_figi_map(self, tickers):
        # Получает уникальные ID (FIGI) для списка тикеров
        figi_map = {}
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            shares = self._safe_call(client.instruments.shares)
            for t in tickers:
                info = next((s for s in shares.instruments if s.ticker == t), None)
                if info: figi_map[t] = info.figi
        return figi_map