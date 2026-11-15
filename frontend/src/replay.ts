import type { Candle } from './market';

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
  news: ReplayNews | null;
};

export type ReplayEpisode = {
  candles: Candle[];
  warmupCount: number;
  thresholdPercent: number;
  event: ReplayEvent | null;
};
