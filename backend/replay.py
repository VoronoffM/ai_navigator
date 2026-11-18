import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from pydantic import BaseModel
from backend.replay_models import replay_scores


HOUR = 3600
MOSCOW = timezone(timedelta(hours=3))
RULE = "Снижение на 2% или больше между закрытиями соседних часовых свечей"
THRESHOLD_PERCENT = Decimal("2")
REPLAY_START = int(datetime.fromisoformat("2025-05-22T13:00:00+03:00").timestamp())
NEWS = {
    "id": "interfax-1027187",
    "kind": "fact",
    "source": "Интерфакс",
    "publishedAt": "2025-05-22T15:46:00+03:00",
    "title": "Совет директоров Газпрома рекомендовал не выплачивать дивиденды за 2024 год",
    "url": "https://www.interfax.ru/business/1027187",
    "text": "Совет директоров рекомендовал годовому собранию акционеров Газпрома оставить прибыль за 2024 год нераспределённой и не выплачивать дивиденды.",
}


def change_percent(previous, current):
    previous = Decimal(str(previous))
    return (Decimal(str(current)) - previous) / previous * 100


def moscow_time(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, MOSCOW)


@lru_cache(maxsize=1)
def gazprom_data():
    return json.loads((Path(__file__).with_name("data") / "gazp-2025-05-22.json").read_text())


def benchmark_comparison(candles, start: int, end: int):
    if end - start != HOUR:
        return None
    closes = {bar["time"] + HOUR: Decimal(str(bar["close"])) for bar in candles if bar["complete"]}
    if any(key not in closes or not closes[key].is_finite() or closes[key] <= 0 for key in (start, end)):
        return None
    return {
        "ticker": "IMOEX",
        "previousClose": float(closes[start]),
        "close": float(closes[end]),
        "changePercent": float(change_percent(closes[start], closes[end])),
        "intervalStart": moscow_time(start).isoformat(),
        "intervalEnd": moscow_time(end).isoformat(),
        "source": "T-Invest MCP",
    }


@lru_cache(maxsize=1)
def gazprom_replay():
    data = gazprom_data()
    candles = data["GAZP"]
    warmup_count = sum(bar["time"] < REPLAY_START for bar in candles)
    news_time = datetime.fromisoformat(NEWS["publishedAt"]).timestamp()
    event = None

    for previous, current in pairwise(candles[max(0, warmup_count - 1):]):
        previous_time, candle_time = previous["time"], current["time"]
        if candle_time - previous_time != HOUR or not (previous["complete"] and current["complete"]):
            continue
        change = change_percent(previous["close"], current["close"])
        if change > -THRESHOLD_PERCENT:
            continue
        detected_at = candle_time + HOUR
        benchmark = benchmark_comparison(data["IMOEX"], candle_time, detected_at)
        event = {
            "event_id": f"gazp-tqbr-1h-{detected_at}",
            "ticker": "GAZP",
            "rule": RULE,
            "candleTime": candle_time,
            "detectedAt": detected_at,
            "changePercent": float(change),
            "previousClose": previous["close"],
            "close": current["close"],
            "indexChangePercent": benchmark["changePercent"] if benchmark else None,
            "news": NEWS if news_time <= detected_at else None,
        }
        break

    history = json.loads((Path(__file__).with_name("data") / "gazp-signal-history.json").read_text())
    scores = replay_scores(history, candles, data["IMOEX"], REPLAY_START, HOUR, MOSCOW)
    frames = []
    for previous, current in pairwise(candles):
        time = current["time"]
        if time not in scores or time - previous["time"] != HOUR or not previous["complete"]:
            continue
        detected_at = time + HOUR
        frames.append({
            "event_id": f"gazp-tqbr-1h-{detected_at}",
            "ticker": "GAZP",
            "rule": "Проверка моделей на закрытии часовой свечи",
            "candleTime": time,
            "detectedAt": detected_at,
            "changePercent": float(change_percent(previous["close"], current["close"])),
            "previousClose": previous["close"],
            "close": current["close"],
            "news": NEWS if news_time <= detected_at else None,
            **scores[time],
        })

    return {
        "candles": candles, "warmupCount": warmup_count, "thresholdPercent": float(THRESHOLD_PERCENT),
        "event": event, "frames": frames,
    }


class Signal(BaseModel):
    event_id: str
    ticker: str
    detectedAt: datetime
    intervalStart: datetime
    intervalEnd: datetime
    previousClose: float
    close: float
    open: float | None = None
    sessionStart: datetime | None = None
    previousSessionDate: date | None = None
    changePercent: float
    rule: str
    episodeId: str | None = None
    datasetVersion: str | None = None
    dataSource: str | None = None
    synthetic: bool = False
    previousCloseAt: datetime | None = None
    comparisonKind: str = "hour"


def gazprom_signal(event_id: str | None = None) -> Signal | None:
    episode = gazprom_replay()
    event = episode["event"]
    if event_id is not None and (event is None or event["event_id"] != event_id):
        event = next((frame for frame in episode["frames"] if frame["event_id"] == event_id), None)
    if event is None:
        return None
    return Signal(
        event_id=event["event_id"], ticker=event["ticker"], rule=event["rule"],
        detectedAt=moscow_time(event["detectedAt"]), intervalStart=moscow_time(event["candleTime"]),
        intervalEnd=moscow_time(event["detectedAt"]), previousClose=event["previousClose"],
        close=event["close"], changePercent=event["changePercent"],
    )
