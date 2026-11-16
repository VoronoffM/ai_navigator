import time
import pandas as pd
from datetime import datetime, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, MoneyValue

class MarketAgent:
    def __init__(self, token):
        self.token = token

    def _get_price(self, q):
        return q.units + q.nano / 1e9

    def _safe_call(self, func, *args, **kwargs):
        for attempt in range(3):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    time.sleep(2)
                elif attempt == 2:
                    raise e
                else:
                    time.sleep(1)

    def get_instruments_info(self, tickers):
        instruments_map = {}
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            shares = self._safe_call(client.instruments.shares)
            for t in tickers:
                info = next((s for s in shares.instruments if s.ticker == t), None)
                if info: 
                    instruments_map[t] = {"figi": info.figi, "lot": info.lot}
        return instruments_map

    def get_trading_status(self, figi):
        try:
            with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
                response = self._safe_call(client.market_data.get_trading_status, instrument_id=figi)
                return response.trading_status
        except Exception:
            return "UNKNOWN"

    def get_candles(self, figi, days=7):
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            now = datetime.utcnow()
            candles = self._safe_call(
                client.market_data.get_candles, 
                figi=figi, from_=now - timedelta(days=days), to=now, 
                interval=CandleInterval.CANDLE_INTERVAL_HOUR
            )
            data = [{
                "time": c.time, "open": self._get_price(c.open), "high": self._get_price(c.high), 
                "low": self._get_price(c.low), "close": self._get_price(c.close)
            } for c in candles.candles if c.is_complete]
            return pd.DataFrame(data)

    def get_candles_period(self, figi, interval, from_date, to_date):
        """Загружает свечи за указанный исторический период (для MCP-кейсов)."""
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            candles = self._safe_call(
                client.market_data.get_candles,
                figi=figi,
                from_=from_date,
                to=to_date,
                interval=interval
            )
            data = [{
                "time": c.time, "open": self._get_price(c.open), "high": self._get_price(c.high), 
                "low": self._get_price(c.low), "close": self._get_price(c.close)
            } for c in candles.candles if c.is_complete]
            return pd.DataFrame(data)

    def get_portfolio_and_account(self):
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