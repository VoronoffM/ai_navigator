from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

from backend.invest_mcp import InvestMCP
from backend.replay import HOUR, MOSCOW, Signal, benchmark_comparison, gazprom_data

CheckName = Literal["news", "market", "dividends", "reports"]
CHECKS: dict[CheckName, str] = {
    "news": "Новости",
    "market": "IMOEX",
    "dividends": "Дивиденды",
    "reports": "Отчётность",
}
CALENDAR_ONLY = "Отчётность была запланирована. Публикацию не удалось подтвердить."


class Material(BaseModel):
    id: str
    source: str | None
    publishedAt: datetime
    title: str
    text: str | None = None
    url: str | None = None

    @property
    def headline_only(self) -> bool:
        return not self.text

    def payload(self):
        return {**self.model_dump(mode="json"), "headlineOnly": self.headline_only}


@dataclass
class CheckResult:
    status: Literal["ok", "empty", "unavailable", "disabled"]
    reason: str | None = None
    facts: dict = field(default_factory=dict)
    materials: list[Material] = field(default_factory=list)

    def payload(self):
        return {
            "status": self.status, "reason": self.reason, "facts": self.facts,
            "materials": [item.payload() for item in self.materials],
        }


Check = Callable[[Signal], Awaitable[CheckResult]]


