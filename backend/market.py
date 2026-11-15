import asyncio
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

import httpx


SANDBOX_URL = "https://sandbox-invest-public-api.tbank.ru/rest/"
CONTRACT = "tinkoff.public.invest.api.contract.v1"
CLASS_CODE = "TQBR"
INTERVALS = {
    "1h": ("CANDLE_INTERVAL_HOUR", timedelta(days=14)),
    "1d": ("CANDLE_INTERVAL_DAY", timedelta(days=180)),
}


class Ticker(StrEnum):
    GAZP = "GAZP"
    SBER = "SBER"
    LKOH = "LKOH"
    ROSN = "ROSN"


class MarketError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.detail = {"code": code, "message": message}
        self.status = status


def price(quotation: dict) -> float:
    return int(quotation.get("units", 0)) + int(quotation.get("nano", 0)) / 1_000_000_000


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


class SandboxMarket:
    def __init__(self, client: httpx.AsyncClient, token: str):
        self.client = client
        self.token = token
        self.instruments: dict[Ticker, dict] = {}
        self.instrument_lock = asyncio.Lock()

    async def call(self, method: str, body: dict) -> dict:
        if not self.token:
            raise MarketError("missing_token", "Задайте TBANK_TOKEN на сервере и перезапустите его.", 503)

        try:
            response = await self.client.post(
                f"{CONTRACT}.{method}", json=body, headers={"Authorization": f"Bearer {self.token}"}
            )
        except httpx.TimeoutException as exc:
            raise MarketError("timeout", "Песочница Т‑Инвестиций не ответила вовремя.", 504) from exc
        except httpx.RequestError as exc:
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                raise MarketError(
                    "certificate",
                    "Не удалось проверить сертификат песочницы. Проверьте SSL_CERT_FILE в настройках сервера.",
                    503,
                ) from exc
            raise MarketError("connection", "Не удалось подключиться к песочнице Т‑Инвестиций.", 503) from exc

        if response.status_code in (401, 403):
            raise MarketError("access_denied", "Песочница отклонила запрос. Проверьте токен и его доступ.", 503)
        if response.status_code == 404:
            raise MarketError("not_found", "Песочница не нашла инструмент или запрошенные данные.", 404)
        if response.status_code == 429:
            raise MarketError("rate_limit", "Достигнут лимит запросов к песочнице. Повторите позже.", 503)
        if not response.is_success:
            raise MarketError("upstream", "Песочница вернула ошибку при запросе рыночных данных.")
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        except ValueError:
            pass
        raise MarketError("invalid_response", "Песочница вернула данные в неожиданном формате.")

    async def instrument(self, ticker: Ticker) -> dict:
        payload = await self.call("InstrumentsService/ShareBy", {
            "idType": "INSTRUMENT_ID_TYPE_TICKER",
            "classCode": CLASS_CODE,
            "id": ticker.value,
        })
        instrument = payload.get("instrument")
        if not instrument:
            raise MarketError("not_found", "Песочница не вернула сведения об акции.", 404)
        if (
            not isinstance(instrument, dict)
            or instrument.get("ticker") != ticker.value
            or not (instrument.get("uid") or instrument.get("figi"))
        ):
            raise MarketError("invalid_response", "Песочница вернула сведения об акции в неожиданном формате.")
        return instrument

    async def quotes(self) -> list[dict]:
        # Successful instrument lookups are reused by the minute-by-minute quote refresh.
        async with self.instrument_lock:
            missing = [ticker for ticker in Ticker if ticker not in self.instruments]
            results = await asyncio.gather(*(self.instrument(ticker) for ticker in missing), return_exceptions=True)
            issues = {}
            for ticker, result in zip(missing, results):
                if isinstance(result, MarketError):
                    issues[ticker] = result.detail
                elif isinstance(result, BaseException):
                    raise result
                else:
                    self.instruments[ticker] = result
            instruments = self.instruments.copy()

        quotes = {}
        quote_issue = None
        if instruments:
            try:
                symbols_by_id = {
                    identifier: ticker
                    for ticker, item in instruments.items()
                    for identifier in (item.get("uid"), item.get("figi"))
                    if identifier
                }
                ids = [item.get("uid") or item["figi"] for item in instruments.values()]
                payload = await self.call("MarketDataService/GetLastPrices", {"instrumentId": ids})
                for item in payload.get("lastPrices", []):
                    ticker = symbols_by_id.get(item.get("instrumentUid")) or symbols_by_id.get(item.get("figi"))
                    if not ticker or item.get("price") is None or not item.get("time"):
                        continue
                    quote = {"price": price(item["price"]), "time": timestamp(item["time"])}
                    if ticker not in quotes or quote["time"] > quotes[ticker]["time"]:
                        quotes[ticker] = quote
            except MarketError as exc:
                quote_issue = exc.detail
            except (KeyError, TypeError, ValueError, AttributeError):
                quote_issue = {"code": "invalid_response", "message": "Песочница вернула котировки в неожиданном формате."}

        rows = []
        for ticker in Ticker:
            item = instruments.get(ticker, {})
            rows.append({
                "ticker": ticker,
                "name": item.get("name"),
                "currency": item.get("currency"),
                "quote": None if quote_issue else quotes.get(ticker),
                "issue": issues.get(ticker) or quote_issue,
            })
        return rows

    async def candles(self, ticker: Ticker, interval: Literal["1h", "1d"]) -> list[dict]:
        api_interval, lookback = INTERVALS[interval]
        now = datetime.now(UTC).replace(microsecond=0)
        payload = await self.call("MarketDataService/GetCandles", {
            "instrumentId": f"{ticker.value}_{CLASS_CODE}",
            "from": (now - lookback).isoformat().replace("+00:00", "Z"),
            "to": now.isoformat().replace("+00:00", "Z"),
            "interval": api_interval,
        })
        try:
            candles = {}
            for item in payload.get("candles", []):
                time = int(timestamp(item["time"]).timestamp())
                candles[time] = {
                    "time": time,
                    "open": price(item["open"]),
                    "high": price(item["high"]),
                    "low": price(item["low"]),
                    "close": price(item["close"]),
                    "complete": item.get("isComplete", False),
                }
            return [candles[time] for time in sorted(candles)]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise MarketError("invalid_response", "Песочница вернула свечи в неожиданном формате.") from exc
