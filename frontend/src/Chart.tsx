import { useEffect, useRef, useState } from 'react';
import {
  CandlestickSeries, ColorType, CrosshairMode, TickMarkType, createChart,
  type IChartApi, type ISeriesApi, type Time,
} from 'lightweight-charts';
import { type Candle, type Interval, number } from './market';

const axisDate = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', day: 'numeric', month: 'short' });
const axisTime = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit' });
const axisMonth = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', month: 'short' });

export function Chart({ candles, interval }: { candles: Candle[]; interval: Interval }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const hasData = useRef(false);
  const [hoverTime, setHoverTime] = useState<Time>();
  const latest = candles[candles.length - 1];
  const bar = candles.find((candle) => candle.time === hoverTime) ?? latest;

  useEffect(() => {
    if (!container.current) return;
    const style = getComputedStyle(container.current);
    const color = (name: string) => style.getPropertyValue(name).trim();
    const grid = { color: color('--chart-grid') };
    const crosshair = { color: color('--chart-cursor'), labelBackgroundColor: color('--chart-label') };
    const fontSize = Number.parseFloat(style.fontSize);
    const api = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: color('--chart-background') },
        textColor: color('--muted'),
        fontFamily: style.fontFamily,
        fontSize,
        attributionLogo: true,
      },
      grid: { vertLines: { visible: false }, horzLines: grid },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: crosshair,
        horzLine: crosshair,
      },
      rightPriceScale: {
        borderVisible: false,
        entireTextOnly: true,
        scaleMargins: { top: 0.12, bottom: 0.12 },
      },
      timeScale: {
        borderVisible: false,
        timeVisible: interval === '1h',
        secondsVisible: false,
        rightOffset: 3,
        tickMarkFormatter: (time: Time, type: TickMarkType) => {
          if (typeof time !== 'number') return null;
          const date = new Date(time * 1000);
          if (type === TickMarkType.Year) return String(date.getUTCFullYear());
          if (type === TickMarkType.Month) return axisMonth.format(date);
          return type === TickMarkType.DayOfMonth ? axisDate.format(date) : axisTime.format(date);
        },
      },
      localization: {
        locale: 'ru-RU',
        priceFormatter: (value: number) => number.format(value),
        timeFormatter: (time: Time) => {
          if (typeof time !== 'number') return String(time);
          const date = new Date(time * 1000);
          const day = axisDate.format(date);
          return interval === '1h' ? `${day}, ${axisTime.format(date)}` : day;
        },
      },
    });
    const up = color('--chart-up');
    const down = color('--chart-down');
    const candleSeries = api.addSeries(CandlestickSeries, {
      upColor: up,
      downColor: down,
      borderVisible: false,
      wickUpColor: up,
      wickDownColor: down,
      priceLineColor: color('--chart-price'),
    });
    api.subscribeCrosshairMove((event) => setHoverTime(event.time));
    chart.current = api;
    series.current = candleSeries;
    return () => {
      api.remove();
      chart.current = null;
      series.current = null;
      hasData.current = false;
    };
  }, [interval]);

  useEffect(() => {
    series.current?.setData(candles);
    if (!hasData.current) {
      chart.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, candles.length - 85) - 2, to: candles.length + 2 });
      hasData.current = true;
    }
  }, [candles]);

  return (
    <div className="chart-frame" role="group" aria-label="График рыночных свечей">
      <div className="ohlc" aria-label="Открытие, максимум, минимум и закрытие свечи">
        {(['open', 'high', 'low', 'close'] as const).map((field, index) => (
          <span key={field}>{['Откр.', 'Макс.', 'Мин.', 'Закр.'][index]} <b className="figures">{number.format(bar[field])}</b></span>
        ))}
      </div>
      <div className="chart-canvas" ref={container} />
    </div>
  );
}
