from collections import defaultdict, deque
from datetime import datetime
from math import sqrt
from statistics import mean, median, stdev


def replay_scores(history, candles, index_candles, start, hour, timezone, ticker="GAZP"):
    """Score each closed replay candle against observations strictly before it."""
    prices = {time: close for time, close, _ in history[ticker]}
    volumes = {time: volume for time, _, volume in history[ticker]}
    index = dict(history["IMOEX"])
    prices.update((bar["time"], bar["close"]) for bar in candles if bar["complete"])
    volumes.update((bar["time"], bar["volume"]) for bar in candles if bar["complete"] and "volume" in bar)
    index.update((bar["time"], bar["close"]) for bar in index_candles if bar["complete"])
    visible = {bar["time"] for bar in candles if bar["complete"] and bar["time"] >= start}
    by_hour = defaultdict(lambda: deque(maxlen=10))
    spreads = deque(maxlen=40)
    variance = 0.0
    returns = 0
    scores = {}

    for time, close in sorted(prices.items()):
        volume = volumes.get(time)
        session_hour = datetime.fromtimestamp(time, timezone).hour
        past_volumes = by_hour[session_hour]
        baseline = median(past_volumes) if len(past_volumes) >= 5 else 0
        if volume is not None:
            past_volumes.append(volume)

        previous = prices.get(time - hour)
        if previous is None or previous <= 0:
            continue
        change = 100 * (close - previous) / previous
        price_z = change / sqrt(variance) if returns >= 20 and variance > 0 else None
        variance = 0.97 * variance + 0.03 * change**2 if returns else change**2
        returns += 1

        index_close, index_previous = index.get(time), index.get(time - hour)
        index_change = None
        market_z = None
        if index_close is not None and index_previous is not None and index_previous > 0:
            index_change = 100 * (index_close - index_previous) / index_previous
            spread = change - index_change
            if len(spreads) >= 20:
                scale = stdev(spreads)
                if scale > 0:
                    market_z = (spread - mean(spreads)) / scale
            spreads.append(spread)

        if time in visible:
            scores[time] = {
                "priceZ": price_z,
                "volumeRatio": volume / baseline if volume is not None and baseline > 0 else None,
                "marketZ": market_z,
                "indexChangePercent": index_change,
            }
    return scores
