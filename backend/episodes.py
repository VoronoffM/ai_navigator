"""Versioned, offline episode library. Labels and expected outcomes stay outside model context."""
import json
from datetime import datetime, timedelta
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from random import Random

from backend.replay import (
    HOUR, MOSCOW, NEWS, REPLAY_START, Signal, change_percent,
    gazprom_data, gazprom_replay, gazprom_signal, moscow_time,
)
from backend.replay_models import replay_scores

VERSION = "1"
GAZP_ID = "gazp-2025-05-22"
EPISODES = [
    dict(id=GAZP_ID, ticker="GAZP", name="Газпром", title="Падение без дивидендов",
         date="22 мая 2025", kind="historical", description="Газпром (GAZP): рекомендация совета директоров не выплачивать дивиденды за 2024 год.",
         source="T-Invest MCP", note="Сохранённые часовые свечи и публикация Интерфакса. Данные открываются по историческому времени."),
    dict(id="vtbr-2025-04-28", ticker="VTBR", name="ВТБ", title="Рост на дивидендах",
         date="28 апреля 2025", kind="historical", description="ВТБ (VTBR): рекомендация выплатить дивиденды на фоне резкого роста котировок.",
         source="Московская биржа · ISS", note="Исходные часовые цены. Раскрытие в 13:39 доступно к закрытию свечи в 14:00. Полная новостная лента не воспроизводится."),
    dict(id="belu-2024-08-22", ticker="BELU", name="НоваБев Групп", title="BELU · Дополнительные акции",
         date="22 августа 2024", kind="historical", description="Возобновление торгов после распределения дополнительных акций.",
         source="Московская биржа · ISS", note="Исходные цены без корректировки. Перерыв в торгах 16–21 августа. Аукционный час 09:00 исключён; новые акции временно недоступны для торгов. Разрыв цены не равен убытку портфеля."),
    dict(id="spbe-2023-11-27", ticker="SPBE", name="СПБ Биржа", title="Падение на слухах о банкротстве",
         date="27 ноября 2023", kind="historical", description="Акции СПБ Биржи резко падают после сообщений о банкротстве. Компания заявляет, что не подавала такого заявления.",
         source="Московская биржа · ISS", note="Реальные часовые свечи SPBE и IMOEX. Сообщение о заявлении в суд — 10:13, опровержение Интерфакса — 10:38. Итоги более позднего расследования в контекст не включены."),
    dict(id="noise-calm", ticker="DEMO", name="Учебный инструмент", title="Шум · Обычные колебания",
         date="Учебная сессия", kind="synthetic", description="Небольшие изменения цены и объёма без существенных публикаций.",
         source="Симуляция", note="Вымышленные цены и индекс. Повторный запуск воспроизводит те же данные. Срабатывание зависит от правил Agent Studio."),
    dict(id="noise-impulse", ticker="DEMO", name="Учебный инструмент", title="Падение без новостей",
         date="Учебная сессия", kind="synthetic", description="Учебный инструмент DEMO: краткое падение цены; в учебной ленте нет подходящих сообщений.",
         source="Симуляция", note="Вымышленные цены и индекс. Отсутствие найденной новости само по себе не доказывает, что движение — шум."),
    dict(id="noise-stale", ticker="DEMO", name="Учебный инструмент", title="Шум · Старая новость",
         date="Учебная сессия", kind="synthetic", description="Ценовой импульс и новый пересказ события месячной давности.",
         source="Симуляция", note="Вымышленные данные. Проверка того, связывает ли агент движение с публикацией только по совпадению времени."),
    dict(id="noise-unavailable", ticker="DEMO", name="Учебный инструмент", title="Шум · Лента недоступна",
         date="Учебная сессия", kind="synthetic", description="Ценовой импульс при недоступном источнике новостей.",
         source="Симуляция", note="Вымышленные данные. Недоступность источника не означает отсутствия новостей или причины движения."),
]
CATALOG = {item["id"]: item for item in EPISODES}
# Keep edge cases available to internal checks without crowding the demonstration picker.
PUBLIC_EPISODE_IDS = (GAZP_ID, "vtbr-2025-04-28", "spbe-2023-11-27")


def catalog():
    return [{**CATALOG[episode_id], "datasetVersion": VERSION, "interval": "1h"}
            for episode_id in PUBLIC_EPISODE_IDS]


def material(id, source, time, title, text, url=None, checks=("news",), kind="fact"):
    return dict(id=id, source=source, publishedAt=time, availableAt=time, title=title,
                text=text, url=url, kind=kind, checks=list(checks))


