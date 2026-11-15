import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ChartCandlestick, CircleAlert, Clock3, Radar, RefreshCw } from 'lucide-react';
import '@fontsource-variable/inter/wght.css';
import { AgentStudio } from './AgentStudio';
import { Chart } from './Chart';
import { Navigator } from './Navigator';
import { marketTime, number, symbols, useMarketResource, type Candle, type Interval, type QuoteRow, type Ticker } from './market';
import './style.css';
import './studio.css';

const intervals = [{ value: '1h', label: '1ч' }, { value: '1d', label: '1д' }] as const;

function Terminal() {
  const [section, setSection] = useState<'market' | 'studio'>('market');
  const [ticker, setTicker] = useState<Ticker>('GAZP');
  const [interval, setInterval] = useState<Interval>('1h');
  const [revision, setRevision] = useState(0);
  const quotes = useMarketResource<QuoteRow[]>('/api/quotes', revision);
  const candles = useMarketResource<Candle[]>(`/api/candles/${ticker}?interval=${interval}`, revision);
  const instrument = symbols.find((item) => item.ticker === ticker)!;
  const rows = quotes.status === 'ready' ? quotes.data : [];
  const selectedQuote = rows.find((row) => row.ticker === ticker);
  const quoteIssue = quotes.status === 'error' ? quotes.issue : rows.find((row) => row.issue)?.issue;
  const chartIssue = candles.status === 'error' ? candles.issue : null;
  const bars = candles.status === 'ready' ? candles.data : [];
  const lastBar = bars[bars.length - 1];
  const loading = quotes.status === 'loading' || candles.status === 'loading';

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
            <div className="source"><span>T-Invest API</span><span className="source-mode">Песочница</span></div>
            <button className="icon-button" aria-label="Обновить рыночные данные" title="Обновить рыночные данные"
              type="button" disabled={loading} onClick={refresh}>
              <RefreshCw size={16} className={loading ? 'rotating' : undefined} aria-hidden="true" />
            </button>
          </div>
        </div>
      </header>

      <main className="workspace" hidden={section !== 'market'}>
        <aside className="symbols" aria-labelledby="symbols-title">
          <div className="symbols-heading"><h2 id="symbols-title">Инструменты</h2><span>₽</span></div>
          <div className="symbol-list">
            {symbols.map((symbol) => {
              const record = rows.find((row) => row.ticker === symbol.ticker);
              return (
                <button className="symbol" type="button" key={symbol.ticker} aria-pressed={ticker === symbol.ticker}
                  title={record?.name || symbol.name} onClick={() => setTicker(symbol.ticker)}>
                  <span className="symbol-name"><strong>{symbol.ticker}</strong><small>{record?.name || symbol.name}</small></span>
                  <span className="symbol-price figures" title={record?.quote ? marketTime(record.quote.time) : record?.issue?.message}>
                    {record?.quote ? number.format(record.quote.price) : '—'}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="symbols-footer" role="status">
            {quotes.status === 'loading' ? 'Загружаем котировки…'
              : quoteIssue?.message ?? (rows.some((row) => row.quote) ? '' : 'Нет последних цен в песочнице.')}
          </p>
        </aside>

        <section className="market-panel" aria-labelledby="instrument-title">
          <div className="market-heading">
            <div className="asset-heading">
              <img className="symbol-logo" src={instrument.logo} alt="" width={50} height={50} />
              <div>
                <h1 id="instrument-title">{selectedQuote?.name || instrument.name}</h1>
                <div className="instrument-context"><strong>{ticker}</strong><span>Московская биржа</span></div>
              </div>
            </div>
            <div className="market-price">
              <strong className="figures">{selectedQuote?.quote ? <>{number.format(selectedQuote.quote.price)} <span>₽</span></> : '—'}</strong>
              <div className="quote-meta">
                <span>Последняя сделка</span>
                <span className="figures">{selectedQuote?.quote ? marketTime(selectedQuote.quote.time)
                  : quotes.status === 'loading' ? 'Загрузка…' : selectedQuote?.issue || quotes.status === 'error' ? 'Цена недоступна' : 'Нет последней цены'}</span>
              </div>
            </div>
          </div>

          <div className="chart-panel">
            <div className="chart-toolbar">
              <h2>Свечной график</h2>
              <div className="intervals" role="group" aria-label="Интервал свечей">
                {intervals.map((option) => (
                  <button type="button" key={option.value} aria-pressed={option.value === interval}
                    onClick={() => setInterval(option.value)}>{option.label}</button>
                ))}
              </div>
            </div>
            {lastBar ? (
              <Chart key={`${ticker}:${interval}`} candles={bars} interval={interval} />
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

        <Navigator />
      </main>
      <AgentStudio visible={section === 'studio'} />
    </>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><Terminal /></StrictMode>);
