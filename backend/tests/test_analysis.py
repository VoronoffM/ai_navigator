import asyncio
import json
import os
import unittest
from datetime import date
from unittest.mock import patch

from backend.analysis import AnalysisService, Profile, resolve_citations
from backend.llm import ProviderError
from backend.replay import gazprom_replay, gazprom_signal
from backend.signal_checks import (
    CALENDAR_ONLY, CHECKS, LiveChecks, Material, ReplayChecks, dividend_result, report_result,
)


class Provider:
    name = "Test provider"

    def __init__(self):
        self.calls = []
        self.response = json.dumps({
            "facts": [{"text": "Совет рекомендовал не выплачивать дивиденды.", "materialIds": ["interfax-1027187"]}],
            "hypotheses": [],
            "questions": [],
        })

    async def generate(self, model, context, _schema):
        self.calls.append((model, context))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class EmptyNews:
    async def call(self, name, arguments):
        assert name == "invest_get_news" and arguments["instrumentId"] == "GAZP"
        return {"items": [], "hasNext": False}


class AnalysisTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.event = gazprom_signal()
        self.replay = ReplayChecks(gazprom_replay()["event"]["news"])
        self.provider = Provider()
        self.checks = {name: getattr(self.replay, name) for name in CHECKS}
        with patch.dict(os.environ, {"ANALYSIS_MODELS": "first,second", "ANALYSIS_DEFAULT_MODEL": "first"}):
            self.service = AnalysisService(self.provider, self.checks)

    async def finish(self, job):
        await asyncio.gather(*self.service.tasks)
        return self.service.jobs[job["id"]]

    async def test_canonical_context_deduplication_and_profile(self):
        job = self.service.start(self.event, Profile())
        self.assertEqual(job["id"], self.service.start(self.event, Profile(checks=set(CHECKS)))["id"])
        result = await self.finish(job)
        self.assertEqual(result, self.service.start(self.event, Profile(model="first")))
        self.assertEqual(result["llm"], "ready")
        self.assertEqual(len(self.provider.calls), 1)
        _, context = self.provider.calls[0]
        self.assertEqual(context["event"]["detectedAt"], "2025-05-22T16:00:00+03:00")
        self.assertAlmostEqual(context["event"]["changePercent"], -2.15, places=2)
        self.assertAlmostEqual(context["computedFacts"]["market"]["comparison"]["changePercent"], 0.03, places=2)
        self.assertEqual(len(context["materials"]), 1)
        self.assertEqual(context["materials"][0]["publishedAt"], "2025-05-22T15:46:00+03:00")
        url = result["synthesis"]["facts"][0]["citations"][0]["url"]
        self.assertEqual(url, "https://www.interfax.ru/business/1027187")

        second = self.service.start(self.event, Profile(model="second"))
        self.assertNotEqual(second["id"], job["id"])
        await self.finish(second)
        self.assertEqual(self.provider.calls[-1][0], "second")
        prices = await self.finish(self.service.start(self.event, Profile(checks={"market"})))
        self.assertEqual(prices["llm"], "skipped")
        self.assertEqual(prices["checks"]["news"]["status"], "disabled")
        self.assertEqual(len(self.provider.calls), 2)

    async def test_source_timeout_preserves_other_checks(self):
        async def slow(_event):
            await asyncio.sleep(5)

        self.checks["reports"] = slow
        for deadline, timeout in (("CHECK_TIMEOUT", "COLLECTION_TIMEOUT"), ("COLLECTION_TIMEOUT", "CHECK_TIMEOUT")):
            with self.subTest(deadline=deadline):
                with patch(f"backend.analysis.{deadline}", 0.01), patch(f"backend.analysis.{timeout}", 5):
                    checks = await self.service.collect(self.event, ("reports", "market", "news"))
                self.assertEqual(checks["reports"].status, "unavailable")
                self.assertEqual(checks["market"].status, "ok")
                self.assertEqual(checks["news"].status, "ok")

    async def test_llm_failure_and_invalid_citations_preserve_context(self):
        self.provider.response = ProviderError("Нет доступа к модели.")
        failed = await self.finish(self.service.start(self.event, Profile()))
        self.assertEqual(failed["reason"], "Нет доступа к модели.")
        self.provider.response = '{"facts":[{"text":"Текст","materialIds":["invented"]}],"hypotheses":[],"questions":[]}'
        invalid = await self.finish(self.service.start(self.event, Profile(model="second")))
        self.assertEqual(invalid["reason"], "Ответ модели не прошёл проверку.")
        for result in (failed, invalid):
            self.assertEqual(result["llm"], "failed")
            self.assertEqual(result["checks"]["news"]["materials"][0]["id"], "interfax-1027187")
            self.assertEqual(result["checks"]["market"]["status"], "ok")

    async def test_empty_news_and_report_calendar_as_of_signal(self):
        news = await LiveChecks(EmptyNews()).news(self.event)
        self.assertEqual(news.status, "empty")
        self.assertEqual(news.reason, "В проверенной ленте подходящих новостей не найдено.")
        report = {"reportDate": "2025-05-22", "createdAt": "2025-05-22T16:01:00+03:00"}
        self.assertEqual(report_result(self.event, [report]).status, "empty")
        report["createdAt"] = "2025-05-22T15:59:00+03:00"
        calendar_only = report_result(self.event, [report])
        self.assertEqual(calendar_only.status, "ok")
        self.assertEqual(calendar_only.reason, CALENDAR_ONLY)
        self.assertEqual(calendar_only.materials, [])

    def test_dividend_gap_needs_session_and_as_of_metadata(self):
        row = {
            "declaredDate": "2025-05-19", "createdAt": "2025-05-19T12:00:00+03:00",
            "lastBuyDate": "2025-05-21", "dividendNet": {"value": "2.88", "currency": "rub"},
            "closePrice": {"value": "134.23", "currency": "rub"},
        }
        result = dividend_result(self.event, [row])
        self.assertNotIn("possibleDividendGap", result.facts["payments"][0])
        first_hour = self.event.model_copy(update={
            "open": 131.35, "sessionStart": self.event.intervalStart, "previousSessionDate": date(2025, 5, 21),
        })
        result = dividend_result(first_hour, [row])
        self.assertEqual(result.facts["payments"][0]["possibleDividendGap"]["gap"], 2.88)
        row["createdAt"] = "2025-05-22T16:01:00+03:00"
        self.assertEqual(dividend_result(first_hour, [row]).status, "empty")

    def test_headline_only_claims(self):
        material = Material(id="headline", source="Source", title="Точный заголовок", publishedAt=self.event.detectedAt)
        statement = {"text": material.title, "materialIds": [material.id]}
        materials = {material.id: material}
        body = {"facts": [statement], "hypotheses": [], "questions": []}
        self.assertEqual(resolve_citations(json.dumps(body), materials)["facts"][0]["text"], material.title)
        body.update(facts=[], hypotheses=[statement])
        with self.assertRaises(ValueError):
            resolve_citations(json.dumps(body), materials)