@lru_cache(maxsize=16)
def episode_data(episode_id):
    if episode_id not in CATALOG:
        raise KeyError(episode_id)
    if episode_id == GAZP_ID:
        return {**gazprom_data(), "materials": [{**NEWS, "availableAt": NEWS["publishedAt"], "checks": ["news", "dividends"]}],
                "start": REPLAY_START, "recommendation": NEWS["title"], "recommendationId": NEWS["id"]}
    if CATALOG[episode_id]["kind"] == "synthetic":
        return synthetic_data(episode_id)
    tag = episode_id.split("-", 1)[0]
    raw = json.loads((Path(__file__).with_name("data") / "episodes" / f"{tag}.json").read_text())
    ticker = raw["ticker"]
    data = {ticker: raw["candles"], "IMOEX": raw["indexCandles"], "history": raw["history"], "provenance": raw["provenance"]}
    if tag == "vtbr":
        article = material("vtbr-disclosure-20250428", "Раскрытие эмитента · ВТБ", "2025-04-28T13:39:00+03:00",
            "Набсовет ВТБ рекомендовал дивиденды 25,58 ₽ на обыкновенную акцию за 2024 год",
            "Наблюдательный совет рекомендовал собранию акционеров выплатить 25,58 рубля на обыкновенную акцию за 2024 год. Это рекомендация, а не состоявшаяся выплата.",
            "https://www.e-disclosure.ru/portal/event.aspx?EventId=9E-C05nxQ30WwcB6uIFpXFQ-B-B", checks=("news", "dividends"))
        data.update(start=int(datetime.fromisoformat("2025-04-28T12:00:00+03:00").timestamp()),
                    materials=[article], recommendation=article["title"], recommendationId=article["id"])
    elif tag == "spbe":
        # Only the unchanged headline is used from the evolving 10:13 article.
        # Do not backdate its later additions or the 2024 regulator findings.
        headline = material("spbe-kommersant-6364432", "Коммерсантъ", "2023-11-27T10:13:00+03:00",
            "Арбитражный суд зарегистрировал заявление о банкротстве СПБ Биржи", None,
            "https://www.kommersant.ru/doc/6364432", kind="unverified")
        denial = material("spbe-interfax-933355", "Интерфакс", "2023-11-27T10:38:00+03:00",
            '"СПБ биржа" опровергла сообщение о подаче документов на банкротство',
            "Биржа отрицает подачу заявления о собственном банкротстве и сообщает об устойчивом финансовом положении. По данным публикации, в судебной картотеке появилась запись о заявлении от 24 ноября; сведения о кредиторе не приведены.",
            "https://www.interfax.ru/business/933355")
        data.update(start=int(datetime.fromisoformat("2023-11-27T10:00:00+03:00").timestamp()),
                    materials=[headline, denial])
    else:
        article = material("belu-interfax-977582", "Интерфакс", "2024-08-22T10:27:00+03:00",
            "Торги BELU возобновлены после дополнительной эмиссии; проводится дискретный аукцион",
            "22 августа торги акциями НоваБев возобновлены после остановки с 16 августа в связи с дополнительной эмиссией. Из-за снижения цены биржа проводит дискретный аукцион с 10:10 до 10:40.",
            "https://www.interfax.ru/business/977582")
        # Use dated prior disclosure as active corporate context. Do not invent a publication time for the FAQ.
        corporate = material("belu-corporate-969335", "Интерфакс", "2024-07-04T17:32:00+03:00",
            "Акционеры НоваБев одобрили восьмикратное увеличение количества акций",
            "Акционеры одобрили увеличение капитала: семь новых акций распределяются на одну прежнюю без изменения долей владельцев. Исходная цена одной акции после распределения не сопоставима напрямую с ценой до него.",
            "https://www.interfax.ru/business/969335")
        data.update(start=int(datetime.fromisoformat("2024-08-22T10:00:00+03:00").timestamp()), materials=[corporate, article])
    return data


def synthetic_data(episode_id):
    rng = Random(20261119)
    start = datetime(2026, 11, 18, 10, tzinfo=MOSCOW)
    bars, index = [], []
    close, index_close = 100., 2500.
    for offset in range(-18, 1):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for hour in range(10, 19):
            moment = day.replace(hour=hour)
            t = int(moment.timestamp())
            previous = close
            change = rng.choice([-1, 1]) * rng.uniform(.0005, .002)
            if offset == 0 and hour == 13 and episode_id != "noise-calm":
                change = -.038
            elif offset == 0 and hour == 14 and episode_id != "noise-calm":
                change = .036
            close = round(close * (1 + change), 4)
            volume = int(rng.uniform(8500, 11500))
            if offset == 0 and hour in (13, 14) and episode_id != "noise-calm":
                volume *= 5
            bars.append(dict(time=t, open=previous, close=close, high=max(previous, close)+.04,
                             low=min(previous, close)-.04, volume=volume, complete=True))
            previous_index = index_close
            index_close = round(index_close * (1 + rng.uniform(-.0008, .0008)), 4)
            index.append(dict(time=t, open=previous_index, close=index_close, high=max(previous_index,index_close)+1,
                              low=min(previous_index,index_close)-1, complete=True))
    epoch = int(start.timestamp())
    visible = [bar for bar in bars if bar["time"] >= epoch - 86400]
    data = {"DEMO": visible, "IMOEX": [bar for bar in index if bar["time"] >= epoch-86400],
            "start": epoch, "materials": [],
            "history": {"DEMO": [[bar["time"],bar["close"],bar["volume"]] for bar in bars if bar["time"] < epoch],
                        "IMOEX": [[bar["time"],bar["close"]] for bar in index if bar["time"] < epoch]}}
    if episode_id == "noise-stale":
        data["materials"] = [material("demo-old-news", "Учебная лента", "2026-11-18T13:10:00+03:00",
            "Повторная публикация: компания открыла офис месяц назад",
            "Это вымышленная учебная публикация. Офис открыт 18 октября; сообщение 18 ноября лишь повторяет старое событие. Новых обстоятельств в нём нет.", kind="unverified")]
    if episode_id == "noise-unavailable":
        data["newsUnavailable"] = True
    return data