def as_of(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.utcoffset() is not None else None
    except ValueError:
        return None


def exchange_day(value: str | None) -> date | None:
    if not value:
        return None
    if len(value) == 10:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if moment := as_of(value):
        return moment.astimezone(MOSCOW).date()
    return None


def safe_url(value: str | None) -> str | None:
    if value:
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username:
            return value
    return None


def market_result(event: Signal, candles: list[dict]) -> CheckResult:
    comparison = benchmark_comparison(candles, int(event.intervalStart.timestamp()), int(event.intervalEnd.timestamp()))
    if comparison is None:
        return CheckResult("empty", "Нет двух завершённых часовых свечей IMOEX с теми же границами.")
    return CheckResult("ok", facts={"comparison": comparison})


def dividend_result(event: Signal, rows: list[dict]) -> CheckResult:
    facts = []
    materials = []
    for row in rows:
        declared_day = exchange_day(row.get("declaredDate"))
        buy_day = exchange_day(row.get("lastBuyDate"))
        created = as_of(row.get("createdAt"))
        if not declared_day or not buy_day or not created:
            continue
        # A calendar date alone does not establish the intraday availability of an announcement.
        declared = as_of(row["declaredDate"]) or datetime.combine(declared_day, time.max, MOSCOW)
        if max(declared, created) > event.detectedAt:
            continue
        event_day = event.detectedAt.astimezone(MOSCOW).date()
        if not event_day - timedelta(days=7) <= buy_day <= event_day + timedelta(days=7):
            continue
        amount = Decimal(row["dividendNet"]["value"])
        if not amount.is_finite() or amount <= 0:
            continue
        currency = row["dividendNet"]["currency"]
        fact = {
            "amount": float(amount), "currency": currency, "declaredDate": declared_day.isoformat(),
            "lastBuyDate": buy_day.isoformat(), "recordCreatedAt": created.isoformat(), "source": "T-Invest MCP",
        }
        # A gap needs a verified session start and the actual close on the last eligible day.
        last_close = row.get("closePrice") or {}
        if (event.sessionStart == event.intervalStart and event.previousSessionDate == buy_day and buy_day < event_day
                and currency.lower() == "rub" and (last_close.get("currency") or "").lower() == "rub"
                and last_close.get("value") and event.open is not None and event.open > 0):
            close = Decimal(last_close["value"])
            gap = close - Decimal(str(event.open))
            if close.is_finite() and close == Decimal(str(event.previousClose)) and abs(gap - amount) <= amount * Decimal("0.2"):
                fact["possibleDividendGap"] = {"gap": float(gap), "referenceClose": float(close)}
        material = Material(
            id=f"mcp-dividend-{event.ticker}-{declared_day}-{buy_day}", source="T-Invest MCP",
            publishedAt=max(declared, created), title=f"Дивидендная запись {event.ticker}",
            text=f"Объявлено {declared_day}. Выплата {amount} {currency} на акцию. Последний день покупки {buy_day}.",
        )
        facts.append({**fact, "materialId": material.id})
        materials.append(material)
    if facts:
        return CheckResult("ok", facts={"payments": facts}, materials=materials)
    return CheckResult("empty", "Нет подходящих записей о выплате с датами, доступными к сигналу.")


def report_result(event: Signal, rows: list[dict], publications: list[Material] | None = None) -> CheckResult:
    entries = []
    event_day = event.detectedAt.astimezone(MOSCOW).date()
    for row in rows:
        created = as_of(row.get("createdAt"))
        scheduled = exchange_day(row.get("reportDate"))
        if created and created <= event.detectedAt and scheduled == event_day:
            entries.append({
                "scheduledDate": scheduled.isoformat(), "createdAt": created.isoformat(),
                "periodYear": row.get("periodYear"), "periodNum": row.get("periodNum"),
                "periodType": row.get("periodType"), "source": "T-Invest MCP",
            })
    materials = [item for item in publications or [] if item.publishedAt <= event.detectedAt]
    if entries or materials:
        return CheckResult("ok", CALENDAR_ONLY if not materials else None, {"calendar": entries}, materials)
    return CheckResult("empty", "Нет записи календаря, доступность которой подтверждена к моменту сигнала.")


class ReplayChecks:
    def __init__(self, news: dict | None):
        self.article = Material.model_validate(news) if news else None
        self.data = gazprom_data()

    async def news(self, event: Signal) -> CheckResult:
        if self.article and event.intervalStart <= self.article.publishedAt <= event.detectedAt:
            return CheckResult("ok", materials=[self.article])
        return CheckResult("empty", "В проверенной ленте подходящих новостей не найдено.")

    async def market(self, event: Signal) -> CheckResult:
        return market_result(event, self.data["IMOEX"])

    async def dividends(self, event: Signal) -> CheckResult:
        result = dividend_result(event, self.data.get("dividends", []))
        if self.article and self.article.publishedAt <= event.detectedAt:
            return CheckResult("ok", facts={
                **result.facts,
                "recommendation": "Совет директоров рекомендовал не выплачивать дивиденды за 2024 год.",
                "announcedAt": self.article.publishedAt.isoformat(), "materialId": self.article.id,
            }, materials=[self.article, *result.materials])
        return result

    async def reports(self, event: Signal) -> CheckResult:
        return report_result(event, self.data.get("reports", []), [
            Material.model_validate(item) for item in self.data.get("reportPublications", [])
        ])


class LiveChecks:
    """Source adapter for recent events. The pilot only exposes the replay entry point."""
    def __init__(self, mcp: InvestMCP):
        self.mcp = mcp

    async def news(self, event: Signal) -> CheckResult:
        materials = []
        cursor = None
        # Bound the scan in addition to the orchestrator deadline.
        for _ in range(3):
            args = {"instrumentId": event.ticker, "limit": 50}
            if cursor:
                args["cursor"] = cursor
            result = await self.mcp.call("invest_get_news", args)
            dates = []
            for row in result.get("items", []):
                published_at = as_of(row.get("ts"))
                if published_at is None:
                    continue
                dates.append(published_at)
                if not event.intervalStart <= published_at <= event.detectedAt or not row.get("title"):
                    continue
                materials.append(Material(
                    id=f"mcp-news-{row['id']}", source=row.get("source") or None, publishedAt=published_at,
                    title=row["title"], text=(row.get("content") or "").strip() or None,
                    url=safe_url(row.get("url")),
                ))
            cursor = result.get("nextCursor") if result.get("hasNext") else None
            if not cursor or (dates and min(dates) < event.intervalStart):
                break
        if materials:
            return CheckResult("ok", materials=materials)
        if cursor and not (dates and min(dates) < event.intervalStart):
            return CheckResult("unavailable", "Не удалось просмотреть всё окно новостей.")
        return CheckResult("empty", "В проверенной ленте подходящих новостей не найдено.")

    async def market(self, event: Signal) -> CheckResult:
        result = await self.mcp.call("invest_get_candles", {
            "instrumentId": "IMOEX_TQBR", "interval": "CANDLE_INTERVAL_HOUR",
            "from": (event.intervalStart - timedelta(seconds=HOUR)).astimezone(UTC).isoformat(),
            "to": event.intervalEnd.astimezone(UTC).isoformat(),
        })
        candles = [
            {"time": int(datetime.fromisoformat(row["time"]).timestamp()),
             "close": row["close"]["value"], "complete": row.get("isComplete") is True}
            for row in result.get("candles", [])
        ]
        return market_result(event, candles)

    async def dividends(self, event: Signal) -> CheckResult:
        result = await self.mcp.call("invest_get_share_dividends", {
            "instrumentId": f"{event.ticker}_TQBR",
            "from": (event.detectedAt - timedelta(days=8)).astimezone(UTC).isoformat(),
            "to": (event.detectedAt + timedelta(days=8)).astimezone(UTC).isoformat(),
        })
        return dividend_result(event, result.get("dividends", []))

    async def reports(self, event: Signal) -> CheckResult:
        start = event.detectedAt.astimezone(MOSCOW).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.mcp.call("invest_get_instrument_reports", {
            "instrumentId": f"{event.ticker}_TQBR", "from": start.astimezone(UTC).isoformat(),
            "to": (start + timedelta(days=1)).astimezone(UTC).isoformat(),
        })
        return report_result(event, result.get("events", []))
