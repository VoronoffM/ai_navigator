import type { Candle, Ticker } from './market';
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
  comparisonKind?: 'hour' | 'session-gap';
  previousCloseAt?: number;
  previousSessionDate?: string;
};

export type EpisodeMetadata = {
  id: string;
  ticker: Ticker;
  name: string;
  title: string;
  date: string;
  kind: 'historical' | 'synthetic';
  description: string;
  source: string;
  note: string;
  datasetVersion: string;
  interval: '1h';
};

export type ReplayEpisode = {
  metadata: EpisodeMetadata;
  candles: Candle[];
  warmupCount: number;
  thresholdPercent: number;
  event: ReplayEvent | null;
  frames?: ReplayEvent[];
};

export function supportsReplayScenario(scenario: Scenario, ticker: string = 'GAZP') {
  return scenario.enabled && scenario.assets.some((asset) => asset === ticker) && scenario.windowMinutes === 60
    && (isPilotTrigger(scenario.trigger) || scenario.trigger === 'price');
}

export function matchesReplayScenario(scenario: Scenario, event: ReplayEvent) {
  if (!supportsReplayScenario(scenario, event.ticker)) return false;
  if (scenario.trigger === 'volume-spike') return event.volumeRatio != null && event.volumeRatio >= scenario.threshold;
  const score = scenario.trigger === 'price-z' ? event.priceZ
    : scenario.trigger === 'relative' ? event.marketZ : event.changePercent;
  if (score == null || Math.abs(score) < scenario.threshold) return false;
  const movement = scenario.trigger === 'relative' && event.indexChangePercent != null
    ? event.changePercent - event.indexChangePercent : event.changePercent;
  return scenario.direction === 'either' || (scenario.direction === 'up' ? movement > 0 : movement < 0);
}
