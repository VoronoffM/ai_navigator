import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import ValidationError

from backend.analysis import AnalysisService, Profile, Workflow
from backend.replay import gazprom_signal
from backend.signal_checks import CheckResult
from backend.sources import ResearchSource, read_source


class SourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.event = gazprom_signal()
        self.source = ResearchSource(url='https://example.com/news', instructions='Проверь заявление о ставке.')

    async def read(self, html, status=200, headers=None):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(
                status, text=html, headers=headers or {'content-type': 'text/html'}))) as client:
            return await read_source(client, self.source, self.event)

    def test_source_configuration_rejects_nonpublic_endpoints_and_empty_task(self):
        for url in ('http://example.com', 'https://localhost/news', 'https://user:pass@example.com', 'https://example.com:8080'):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                ResearchSource(url=url, instructions='Проверь')
        with self.assertRaises(ValidationError):
            ResearchSource(url='https://example.com', instructions='   ')

    async def test_page_outside_signal_window_or_without_date_is_excluded(self):
        for date in ('', '2025-05-22T15:46:00', '2025-05-22T16:46:00+03:00', '2025-05-21T15:46:00+03:00'):
            with self.subTest(date=date):
                result = await self.read(f'<meta property="article:published_time" content="{date}"><p>Новость.</p>')
                self.assertNotEqual(result.status, 'ok')
                self.assertFalse(result.materials)

    async def test_redirect_nonhtml_and_oversized_page_are_not_read(self):
        redirected = await self.read('', status=302, headers={'location': 'http://127.0.0.1/private'})
        self.assertEqual(redirected.status, 'unavailable')
        nonhtml = await self.read('{}', headers={'content-type': 'application/json'})
        self.assertEqual(nonhtml.status, 'unavailable')
        large = await self.read('x' * 1_000_001)
        self.assertEqual(large.status, 'unavailable')

    async def test_page_text_date_and_citation(self):
        result = await self.read('<title>Решение</title><meta property="article:published_time" '
                                 'content="2025-05-22T15:46:00+03:00"><script>secret()</script><p>Текст заявления.</p>')
        self.assertEqual(result.status, 'ok')
        material = result.materials[0]
        self.assertEqual(material.url, self.source.url)
        self.assertIn('Текст заявления.', material.text)
        self.assertNotIn('secret', material.text)
        self.assertEqual(material.kind, 'unverified')

    async def test_unknown_and_future_dates_are_excluded(self):
        self.assertEqual((await self.read('<p>Нет даты</p>')).status, 'unavailable')
        self.assertEqual((await self.read('<time datetime="2026-11-19T12:00:00+03:00">Сегодня</time>')).status, 'empty')

    async def test_redirect_non_html_and_large_response_are_unavailable(self):
        self.assertEqual((await self.read('', 302, {'location': 'http://127.0.0.1/'})).status, 'unavailable')
        self.assertEqual((await self.read('{}', headers={'content-type': 'application/json'})).status, 'unavailable')
        self.assertEqual((await self.read('x' * 1_000_001)).status, 'unavailable')

    async def test_invalid_source_configuration(self):
        for url in ('http://example.com', 'https://localhost/a', 'https://user:pass@example.com'):
            with self.assertRaises(ValidationError):
                ResearchSource(url=url, instructions='Проверь')
        with self.assertRaises(ValidationError):
            ResearchSource(url=self.source.url, instructions='  ')

    async def test_source_workflow_passes_instructions_and_preserves_failure(self):
        provider = AsyncMock()
        service = AnalysisService(provider, {}, cbr_check=AsyncMock(return_value=CheckResult('empty', 'Решений нет.')))
        workflow = Workflow(actions=('source',), sources=[self.source])
        with patch('backend.analysis.check_source', new=AsyncMock(return_value=CheckResult('unavailable', 'Нет даты.'))):
            result = await service.wait(service.start(self.event, Profile(workflow=workflow))['id'])
        self.assertEqual(result['sources'][0]['reason'], 'Нет даты.')
        provider.generate.assert_not_awaited()

        material_result = await self.read('<title>Новость</title><time datetime="2025-05-22T15:46:00+03:00"></time><p>Текст.</p>')
        provider.generate.return_value = json.dumps({'summary': None, 'facts': [], 'hypotheses': [], 'questions': ['Как оценить влияние?']})
        with patch('backend.analysis.check_source', new=AsyncMock(return_value=material_result)):
            # Separate workflow identity avoids reusing a completed job.
            workflow.instructions = 'Проверь источник'
            result = await service.wait(service.start(self.event, Profile(workflow=workflow))['id'])
        self.assertEqual(result['llm'], 'ready')
        context = provider.generate.await_args.args[1]
        self.assertEqual(context['sourceTasks'][0]['instructions'], self.source.instructions)
        self.assertEqual(context['sourceTasks'][0]['materialIds'], [material_result.materials[0].id])
