import time
import pandas as pd
from datetime import datetime, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, MoneyValue
from t_tech.invest.exceptions import RequestError

class MarketAgent:
    """
    Агент взаимодействия с API Т-Инвестиций.
    Отвечает за получение исторических данных, портфеля и справочной информации.
    """
    def __init__(self, token):
        self.token = token

    def _get_price(self, q):
        """Конвертирует формат Quotation (units + nano) в обычный float."""
        return q.units + q.nano / 1e9

    def _safe_call(self, func, *args, **kwargs):
        """
        Обертка для отказоустойчивости API.
        Обрабатывает лимиты (429) и сетевые сбои с помощью повторных попыток.
        """
        for attempt in range(3):
            try:
                return func(*args, **kwargs)
            except RequestError as e:
                if e.status_code == 429:
                    time.sleep(2) # Ждем при превышении лимита запросов
                elif attempt == 2:
                    raise e # Пробрасываем ошибку, если 3 попытки не удались
                else:
                    time.sleep(1)

    def get_instruments_info(self, tickers):
        """
        СЕНЬОР-ПРАВИЛО: Динамически получаем лотность и FIGI. 
        Никакого хардкода, так как у каждой акции свои параметры (например, у Газпрома лот 10, у Лукойла 1).
        """
        instruments_map = {}
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            shares = self._safe_call(client.instruments.shares)
            for t in tickers:
                info = next((s for s in shares.instruments if s.ticker == t), None)
                if info: 
                    instruments_map[t] = {
                        "figi": info.figi,
                        "lot": info.lot,
                    }
        return instruments_map

    def get_trading_status(self, figi):
        """
        Проверяет, идут ли сейчас торги по инструменту.
        Спасает от ошибки 30079 (торги закрыты) при попытке купить ночью или в выходные.
        """
        try:
            with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
                response = self._safe_call(
                    client.market_data.get_trading_status,
                    instrument_id=figi
                )
                return response.trading_status
        except Exception:
            return "UNKNOWN"

    def get_candles(self, figi, days=7):
        """Загружает часовые свечи за указанный период."""
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            now = datetime.utcnow()
            candles = self._safe_call(
                client.market_data.get_candles, 
                figi=figi, from_=now - timedelta(days=days), to=now, 
                interval=CandleInterval.CANDLE_INTERVAL_HOUR
            )
            # Оставляем только завершенные свечи (is_complete)
            data = [{
                "time": c.time, "open": self._get_price(c.open), "high": self._get_price(c.high), 
                "low": self._get_price(c.low), "close": self._get_price(c.close)
            } for c in candles.candles if c.is_complete]
            return pd.DataFrame(data)

    def get_portfolio_and_account(self):
        """Возвращает (кэш, позиции, id_счета). Создает и пополняет счет при необходимости."""
        with Client(self.token, target=INVEST_GRPC_API_SANDBOX) as client:
            accounts = self._safe_call(client.users.get_accounts)
            if not accounts.accounts:
                # Если счета нет, создаем песочницу и кидаем 100к виртуальных рублей
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