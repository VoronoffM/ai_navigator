import assert from 'node:assert/strict';
import test from 'node:test';
import { matchesReplayScenario, supportsReplayScenario, type ReplayEvent } from '../src/replay';
import { draftFrom, type Scenario } from '../src/scenarios';

const rule = (changes: Partial<Scenario> = {}): Scenario => ({
  ...draftFrom('price'), id: 'rule', enabled: true, assets: ['VTBR'], direction: 'either', threshold: 2, ...changes,
});
const event = (changes: Partial<ReplayEvent> = {}): ReplayEvent => ({
  event_id: 'vtbr-v1-1', ticker: 'VTBR', rule: '', candleTime: 1, detectedAt: 3601,
  previousClose: 100, close: 110, changePercent: 10, indexChangePercent: .2, news: null, ...changes,
});

test('only rules with matching ticker, interval, enabled state and supported trigger apply', () => {
  assert.equal(supportsReplayScenario(rule(), 'VTBR'), true);
  for (const settings of [{ assets: ['GAZP'] }, { enabled: false }, { windowMinutes: 240 }, { trigger: 'news' }]) {
    assert.equal(matchesReplayScenario(rule(settings as Partial<Scenario>), event()), false);
  }
});
test('direction and threshold are respected for positive and negative episodes', () => {
  assert.equal(matchesReplayScenario(rule({ direction: 'up' }), event()), true);
  assert.equal(matchesReplayScenario(rule({ direction: 'down' }), event()), false);
  assert.equal(matchesReplayScenario(rule(), event({ changePercent: -2 })), true);
  assert.equal(matchesReplayScenario(rule(), event({ changePercent: -1.99 })), false);
  assert.equal(matchesReplayScenario(rule({ assets: ['DEMO'] }), event({ ticker: 'DEMO', changePercent: -3.8 })), true);
});
test('BELU session gap matches price rules and cannot fabricate an hourly Z score', () => {
  const belu = event({ ticker: 'BELU', comparisonKind: 'session-gap', changePercent: -83.31, priceZ: null, marketZ: null });
  assert.equal(matchesReplayScenario(rule({ assets: ['BELU'] }), belu), true);
  assert.equal(matchesReplayScenario(rule({ assets: ['BELU'], trigger: 'price-z' }), belu), false);
  assert.equal(matchesReplayScenario(rule({ assets: ['BELU'], trigger: 'relative' }), belu), false);
});
test('missing statistical history never triggers and relative direction follows excess return', () => {
  assert.equal(matchesReplayScenario(rule({ trigger: 'price-z' }), event()), false);
  assert.equal(matchesReplayScenario(rule({ trigger: 'volume-spike' }), event()), false);
  assert.equal(matchesReplayScenario(rule({ trigger: 'volume-spike' }), event({ volumeRatio: 2 })), true);
  assert.equal(matchesReplayScenario(rule({ trigger: 'relative', direction: 'down' }),
    event({ changePercent: 1, indexChangePercent: 3, marketZ: -3 })), true);
});
