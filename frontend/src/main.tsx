import { StrictMode, useEffect, useLayoutEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ChartCandlestick, CircleAlert, Clock3, RefreshCw } from 'lucide-react';
import '@fontsource-variable/inter/wght.css';
import { normalizeProfile, readProfile, saveProfile, type AnalysisConfig, type Profile } from './analysis';
import { AgentStudio } from './AgentStudio';
import { CandleIntervalControl } from './CandleIntervalControl';
import { Chart } from './Chart';
import { Navigator } from './Navigator';
import { EpisodePicker } from './EpisodePicker';
import { SpringDropdown } from './SpringDropdown';
import { ThemeSwitch, readTheme, saveTheme } from './ThemeSwitch';
import { WorkspaceNav } from './WorkspaceNav';
import { storageKey } from './scenarios';
import { loadStudio, studioSettingsKey, type StudioState } from './studioSettings';
import { marketTime, number, symbols, allSymbols, useMarketResource, type Candle, type Interval, type QuoteRow, type Ticker } from './market';
import { matchesReplayScenario, supportsReplayScenario, type EpisodeMetadata, type ReplayEpisode } from './replay';
import './style.css';
import './studio.css';

const modeOptions = [
  { value: 'historical', label: 'Исторический режим' },
  { value: 'live', label: 'Реальный режим (недоступен)', disabled: true },
] as const;

