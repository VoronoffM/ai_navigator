import { useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Check, Play, Radar, Square } from 'lucide-react';
import { marketTime, number, symbols, type Ticker } from './market';
import { EventAnalysis } from './EventAnalysis';
import { useAnalysis, type Profile } from './analysis';
import type { ReplayEvent } from './replay';

const percent = new Intl.NumberFormat('ru-RU', {
  style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2,
});

const hour = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
});

type NavigatorProps = {
  event: ReplayEvent | null;
  profile: Profile;
  running: boolean;
  replay: boolean;
  loading: boolean;
  issue: string | null;
  threshold: number | undefined;
  onPlay: () => void;
  onExit: () => void;
};

export function Navigator({ event, profile, running, replay, loading, issue, threshold, onPlay, onExit }: NavigatorProps) {
  const [selected, setSelected] = useState<Ticker[]>(['GAZP']);
  const canReplay = selected.includes('GAZP');
  const analysis = useAnalysis(event?.event_id, profile);
  const canStop = running || analysis?.status === 'collecting' || analysis?.status === 'analyzing';

  function toggleTicker(ticker: Ticker) {
    setSelected((current) => current.includes(ticker)
      ? current.filter((item) => item !== ticker)
      : [...current, ticker]);
  }

  return (
    <aside className="navigator" aria-labelledby="navigator-title">
      <header className="navigator-heading">
        <span className="navigator-symbol"><Radar size={20} aria-hidden="true" /></span>
        <h2 id="navigator-title">AI Navigator</h2>
        <span className="replay-badge">История</span>
      </header>

      <section className="monitoring" aria-labelledby="watchlist-title">
        <h3 id="watchlist-title">Список наблюдения</h3>
        <div className="watch-options" role="group" aria-labelledby="watchlist-title">
          {symbols.map(({ ticker }) => (
            <label className="watch-chip" key={ticker}>
              <input type="checkbox" checked={selected.includes(ticker)} disabled={replay}
                onChange={() => toggleTicker(ticker)} />
              <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>
              {ticker}
            </label>
          ))}
        </div>
        <p className="watch-hint">{canReplay ? 'GAZP · 22 мая 2025 · 1 час' : 'Выберите GAZP для воспроизведения.'}</p>
        <button type="button" className={canStop ? 'button button-stop' : 'button button-primary'}
          disabled={!canStop && (loading || !canReplay)} onClick={canStop ? onExit : onPlay}>
          {canStop ? <Square size={14} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
          {canStop ? 'Остановить' : issue ? 'Повторить загрузку' : replay ? 'Воспроизвести снова' : 'Воспроизвести эпизод'}
        </button>
        {replay && !canStop && (
          <button type="button" className="replay-exit" onClick={onExit}>Вернуться к рынку</button>
        )}
      </section>

      <section className="navigator-event" aria-label="Событие" aria-live="polite">
        {event ? (
          <article className="event-card">
            <div className="event-heading">
              <span className="event-icon"><ArrowDownRight size={18} aria-hidden="true" /></span>
              <div><h3>Сигнал по {event.ticker}</h3><span>Закрытие · {marketTime(event.detectedAt)}</span></div>
              <strong className="event-drop figures">{percent.format(event.changePercent / 100)}</strong>
            </div>
            <p className="event-context figures">
              {number.format(event.previousClose)} → {number.format(event.close)} ₽
              {' · '}{hour.format(event.candleTime * 1000)}–{hour.format(event.detectedAt * 1000)} МСК
            </p>
            <p className="event-context">{event.rule}</p>
            {event.news ? (
              <a className="event-news" href={event.news.url} target="_blank" rel="noopener noreferrer">
                <span className="event-news-source">{event.news.source} · {marketTime(event.news.publishedAt)}</span>
                <strong>{event.news.title}</strong>
                <ArrowUpRight size={16} aria-hidden="true" />
              </a>
            ) : <p className="event-context">К моменту сигнала публикаций в эпизоде нет.</p>}
            {analysis && <EventAnalysis state={analysis} articleId={event.news?.id} />}
          </article>
        ) : (
          <p className="event-placeholder" role={issue ? 'alert' : undefined}>
            {issue ?? (running ? 'Проверяем закрытия часовых свечей…'
              : replay ? 'В этом эпизоде сигнал не сработал.'
                : loading ? 'Загружаем исторический эпизод…'
                  : `Сигнал появится при снижении на ${threshold}% или больше за час.`)}
          </p>
        )}
      </section>
    </aside>
  );
}
