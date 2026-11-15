import { useEffect, useState } from 'react';
import type { CandlestickData, UTCTimestamp } from 'lightweight-charts';

export const symbols = [
  { ticker: 'GAZP', name: 'Газпром', logo: '/logos/gazp.png' },
  { ticker: 'SBER', name: 'Сбербанк', logo: '/logos/sber.png' },
  { ticker: 'LKOH', name: 'Лукойл', logo: '/logos/lkoh.png' },
  { ticker: 'ROSN', name: 'Роснефть', logo: '/logos/rosn.png' },
] as const;

export type Ticker = (typeof symbols)[number]['ticker'];
export type Interval = '1h' | '1d';
export type Issue = { code: string; message: string };
export type QuoteRow = {
  ticker: Ticker;
  name: string | null;
  currency: string | null;
  quote: { price: number; time: string } | null;
  issue: Issue | null;
};
export type Candle = CandlestickData<UTCTimestamp> & { complete: boolean };

export const number = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const dateTime = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

export function marketTime(value: string | number) {
  return `${dateTime.format(typeof value === 'number' ? value * 1000 : new Date(value))} МСК`;
}

type Resource<T> = { status: 'loading' } | { status: 'ready'; data: T } | { status: 'error'; issue: Issue };

export function useMarketResource<T>(path: string, revision: number): Resource<T> {
  const key = `${path}:${revision}`;
  const [result, setResult] = useState<{ key: string; value: Resource<T> }>();

  useEffect(() => {
    const controller = new AbortController();
    let nextRefresh: number | undefined;

    async function fetchData() {
      let value: Resource<T>;
      try {
        const response = await fetch(path, { signal: controller.signal, cache: 'no-store' });
        if (response.ok) {
          value = { status: 'ready', data: await response.json() };
        } else {
          const body = await response.json().catch(() => null);
          const issue = body?.detail;
          value = {
            status: 'error',
            issue: typeof issue?.message === 'string'
              ? issue
              : { code: 'local_server', message: 'Проверьте, что запущен локальный сервер AI Navigator.' },
          };
        }
      } catch {
        value = {
          status: 'error',
          issue: { code: 'local_server', message: 'Не удалось получить ответ локального сервера AI Navigator.' },
        };
      }
      if (!controller.signal.aborted) {
        setResult({ key, value });
        nextRefresh = window.setTimeout(fetchData, 60_000);
      }
    }

    void fetchData();
    return () => {
      controller.abort();
      window.clearTimeout(nextRefresh);
    };
  }, [key, path]);

  return result?.key === key ? result.value : { status: 'loading' };
}
