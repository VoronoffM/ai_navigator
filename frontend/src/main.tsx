import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ChartCandlestick, CircleAlert, Clock3, Radar, RefreshCw } from 'lucide-react';
import '@fontsource-variable/inter/wght.css';
import { normalizeProfile, readProfile, saveProfile, type AnalysisConfig, type Profile } from './analysis';
import { AgentStudio } from './AgentStudio';
import { Chart } from './Chart';
import { Navigator } from './Navigator';
import { marketTime, number, symbols, useMarketResource, type Candle, type Interval, type QuoteRow, type Ticker } from './market';
import type { ReplayEpisode } from './replay';
import './style.css';
import './studio.css';

const intervals = [{ value: '1h', label: '1ч' }, { value: '1d', label: '1д' }] as const;

function Terminal() {
  const [section, setSection] = useState<'market' | 'studio'>('market');
  const [ticker, setTicker] = useState<Ticker>('GAZP');
  const [interval, setInterval] = useState<Interval>('1h');
  const [revision, setRevision] = useState(0);
  const [replayRevision, setReplayRevision] = useState(0);
  const [replayCount, setReplayCount] = useState<number | null>(null);
  const [savedProfile, setSavedProfile] = useState(readProfile);
  const [replayProfile, setReplayProfile] = useState<Profile>({});
  const configResource = useMarketResource<AnalysisConfig>('/api/analysis/config', 0, false);
  const config = configResource.status === 'ready' ? configResource.data : undefined;
  const quotes = useMarketResource<QuoteRow[]>('/api/quotes', revision);
  const candles = useMarketResource<Candle[]>(`/api/candles/${ticker}?interval=${interval}`, revision);
  const replayResource = useMarketResource<ReplayEpisode>('/api/replay/gazprom', replayRevision, false);
  const episode = replayResource.status === 'ready' ? replayResource.data : null;
  const historical = replayCount !== null;
  const replayRunning = replayCount !== null && episode !== null && replayCount < episode.candles.length;
  const shownTicker = historical ? 'GAZP' : ticker;
  const shownInterval = historical ? '1h' : interval;
  const instrument = symbols.find((item) => item.ticker === shownTicker)!;
  const rows = quotes.status === 'ready' ? quotes.data : [];
  const selectedQuote = rows.find((row) => row.ticker === ticker);
  const quoteIssue = quotes.status === 'error' ? quotes.issue : rows.find((row) => row.issue)?.issue;
  const chartIssue = candles.status === 'error' ? candles.issue : null;
  const bars = historical ? episode?.candles.slice(0, replayCount) ?? []
    : candles.status === 'ready' ? candles.data : [];
  const lastBar = bars[bars.length - 1];
  const event = historical && episode?.event && lastBar?.time >= episode.event.candleTime ? episode.event : null;
  const replayIssue = replayResource.status === 'error' ? replayResource.issue.message : null;
  const headerPrice = historical ? lastBar?.close : selectedQuote?.quote?.price;
  const loading = quotes.status === 'loading' || candles.status === 'loading';

  useEffect(() => {
    if (!replayRunning || replayCount === null) return;
    const timer = window.setTimeout(() => setReplayCount(replayCount + 1), 1100);
    return () => window.clearTimeout(timer);
  }, [replayRunning, replayCount]);

  function playReplay() {
    if (episode) {
      setReplayProfile(normalizeProfile(savedProfile, config));
      setReplayCount(episode.warmupCount);
    } else setReplayRevision((value) => value + 1);
  }

  function refresh() {
    setRevision((value) => value + 1);
  }

  const chartState = candles.status === 'loading'
    ? { title: 'Загружаем свечи', description: 'Запрашиваем историю в песочнице Т‑Инвестиций.' }
    : chartIssue
      ? { title: chartIssue.code === 'not_found' ? 'Данные не найдены' : 'Свечи недоступны', description: chartIssue.message }
      : { title: 'Свечей пока нет', description: 'Песочница вернула пустой ответ за выбранный период.' };

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark"><Radar size={19} aria-hidden="true" /></span>
            <span>AI Navigator</span>
          </div>
          <nav className="workspace-nav" aria-label="Разделы AI Navigator">
            <button type="button" aria-current={section === 'market' ? 'page' : undefined}
              onClick={() => setSection('market')}>Market</button>
            <button type="button" aria-current={section === 'studio' ? 'page' : undefined}
              onClick={() => setSection('studio')}>Agent Studio</button>
          </nav>
          <div className="topbar-actions" hidden={section !== 'market'}>
            <div className="source"><span>{historical ? 'T-Invest MCP' : 'T-Invest API'}</span><span className="source-mode">{historical ? 'Исторический режим' : 'Песочница'}</span></div>
            {!historical && <button className="icon-button" aria-label="Обновить рыночные данные" title="Обновить рыночные данные"
              type="button" disabled={loading} onClick={refresh}>
              <RefreshCw size={16} className={loading ? 'rotating' : undefined} aria-hidden="true" />
            </button>}
          </div>
        </div>
      </header>

      <main className="workspace" hidden={section !== 'market'}>
        <aside className="symbols" aria-labelledby="symbols-title">
          <div className="symbols-heading"><h2 id="symbols-title">Инструменты</h2><span>₽</span></div>
          <div className="symbol-list">
            {symbols.map((symbol) => {
              const record = rows.find((row) => row.ticker === symbol.ticker);
              const quote = historical ? undefined : record?.quote;
              const price = historical && symbol.ticker === shownTicker ? headerPrice : quote?.price;
              return (
                <button className="symbol" type="button" key={symbol.ticker} aria-pressed={shownTicker === symbol.ticker}
                  title={record?.name || symbol.name} disabled={historical} onClick={() => setTicker(symbol.ticker)}>
                  <span className="symbol-name"><strong>{symbol.ticker}</strong><small>{record?.name || symbol.name}</small></span>
                  <span className="symbol-price figures" title={quote ? marketTime(quote.time) : historical ? undefined : record?.issue?.message}>
                    {price !== undefined ? number.format(price) : '—'}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="symbols-footer" role="status">
            {historical ? '' : quotes.status === 'loading' ? 'Загружаем котировки…'
              : quoteIssue?.message ?? (rows.some((row) => row.quote) ? '' : 'Нет последних цен в песочнице.')}
          </p>
        </aside>

        <section className="market-panel" aria-labelledby="instrument-title">
          <div className="market-heading">
            <div className="asset-heading">
              <img className="symbol-logo" src={instrument.logo} alt="" width={50} height={50} />
              <div>
                <h1 id="instrument-title">{(!historical && selectedQuote?.name) || instrument.name}</h1>
                <div className="instrument-context"><strong>{shownTicker}</strong><span>{historical ? '22 мая 2025 · Московская биржа' : 'Московская биржа'}</span></div>
              </div>
            </div>
            <div className="market-price">
              <strong className="figures">{headerPrice !== undefined ? <>{number.format(headerPrice)} <span>₽</span></> : '—'}</strong>
              <div className="quote-meta">
                <span>{historical ? 'Закрытие свечи' : 'Последняя сделка'}</span>
                <span className="figures">{historical && lastBar ? marketTime(lastBar.time + 3600)
                  : selectedQuote?.quote ? marketTime(selectedQuote.quote.time)
                  : quotes.status === 'loading' ? 'Загрузка…' : selectedQuote?.issue || quotes.status === 'error' ? 'Цена недоступна' : 'Нет последней цены'}</span>
              </div>
            </div>
          </div>

          <div className="chart-panel">
            <div className="chart-toolbar">
              <h2>Свечной график</h2>
              <div className="intervals" role="group" aria-label="Интервал свечей">
                {intervals.map((option) => (
                  <button type="button" key={option.value} aria-pressed={option.value === shownInterval}
                    disabled={historical} onClick={() => setInterval(option.value)}>{option.label}</button>
                ))}
              </div>
            </div>
            {lastBar ? (
              <Chart key={historical ? 'replay:gazprom' : `${ticker}:${interval}`} candles={bars} interval={shownInterval} />
            ) : (
              <div className="chart-state" role="status">
                <div className="chart-state-content">
                  <span className="chart-state-icon" aria-hidden="true">
                    {candles.status === 'loading' ? <RefreshCw size={21} className="rotating" />
                      : chartIssue ? <CircleAlert size={23} /> : <ChartCandlestick size={23} />}
                  </span>
                  <h3>{chartState.title}</h3>
                  <p>{chartState.description}</p>
                  {candles.status !== 'loading' && <button className="retry" type="button" onClick={refresh}>Повторить запрос</button>}
                </div>
              </div>
            )}
            <div className="chart-footer">
              <span><Clock3 size={14} aria-hidden="true" /> {lastBar
                ? <>Последняя свеча · <span className="figures">{marketTime(lastBar.time)}</span>{lastBar.complete ? '' : ' · формируется'}</>
                : 'Время по Москве'}</span>
              <span className="chart-credit">₽ за акцию{lastBar && <small title="TradingView Lightweight Charts™">© 2025 TradingView, Inc.</small>}</span>
            </div>
          </div>
        </section>

        <Navigator event={event} profile={replayProfile} running={replayRunning} replay={historical}
          loading={replayResource.status === 'loading'} issue={replayIssue} threshold={episode?.thresholdPercent}
          onPlay={playReplay} onExit={() => setReplayCount(null)} />
      </main>
      <AgentStudio visible={section === 'studio'} analysisConfig={config}
        analysisConfigFailed={configResource.status === 'error'} profile={normalizeProfile(savedProfile, config)}
        onProfileChange={(profile) => {
          setSavedProfile(profile);
          saveProfile(profile);
        }} />
    </>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><Terminal /></StrictMode>);
