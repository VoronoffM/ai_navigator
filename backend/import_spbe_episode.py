"""Refresh the offline SPBE episode from public MOEX ISS hourly candles.

Run from the repository root: python -m backend.import_spbe_episode
News excerpts are curated separately; this importer never generates prices.
"""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

MOSCOW = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parent.parent
START = int(datetime(2023, 11, 27, 10, tzinfo=MOSCOW).timestamp())


def fetch(client, url):
    rows, requests = [], []
    offset = 0
    columns = None
    while True:
        response = client.get(url, params={
            "from": "2023-11-06", "till": "2023-11-27", "interval": 60,
            "iss.meta": "off", "start": offset,
        })
        response.raise_for_status()
        block = response.json()["candles"]
        columns = block["columns"]
        requests.append({"url": str(response.url), "sha256": hashlib.sha256(response.content).hexdigest()})
        if not block["data"]:
            break
        rows.extend(dict(zip(columns, row)) for row in block["data"])
        offset += len(block["data"])
    # 09:00 rows are opening-auction observations, not a full continuous trading hour.
    bars = [dict(
        time=int(datetime.fromisoformat(row["begin"]).replace(tzinfo=MOSCOW).timestamp()),
        open=row["open"], high=row["high"], low=row["low"], close=row["close"],
        **({"volume": row["volume"]} if "volume" in row else {}), complete=True,
    ) for row in rows if datetime.fromisoformat(row["begin"]).hour != 9]
    assert bars and len({bar["time"] for bar in bars}) == len(bars)
    assert all(bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"] for bar in bars)
    return bars, requests


def main():
    with httpx.Client(timeout=30) as client:
        stock, stock_requests = fetch(client, "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/SPBE/candles.json")
        index, index_requests = fetch(client, "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX/candles.json")
    warmup_start = int(datetime(2023, 11, 24, tzinfo=MOSCOW).timestamp())
    output = {
        "ticker": "SPBE", "candles": [bar for bar in stock if bar["time"] >= warmup_start],
        "indexCandles": [bar for bar in index if bar["time"] >= warmup_start],
        "history": {
            "SPBE": [[bar["time"], bar["close"], bar["volume"]] for bar in stock if bar["time"] < START],
            "IMOEX": [[bar["time"], bar["close"]] for bar in index if bar["time"] < START],
        },
        "provenance": {
            "source": "Московская биржа · ISS", "timezone": "Europe/Moscow", "interval": 3600,
            "retrievedAt": datetime.now(timezone.utc).isoformat(),
            "requests": {"SPBE": stock_requests, "IMOEX": index_requests},
            "adjustment": "Исходные OHLCV, без корректировки и интерполяции.",
            "filter": "Исключены строки 09:00 с данными аукциона открытия. Последняя сделка часа может быть раньше его конца.",
        },
    }
    path = ROOT / "backend/data/episodes/spbe.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(output['candles'])} SPBE and {len(output['indexCandles'])} IMOEX candles to {path}")


if __name__ == "__main__":
    main()
