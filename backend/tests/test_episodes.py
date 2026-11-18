import asyncio
import json
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.analysis import AnalysisService, Profile, Workflow
from backend.episodes import GAZP_ID, catalog, episode_data, episode_signal, replay_episode, visible_materials
from backend.main import app
from backend.replay import HOUR, gazprom_replay, gazprom_signal
from backend.replay_models import replay_scores
from backend.signal_checks import CHECKS, ReplayChecks, replay_check
from backend.sources import ResearchSource


class EpisodeTests(unittest.TestCase):
    def test_catalog_endpoints_and_gazp_compatibility(self):
        with TestClient(app) as client:
            items = client.get('/api/replay/episodes').json()
            self.assertEqual(len(items), 7)
            self.assertEqual(len({item['id'] for item in items}), 7)
            for item in items:
                response = client.get('/api/replay/episodes/' + item['id'])
                self.assertEqual(response.status_code, 200)
                episode = response.json()
                self.assertEqual(episode['metadata']['id'], item['id'])
                times = [bar['time'] for bar in episode['candles']]
                self.assertEqual(times, sorted(set(times)))
                self.assertGreater(episode['warmupCount'], 0)
                self.assertLess(episode['warmupCount'], len(times))
                for bar in episode['candles']:
                    self.assertLessEqual(bar['low'], min(bar['open'], bar['close']))
                    self.assertGreaterEqual(bar['high'], max(bar['open'], bar['close']))
                for frame in episode['frames']:
                    signal = episode_signal(frame['event_id'])
                    self.assertIsNotNone(signal)
                    self.assertEqual(signal.ticker, item['ticker'])
                    for entry in visible_materials(item['id'], frame['detectedAt']):
                        self.assertLessEqual(datetime.fromisoformat(entry['availableAt']), signal.detectedAt)
            original = client.get('/api/replay/gazprom').json()
            selected = client.get('/api/replay/episodes/' + GAZP_ID).json()
            self.assertEqual(original, {key: value for key, value in selected.items() if key != 'metadata'})
            self.assertEqual(selected['event'], gazprom_replay()['event'])
            self.assertEqual(client.get('/api/replay/episodes/missing').status_code, 404)
            self.assertEqual(client.post('/api/analysis/forged', json={}).status_code, 404)

    def test_vtbr_release_is_available_only_after_1339(self):
        frame = replay_episode('vtbr-2025-04-28')['event']
        event = episode_signal(frame['event_id'])
        self.assertEqual(event.detectedAt.isoformat(), '2025-04-28T14:00:00+03:00')
        self.assertAlmostEqual(event.changePercent, (107.14/86.65-1)*100)
        self.assertEqual(visible_materials(event.episodeId, datetime.fromisoformat('2025-04-28T13:38:59+03:00').timestamp()), [])
        self.assertEqual(len(visible_materials(event.episodeId, event.detectedAt.timestamp())), 1)
        self.assertIsNone(episode_signal(frame['event_id'].replace('-v1-', '-v2-')))

    def test_belu_gap_preserves_raw_prices_and_omits_hourly_statistics(self):
        data = replay_episode('belu-2024-08-22')
        frame = data['event']
        event = episode_signal(frame['event_id'])
        self.assertEqual(frame['comparisonKind'], 'session-gap')
        self.assertEqual(frame['previousClose'], 4680)
        self.assertEqual(frame['close'], 781)
        self.assertEqual(event.detectedAt.isoformat(), '2024-08-22T11:00:00+03:00')
        self.assertGreater(event.intervalStart.timestamp() - event.previousCloseAt.timestamp(), HOUR)
        self.assertIsNone(frame['priceZ'])
        self.assertIsNone(frame['marketZ'])
        self.assertEqual([item['id'] for item in visible_materials(event.episodeId, datetime.fromisoformat('2024-08-22T10:26:59+03:00').timestamp())], ['belu-corporate-969335'])

    def test_synthetic_prices_repeat_and_variants_share_the_same_impulse(self):
        calm = replay_episode('noise-calm')
        self.assertIsNone(calm['event'])
        self.assertLess(max(abs(frame['changePercent']) for frame in calm['frames']), .3)
        impulse = episode_data('noise-impulse')
        for name in ('noise-stale', 'noise-unavailable'):
            self.assertEqual(impulse['DEMO'], episode_data(name)['DEMO'])
            self.assertEqual(impulse['IMOEX'], episode_data(name)['IMOEX'])
        replay_episode.cache_clear()
        episode_data.cache_clear()
        self.assertEqual(impulse, episode_data('noise-impulse'))

    def test_scores_do_not_use_future_candles_or_future_volume(self):
        from backend.replay import MOSCOW
        data = episode_data('vtbr-2025-04-28')
        candles = data['VTBR']
        first = replay_episode('vtbr-2025-04-28')['event']
        prefix = [bar for bar in candles if bar['time'] <= first['candleTime']]
        all_scores = replay_scores(data['history'], candles, data['IMOEX'], data['start'], HOUR, MOSCOW, 'VTBR')
        prefix_scores = replay_scores(data['history'], prefix, data['IMOEX'], data['start'], HOUR, MOSCOW, 'VTBR')
        self.assertEqual(prefix_scores[first['candleTime']], all_scores[first['candleTime']])
        self.assertGreater(first['volumeRatio'], 1)


class EpisodeAnalysisTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_is_isolated_across_parallel_episodes(self):
        ids = ['vtbr-2025-04-28', 'belu-2024-08-22', 'noise-impulse', 'noise-stale', 'noise-unavailable']
        events = [episode_signal(replay_episode(key)['event']['event_id']) for key in ids]
        checks = await asyncio.gather(*(replay_check('news', event) for event in events))
        self.assertEqual([check.status for check in checks], ['ok', 'ok', 'empty', 'ok', 'unavailable'])
        self.assertEqual([item.id for item in checks[0].materials], ['vtbr-disclosure-20250428'])
        self.assertEqual({item.id for item in checks[1].materials}, {'belu-interfax-977582', 'belu-corporate-969335'})
        self.assertEqual(checks[3].materials[0].kind, 'unverified')
        self.assertEqual((await replay_check('market', events[1])).status, 'empty')
        market = await replay_check('market', events[2])
        self.assertEqual(market.facts['comparison']['ticker'], 'DEMO-INDEX')
        self.assertEqual(market.facts['comparison']['source'], 'Симуляция')
        self.assertEqual((await replay_check('dividends', events[0])).status, 'ok')
        self.assertNotIn('recommendation', (await replay_check('dividends', events[1])).facts)

    async def test_new_episode_does_not_fetch_live_sources_or_share_cached_jobs(self):
        provider = AsyncMock()
        provider.name = 'Test'
        service = AnalysisService(provider, {name: lambda event, name=name: replay_check(name, event) for name in CHECKS})
        profile = Profile(checks={'market'})
        events = [episode_signal(replay_episode(key)['event']['event_id']) for key in ['vtbr-2025-04-28','noise-impulse']]
        with patch('backend.analysis.check_source', new_callable=AsyncMock) as network:
            jobs = [service.start(event, profile) for event in events]
            self.assertNotEqual(jobs[0]['id'], jobs[1]['id'])
            results = await asyncio.gather(*(service.wait(job['id']) for job in jobs))
            self.assertEqual([item['dataSource'] for item in results], ['Московская биржа · ISS', 'Симуляция'])
            self.assertTrue(results[1]['synthetic'])
            revised = events[0].model_copy(update={'datasetVersion': '2'})
            self.assertNotEqual(service.start(revised, profile)['id'], jobs[0]['id'])
            source_profile = Profile(checks=set(), workflow=Workflow(actions=('source',), sources=[ResearchSource(
                kind='url', url='https://example.com', instructions='Проверь публикацию.')]))
            result = await service.wait(service.start(events[1], source_profile)['id'])
            self.assertEqual(result['sources'][0]['status'], 'unavailable')
            network.assert_not_called()
        await service.shutdown()

    async def test_model_receives_only_materials_for_selected_episode_and_time(self):
        calls = []
        class Provider:
            name = 'Recording provider'
            async def generate(self, model, context, schema):
                calls.append(context)
                entry = context['materials'][0]
                return json.dumps({'facts': [{'text': entry['title'], 'materialIds': [entry['id']]}],
                                   'hypotheses': [], 'questions': []})
        service = AnalysisService(Provider(), {name: lambda event, name=name: replay_check(name, event) for name in CHECKS})
        try:
            for key in ['vtbr-2025-04-28', 'belu-2024-08-22', 'noise-stale']:
                event = episode_signal(replay_episode(key)['event']['event_id'])
                result = await service.wait(service.start(event, Profile())['id'])
                self.assertEqual(result['llm'], 'ready')
                context = calls[-1]
                self.assertEqual(context['event']['episodeId'], key)
                self.assertNotIn('metadata', context)
                self.assertNotIn('expected', context)
                for item in context['materials']:
                    self.assertLessEqual(datetime.fromisoformat(item['publishedAt']), event.detectedAt)
                self.assertNotIn('interfax-1027187', [item['id'] for item in context['materials']])
        finally:
            await service.shutdown()

    async def test_simulation_remains_labeled_in_telegram_report(self):
        from backend.telegram import ScenarioDelivery, report_text
        from uuid import uuid4
        event = episode_signal(replay_episode('noise-impulse')['event']['event_id'])
        service = AnalysisService(AsyncMock(), {name: lambda event, name=name: replay_check(name, event) for name in CHECKS})
        try:
            result = await service.wait(service.start(event, Profile())['id'])
            text = report_text(event, ScenarioDelivery(run_id=uuid4(), scenario_id='test', name='Test'), result)
            self.assertIn('симуляция · вымышленные данные', text)
            self.assertIn('Учебный индекс', text)
            self.assertNotIn('IMOEX', text)
        finally:
            await service.shutdown()
