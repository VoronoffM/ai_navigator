import type { Candle } from './market';
import { isPilotTrigger, type Scenario } from './scenarios';

type ReplayNews = {
  id: string;
  source: string;
  publishedAt: string;
  title: string;
  url: string;
};

export type ReplayEvent = {
  event_id: string;
  ticker: string;
  rule: string;
  candleTime: number;
  detectedAt: number;
  previousClose: number;
  close: number;
  changePercent: number;
  indexChangePercent: number | null;
  priceZ?: number | null;
  volumeRatio?: number | null;
  marketZ?: number | null;
  news: ReplayNews | null;
};

export type ReplayEpisode = {
  candles: Candle[];
  warmupCount: number;
  thresholdPercent: number;
  event: ReplayEvent | null;
  frames?: ReplayEvent[];
};

export function supportsReplayScenario(scenario: Scenario) {
  return scenario.enabled && scenario.assets.includes('GAZP') && scenario.windowMinutes === 60
    && (isPilotTrigger(scenario.trigger) || scenario.trigger === 'price');
}

export function matchesReplayScenario(scenario: Scenario, event: ReplayEvent) {
  if (!supportsReplayScenario(scenario)) return false;
  if (scenario.trigger === 'volume-spike') return event.volumeRatio != null && event.volumeRatio >= scenario.threshold;
  const score = scenario.trigger === 'price-z' ? event.priceZ
    : scenario.trigger === 'relative' ? event.marketZ : event.changePercent;
  if (score == null || Math.abs(score) < scenario.threshold) return false;
  const movement = scenario.trigger === 'relative' && event.indexChangePercent != null
    ? event.changePercent - event.indexChangePercent : event.changePercent;
  return scenario.direction === 'either' || (scenario.direction === 'up' ? movement > 0 : movement < 0);
}
