import asyncio
import json
import os
import unittest
from datetime import date
from unittest.mock import patch

import httpx

from backend.analysis import AnalysisService, Profile, Workflow, resolve_citations
from backend.cbr import CALENDAR, check_cbr_calendar
from backend.llm import PublicCloudTransport, ProviderError, analysis_messages
from backend.replay import gazprom_replay, gazprom_signal
from backend.signal_checks import (
    CALENDAR_ONLY, CHECKS, CheckResult, LiveChecks, Material, ReplayChecks, dividend_result, report_result,
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

    async def test_workflow_runs_in_saved_order_and_passes_report_settings(self):
        order = []

        async def check_news(event):
            order.append("mcp")
            return await self.replay.news(event)

        async def check_cbr(_event):
            order.append("cbr")
            return CheckResult("empty", "Решения по ставке не было.")

        self.checks["news"] = check_news
        self.service.cbr_check = check_cbr
        workflow = Workflow(actions=("cbr", "mcp"), depth="detailed", instructions="Укажи время публикации.")
        result = await self.finish(self.service.start(self.event, Profile(checks={"news"}, workflow=workflow)))
        self.assertEqual(order, ["cbr", "mcp"])
        self.assertEqual(result["cbr"]["status"], "empty")
        self.assertEqual(result["llm"], "ready")
        context = self.provider.calls[-1][1]
        self.assertEqual(context["report"], {"format": "detailed", "focus": "Укажи время публикации."})
        self.assertIn("до трёх утверждений источников", analysis_messages(context)[0]["content"])

        reversed_workflow = workflow.model_copy(update={"actions": ("mcp", "cbr")})
        second = await self.finish(self.service.start(self.event, Profile(checks={"news"}, workflow=reversed_workflow)))
        self.assertNotEqual(result["id"], second["id"])
        self.assertEqual(order, ["cbr", "mcp", "mcp", "cbr"])

    async def test_cbr_calendar_filters_out_releases_after_signal(self):
        requests = []

        def calendar(request):
            requests.append(str(request.url))
            if str(request.url) == CALENDAR:
                return httpx.Response(200, text=(
                    '<a href="/press/pr/?file=22052025_153000key.htm">До</a>'
                    '<a href="/press/PR?file=22052025_163000key.htm">После</a>'
                ))
            return httpx.Response(200, text="<h1>Банк России сохранил ключевую ставку</h1>")

        async with httpx.AsyncClient(transport=httpx.MockTransport(calendar)) as client:
            result = await check_cbr_calendar(client, self.event)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.materials), 1)
        self.assertEqual(result.materials[0].kind, "fact")
        self.assertEqual(requests, [CALENDAR, "https://www.cbr.ru/press/pr/?file=22052025_153000key.htm"])

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
        self.provider.response = json.dumps({
            "summary": "Индекс почти не изменился. Данных для определения причины недостаточно.",
            "evidenceChecks": ["market"], "facts": [], "hypotheses": [], "questions": [],
        })
        prices = await self.finish(self.service.start(self.event, Profile(checks={"market"})))
        self.assertEqual(prices["llm"], "ready")
        self.assertEqual(prices["checks"]["news"]["status"], "disabled")
        self.assertEqual(len(self.provider.calls), 3)

    async def test_empty_news_calls_model_with_check_evidence_and_no_materials(self):
        async def empty(_event):
            return CheckResult("empty", "Подходящих новостей не найдено.")

        self.checks["news"] = empty
        self.provider.response = json.dumps({
            "summary": "Скорее всего, рыночный шум. В проверенной ленте причина не подтверждена.",
            "evidenceChecks": ["news", "market"], "facts": [], "hypotheses": [], "questions": [],
        })
        result = await self.finish(self.service.start(self.event, Profile(checks={"news", "market"})))
        self.assertEqual(result["llm"], "ready")
        self.assertEqual(result["synthesis"]["evidenceChecks"], ["news", "market"])
        context = self.provider.calls[0][1]
        self.assertEqual(context["materials"], [])
        self.assertEqual(context["coverage"]["news"]["status"], "empty")
        self.assertIn("comparison", context["computedFacts"]["market"])

    async def test_unavailable_news_is_preserved_in_model_context(self):
        async def unavailable(_event):
            return CheckResult("unavailable", "Лента недоступна.")

        self.checks["news"] = unavailable
        self.provider.response = json.dumps({
            "summary": "Лента недоступна. Данных для определения причины недостаточно.",
            "evidenceChecks": ["market"], "facts": [], "hypotheses": [], "questions": [],
        })
        result = await self.finish(self.service.start(self.event, Profile(checks={"news", "market"})))
        self.assertEqual(result["llm"], "ready")
        self.assertEqual(self.provider.calls[0][1]["coverage"]["news"]["status"], "unavailable")
        skipped = await self.finish(self.service.start(self.event, Profile(checks={"news"})))
        self.assertEqual(skipped["llm"], "skipped")
        self.assertEqual(len(self.provider.calls), 1)

    async def test_summary_uses_only_available_evidence(self):
        body = {
            "summary": "Газпром снизился, пока индекс почти не изменился.\n\nПричина неясна.",
            "facts": [], "hypotheses": [], "questions": [],
            "evidenceChecks": ["market", "market"],
        }
        self.provider.response = json.dumps(body)
        ready = await self.finish(self.service.start(self.event, Profile()))
        self.assertEqual(ready["llm"], "ready")
        self.assertEqual(ready["synthesis"]["summary"],
                         "Газпром снизился, пока индекс почти не изменился. Причина неясна.")
        self.assertEqual(ready["synthesis"]["evidenceChecks"], ["market"])

        for evidence in ([], ["cbr"]):
            with self.subTest(evidence=evidence):
                body["evidenceChecks"] = evidence
                with self.assertRaises(ValueError):
                    resolve_citations(json.dumps(body), {}, {"market"})

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

    async def test_cloud_routing_and_retries_are_scoped_to_endpoint_model_and_key(self):
        requests = []

        def cloud(request):
            body = json.loads(request.content)
            requests.append((str(request.url), body["model"], request.headers["Authorization"]))
            self.assertEqual(set(body), {"model", "messages"})
            schema = json.loads(body["messages"][0]["content"].split("Верни только JSON по схеме: ", 1)[1])
            ids = schema["$defs"]["Statement"]["properties"]["materialIds"]["items"]["enum"]
            self.assertEqual(ids, ["interfax-1027187"])
            if len(requests) == 1:
                return httpx.Response(429)
            return httpx.Response(200, json={"choices": [
                {"finish_reason": "stop", "message": {"content": self.provider.response}},
            ]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(cloud)) as client:
            self.service.cloud_client = client
            base_url = "https://example.com/api/v1"
            endpoint = f"{base_url}/chat/completions"
            profile = Profile(provider="cloud", model="vendor/custom", apiUrl=base_url)
            missing = await self.finish(self.service.start(self.event, profile))
            self.assertEqual(missing["llm"], "failed")
            self.assertEqual(missing["checks"]["news"]["status"], "ok")
            self.assertEqual(requests, [])

            failed = await self.finish(self.service.start(self.event, profile, "test-key"))
            self.assertIn("лимит облачного API", failed["reason"])
            retry = self.service.start(self.event, profile, "test-key")
            self.assertNotEqual(retry["id"], failed["id"])
            self.assertEqual(retry["id"], self.service.start(self.event, profile, "test-key")["id"])
            ready = await self.finish(retry)
            self.assertEqual(ready["llm"], "ready")
            same_endpoint = profile.model_copy(update={"apiUrl": endpoint + "/"})
            self.assertEqual(self.service.start(self.event, same_endpoint, "test-key")["id"], ready["id"])
            self.assertNotIn("test-key", json.dumps(ready))
            other = await self.finish(self.service.start(self.event, profile, "other-key"))
            self.assertNotEqual(other["id"], ready["id"])
            other_endpoint = profile.model_copy(update={"apiUrl": "https://other.example.com/v1/chat/completions"})
            other_model = profile.model_copy(update={"model": "vendor/other"})
            for changed in (other_endpoint, other_model):
                result = await self.finish(self.service.start(self.event, changed, "test-key"))
                self.assertNotEqual(result["id"], ready["id"])
                self.assertEqual(result["llm"], "ready")
            self.assertEqual(requests, [
                (endpoint, "vendor/custom", "Bearer test-key"),
                (endpoint, "vendor/custom", "Bearer test-key"),
                (endpoint, "vendor/custom", "Bearer other-key"),
                ("https://other.example.com/v1/chat/completions", "vendor/custom", "Bearer test-key"),
                (endpoint, "vendor/other", "Bearer test-key"),
            ])
            self.assertEqual(self.provider.calls, [])

    async def test_cloud_transport_pins_public_ip_and_rejects_private_dns_results(self):
        loop = asyncio.get_running_loop()
        request = httpx.Request("POST", "https://example.com/v1/chat/completions")
        async with PublicCloudTransport() as transport:
            with (patch.object(loop, "getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 443))]),
                  patch.object(httpx.AsyncHTTPTransport, "handle_async_request", return_value=httpx.Response(200)) as send):
                await transport.handle_async_request(request)
                outgoing = send.await_args.args[0]
                self.assertEqual(outgoing.url.host, "93.184.216.34")
                self.assertEqual(outgoing.headers["Host"], "example.com")
                self.assertEqual(outgoing.extensions["sni_hostname"], "example.com")
            with (patch.object(loop, "getaddrinfo", return_value=[(0, 0, 0, "", ("::ffff:127.0.0.1", 443))]),
                  patch.object(httpx.AsyncHTTPTransport, "handle_async_request") as send):
                with self.assertRaisesRegex(ProviderError, "публичный HTTPS"):
                    await transport.handle_async_request(request)
                send.assert_not_awaited()

    async def test_cloud_transport_accepts_synthetic_dns_for_official_openai_https(self):
        loop = asyncio.get_running_loop()
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        async with PublicCloudTransport() as transport:
            with (patch.object(loop, "getaddrinfo", return_value=[(0, 0, 0, "", ("240.0.0.45", 443))]),
                  patch.object(httpx.AsyncHTTPTransport, "handle_async_request", return_value=httpx.Response(200)) as send):
                await transport.handle_async_request(request)
                outgoing = send.await_args.args[0]
                self.assertEqual(outgoing.url.host, "240.0.0.45")
                self.assertEqual(outgoing.extensions["sni_hostname"], "api.openai.com")
                for other_url in ("https://example.com/v1/chat/completions",
                                  "https://api.openai.com:8443/v1/chat/completions"):
                    with self.assertRaises(ProviderError):
                        await transport.handle_async_request(httpx.Request("POST", other_url))
                self.assertEqual(send.await_count, 1)

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

    def test_statement_kind_preserves_source_provenance(self):
        materials = {
            item.id: item for item in (
                Material.model_validate(gazprom_replay()["event"]["news"]),
                Material(id="pulse", source="Пульс", kind="opinion", publishedAt=self.event.detectedAt,
                         title="Ожидаю дальнейшего снижения", text="По-моему, падение продолжится."),
                Material(id="unknown", source="Лента", publishedAt=self.event.detectedAt,
                         title="Ждём роста"),
            )
        }
        news = materials["interfax-1027187"]
        body = {
            "facts": [
                {"text": news.title, "materialIds": [news.id]},
                {"text": "Участник Пульса ждёт дальнейшего падения.", "materialIds": ["pulse"]},
                {"text": materials["unknown"].title, "materialIds": ["unknown"]},
            ],
            "hypotheses": [
                {"text": "Негативные ожидания могли усилить реакцию на новость.", "materialIds": [news.id, "pulse"]},
                {"text": materials["pulse"].title, "materialIds": ["pulse"]},
            ],
            "questions": [],
        }
        result = resolve_citations(json.dumps(body), materials)
        self.assertEqual([item["kind"] for item in result["facts"]], ["fact", "opinion", "unverified"])
        self.assertEqual([item["kind"] for item in result["hypotheses"]], ["ai_analysis", "opinion"])
        self.assertEqual(result["facts"][1]["citations"][0]["source"], "Пульс")

        body["facts"] = [{"text": "Дивиденды отменили.", "materialIds": [news.id]}]
        self.assertEqual(resolve_citations(json.dumps(body), materials)["facts"][0]["kind"], "unverified")
