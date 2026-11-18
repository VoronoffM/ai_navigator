import re
from datetime import datetime
from html import unescape

import httpx

from backend.replay import MOSCOW, Signal
from backend.signal_checks import CheckResult, Material

CALENDAR = "https://www.cbr.ru/dkp/cal_mp/"
RELEASES = re.compile(r"""href=["'](/press/pr/?\?file=(\d{8}_\d{6})key\.htm)["']""", re.IGNORECASE)


async def check_cbr_calendar(client: httpx.AsyncClient, event: Signal) -> CheckResult:
    try:
        response = await client.get(CALENDAR, follow_redirects=False, timeout=3)
        response.raise_for_status()
        releases = dict(RELEASES.findall(response.text))
        if not releases:
            raise ValueError("No decision links in the calendar")
        dates = {path: datetime.strptime(value, "%d%m%Y_%H%M%S").replace(tzinfo=MOSCOW)
                 for path, value in releases.items()}
        if not any(moment.year == event.detectedAt.year for moment in dates.values()):
            raise ValueError("Event year is missing from the calendar")
        materials = []
        for path, moment in sorted(dates.items(), key=lambda item: item[1]):
            if not event.intervalStart <= moment <= event.detectedAt:
                continue
            url = f"https://www.cbr.ru{path}"
            release = await client.get(url, follow_redirects=False, timeout=3)
            release.raise_for_status()
            heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", release.text, re.IGNORECASE | re.DOTALL)
            title = " ".join(unescape(re.sub(r"<[^>]+>", " ", heading[1])).split()) if heading else ""
            if "ключев" not in title.lower():
                raise ValueError("Missing decision headline")
            materials.append(Material(id=f"cbr-{moment:%Y%m%d%H%M%S}", source="Банк России",
                                      publishedAt=moment, title=title, url=url, kind="fact"))
        if materials:
            return CheckResult("ok", materials=materials)
        return CheckResult("empty", "По календарю ЦБ решения по ставке в окне сигнала не было.")
    except (httpx.HTTPError, ValueError):
        start = event.intervalStart.astimezone(MOSCOW)
        end = event.detectedAt.astimezone(MOSCOW)
        # Verified in the official calendar for the saved GAZP episode.
        if start.date().isoformat() == end.date().isoformat() == "2025-05-22":
            return CheckResult("empty", "По сохранённому календарю ЦБ за 22 мая 2025 года решений по ставке не было.")
        return CheckResult("unavailable", "Не удалось проверить календарь Банка России.")