def visible_materials(episode_id, detected_at, check="news"):
    return [entry for entry in episode_data(episode_id)["materials"]
            if check in entry.get("checks", ["news"])
            and datetime.fromisoformat(entry["publishedAt"]).timestamp() <= detected_at
            and datetime.fromisoformat(entry.get("availableAt", entry["publishedAt"])).timestamp() <= detected_at]


@lru_cache(maxsize=16)
def replay_episode(episode_id):
    meta = CATALOG[episode_id]
    data = episode_data(episode_id)
    if episode_id == GAZP_ID:
        episode = gazprom_replay()
        return {**episode, "metadata": {**meta, "datasetVersion": VERSION, "interval": "1h"}}
    candles = data[meta["ticker"]]
    start = data["start"]
    scores = replay_scores(data["history"], candles, data["IMOEX"], start, HOUR, MOSCOW, meta["ticker"])
    frames = []
    for previous, current in pairwise(candles):
        if current["time"] < start or not (previous["complete"] and current["complete"]):
            continue
        time = current["time"]
        detected = time + HOUR
        gap = time - previous["time"] != HOUR
        # Session gaps are eligible for the fixed price rule; hourly statistical scores stay unavailable.
        frame = dict(event_id=f"{episode_id}-v{VERSION}-{detected}", ticker=meta["ticker"],
                     rule="Изменение к предыдущей торговой свече" if gap else "Проверка на закрытии часовой свечи",
                     candleTime=time, detectedAt=detected, previousClose=previous["close"], close=current["close"],
                     changePercent=float(change_percent(previous["close"], current["close"])),
                     indexChangePercent=None, news=None, comparisonKind="session-gap" if gap else "hour",
                     previousCloseAt=previous["time"]+HOUR, previousSessionDate=moscow_time(previous["time"]).date().isoformat())
        if not gap:
            frame.update(scores.get(time, {}))
        else:
            frame.update(priceZ=None, marketZ=None, volumeRatio=scores.get(time, {}).get("volumeRatio"))
        entries = visible_materials(episode_id, detected)
        frame["news"] = entries[0] if entries else None
        frames.append(frame)
    event = next((item for item in frames if abs(item["changePercent"]) >= 2), None)
    return dict(metadata={**meta, "datasetVersion": VERSION, "interval": "1h"}, candles=candles,
                warmupCount=sum(bar["time"] < start for bar in candles), thresholdPercent=2, event=event, frames=frames)


def episode_signal(event_id):
    # Preserve the existing public event identifiers for GAZP.
    legacy = gazprom_signal(event_id)
    if legacy:
        return legacy.model_copy(update={"episodeId": GAZP_ID, "datasetVersion": VERSION, "dataSource": "T-Invest MCP"})
    for episode_id, meta in CATALOG.items():
        if episode_id == GAZP_ID or not event_id.startswith(f"{episode_id}-v{VERSION}-"):
            continue
        frame = next((item for item in replay_episode(episode_id)["frames"] if item["event_id"] == event_id), None)
        if frame is None:
            return None
        bar = next(bar for bar in replay_episode(episode_id)["candles"] if bar["time"] == frame["candleTime"])
        return Signal(event_id=event_id, ticker=frame["ticker"], rule=frame["rule"],
            detectedAt=moscow_time(frame["detectedAt"]), intervalStart=moscow_time(frame["candleTime"]),
            intervalEnd=moscow_time(frame["detectedAt"]), previousClose=frame["previousClose"], close=frame["close"],
            open=bar["open"], high=bar["high"], low=bar["low"], volume=bar.get("volume"),
            changePercent=frame["changePercent"], episodeId=episode_id, datasetVersion=VERSION,
            dataSource=meta["source"], synthetic=meta["kind"] == "synthetic",
            comparisonKind=frame["comparisonKind"], previousCloseAt=moscow_time(frame["previousCloseAt"]),
            previousSessionDate=frame["previousSessionDate"])
    return None