function Terminal() {
  const [theme, setTheme] = useState(readTheme);
  const [section, setSection] = useState<'market' | 'studio'>('market');
  const [activeScenariosOnly, setActiveScenariosOnly] = useState(false);
  const [studio, setStudio] = useState(loadStudio);
  const [ticker, setTicker] = useState<Ticker>('GAZP');
  const [interval, setInterval] = useState<Interval>('1h');
  const [revision, setRevision] = useState(0);
  const [replayRevision, setReplayRevision] = useState(0);
  const [episodeId, setEpisodeId] = useState('gazp-2025-05-22');
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState('1');
  const [replayCount, setReplayCount] = useState<number | null>(null);
  const [savedProfile, setSavedProfile] = useState(readProfile);
  const [apiKey, setApiKey] = useState('');
  const [replaySettings, setReplaySettings] = useState<{
    profile: Profile; apiKey: string; runId?: string; studio?: StudioState;
  }>({
    profile: {}, apiKey: '',
  });
  const configResource = useMarketResource<AnalysisConfig>('/api/analysis/config', 0, false);
  const config = configResource.status === 'ready' ? configResource.data : undefined;
  const quotes = useMarketResource<QuoteRow[]>('/api/quotes', revision);
  const candles = useMarketResource<Candle[]>(`/api/candles/${ticker}?interval=${interval}`, revision);
  const catalogResource = useMarketResource<EpisodeMetadata[]>('/api/replay/episodes', replayRevision, false);
  const catalog = catalogResource.status === 'ready' ? catalogResource.data : [];
  const replayResource = useMarketResource<ReplayEpisode>(`/api/replay/episodes/${episodeId}`, replayRevision, false);
  const episode = replayResource.status === 'ready' ? replayResource.data : null;
  const historical = replayCount !== null;
  const replayRunning = replayCount !== null && episode !== null && replayCount < episode.candles.length;
  const metadata = episode?.metadata ?? catalog.find((item) => item.id === episodeId);
  const shownTicker = historical && metadata ? metadata.ticker : ticker;
  const shownInterval = historical ? '1h' : interval;
  const instrument = allSymbols.find((item) => item.ticker === shownTicker)!;
  const rows = quotes.status === 'ready' ? quotes.data : [];
  const selectedQuote = rows.find((row) => row.ticker === ticker);
  const quoteIssue = quotes.status === 'error' ? quotes.issue : rows.find((row) => row.issue)?.issue;
  const chartIssue = candles.status === 'error' ? candles.issue : null;
  const bars = historical ? episode?.candles.slice(0, replayCount) ?? []
    : candles.status === 'ready' ? candles.data : [];
  const lastBar = bars[bars.length - 1];
  const replayStudio = replaySettings.studio;
  const eligible = replayStudio?.scenarios.filter((scenario) => supportsReplayScenario(scenario, metadata?.ticker)
    && replayStudio.settings.agents.some((agent) => agent.id === scenario.agentId));
  const candidate = episode?.frames?.find((frame) => eligible?.some((scenario) => matchesReplayScenario(scenario, frame)));
  const event = historical && candidate && lastBar?.time >= candidate.candleTime ? candidate : null;
  const replayIssue = replayResource.status === 'error' ? replayResource.issue.message
    : catalogResource.status === 'error' ? catalogResource.issue.message : null;
  const headerPrice = historical ? lastBar?.close : selectedQuote?.quote?.price;
  const loading = quotes.status === 'loading' || candles.status === 'loading';

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    const color = getComputedStyle(document.documentElement).getPropertyValue('--background').trim();
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', color);
  }, [theme]);

  useEffect(() => {
    function sync(event: StorageEvent) {
      if (event.key === storageKey || event.key === studioSettingsKey || event.key === null) setStudio(loadStudio());
    }
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  useEffect(() => {
    if (!replayRunning || replayCount === null || paused) return;
    const timer = window.setTimeout(() => setReplayCount((count) => count === null ? null : count + 1), 1100 / Number(speed));
    return () => window.clearTimeout(timer);
  }, [replayRunning, replayCount, paused, speed, episodeId]);

  function playReplay() {
    if (episode) {
      const profile = normalizeProfile(savedProfile, config);
      setReplaySettings({
        profile, apiKey: profile.provider === 'cloud' ? apiKey.trim() : '', runId: crypto.randomUUID(), studio,
      });
      setPaused(false);
      setReplayCount(episode.warmupCount);
    } else setReplayRevision((value) => value + 1);
  }

  function selectEpisode(id: string) {
    setReplayCount(null);
    setPaused(false);
    setReplaySettings({ profile: {}, apiKey: '' });
    setEpisodeId(id);
  }

  function openStudio() {
    setActiveScenariosOnly(true);
    setSection('studio');
    requestAnimationFrame(() => document.getElementById('saved-scenarios-title')?.focus());
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
            <img className="brand-mark" src="/logos/marketing.svg" alt="" width={34} height={34} />
            <span>AI Штурман</span>
          </div>
          <WorkspaceNav section={section} onChange={(destination) => {
            setSection(destination);
            setActiveScenariosOnly(false);
          }} />
          <div className="topbar-actions">
            <div className="market-actions" hidden={section !== 'market'}>
              <div className="mode-picker">
                <SpringDropdown floating label="Режим работы" options={modeOptions} value="historical" />
              </div>
              {!historical && <button className="icon-button" aria-label="Обновить рыночные данные" title="Обновить рыночные данные"
                type="button" disabled={loading} onClick={refresh}>
                <RefreshCw size={16} className={loading ? 'rotating' : undefined} aria-hidden="true" />
              </button>}
            </div>
            <ThemeSwitch theme={theme} onChange={(nextTheme) => {
              setTheme(nextTheme);
              saveTheme(nextTheme);
            }} />
          </div>
        </div>
      </header>

      <main className="workspace" hidden={section !== 'market'}>
        <aside className="symbols" aria-labelledby="symbols-title">
          <div className="symbols-heading"><h2 id="symbols-title">Инструменты</h2><span>₽</span></div>
          <div className="symbol-list">
            {(historical && metadata && !symbols.some((item) => item.ticker === metadata.ticker)
              ? [...symbols, instrument] : symbols).map((symbol) => {
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
                <div className="instrument-context"><strong>{shownTicker}</strong><span>{historical ? `${metadata?.date} · ${metadata?.kind === 'synthetic' ? 'Симуляция' : 'Московская биржа'}` : 'Московская биржа'}</span></div>
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

          {historical && metadata?.kind === 'synthetic' && <div className="simulation-banner" role="note">
            <strong>Симуляция</strong><span>Вымышленные цены, индекс и сообщения. Учебный инструмент DEMO.</span>
          </div>}
          {historical && metadata?.ticker === 'BELU' && <div className="corporate-banner" role="note">
            <strong>Корпоративное действие</strong><span>Исходные цены без корректировки. Разрыв цены одной акции не равен убытку портфеля.</span>
          </div>}
          <div className="chart-panel">
            <div className="chart-toolbar">
              <h2>Свечной график</h2>
              <CandleIntervalControl value={shownInterval} disabled={historical} onChange={setInterval} />
            </div>
            {lastBar ? (
              <Chart key={historical ? `replay:${episodeId}` : `${ticker}:${interval}`} candles={bars} interval={shownInterval} theme={theme} />
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

        <Navigator key={episodeId} event={event} profile={replaySettings.profile} apiKey={replaySettings.apiKey} runId={replaySettings.runId}
          running={replayRunning} replay={historical}
          loading={replayResource.status === 'loading'} issue={replayIssue}
          studio={studio} replayStudio={replayStudio} onOpenStudio={openStudio}
          episodePicker={<EpisodePicker episodes={catalog} selected={episodeId} metadata={metadata}
            historical={historical} paused={paused} finished={historical && !replayRunning}
            progress={episode && replayCount !== null ? replayCount - episode.warmupCount : 0}
            total={episode ? episode.candles.length - episode.warmupCount : 0} speed={speed} issue={replayIssue}
            onSelect={selectEpisode} onPause={() => setPaused((value) => !value)}
            onStep={() => { setPaused(true); setReplayCount((count) => count === null || !episode ? count : Math.min(episode.candles.length, count + 1)); }}
            onSpeed={setSpeed} onRetry={() => setReplayRevision((value) => value + 1)} />}
          onPlay={playReplay} onExit={() => { setReplayCount(null); setPaused(false); }} />
      </main>
      <AgentStudio visible={section === 'studio'} studio={studio} setStudio={setStudio} analysisConfig={config}
        activeScenariosOnly={activeScenariosOnly} onActiveScenariosOnlyChange={setActiveScenariosOnly}
        analysisConfigFailed={configResource.status === 'error'} profile={normalizeProfile(savedProfile, config)}
        apiKey={apiKey} onApiKeyChange={setApiKey}
        onProfileChange={(profile) => {
          saveProfile(profile);
          setSavedProfile(profile);
        }} />
    </>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><Terminal /></StrictMode>);
