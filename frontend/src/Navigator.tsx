import { Activity, ChartNoAxesColumnIncreasing, ChevronDown, Newspaper, Play, RotateCcw, Square, Waves } from 'lucide-react';
import { number } from './market';
import { EventAnalysis } from './EventAnalysis';
import { SiriOrb } from './SiriOrb';
import { useAnalysis, type Profile } from './analysis';
import type { ReplayEvent } from './replay';
import { describeTrigger, type Trigger } from './scenarios';
import type { StudioState } from './studioSettings';

const percent = new Intl.NumberFormat('ru-RU', {
  style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2,
});

const hour = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
});
const day = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', day: 'numeric', month: 'long',
});

const signalIcons = {
  price: Activity,
  volume: ChartNoAxesColumnIncreasing,
  news: Newspaper,
  volatility: Waves,
} satisfies Record<Trigger, typeof Activity>;

type NavigatorProps = {
  event: ReplayEvent | null;
  profile: Profile;
  openaiKey: string;
  running: boolean;
  replay: boolean;
  loading: boolean;
  issue: string | null;
  threshold: number | undefined;
  studio: StudioState;
  onOpenStudio: () => void;
  onPlay: () => void;
  onExit: () => void;
};

export function Navigator({ event, profile, openaiKey, running, replay, loading, issue, threshold, studio, onOpenStudio, onPlay, onExit }: NavigatorProps) {
  const analysis = useAnalysis(event?.event_id, profile, openaiKey);
  const canStop = running || analysis?.status === 'collecting' || analysis?.status === 'analyzing';
  const PlayIcon = canStop ? Square : replay || issue ? RotateCcw : Play;

  return (
    <aside className="navigator" aria-labelledby="navigator-title">
      <header className="navigator-heading">
        <SiriOrb />
        <h2 id="navigator-title">AI Штурман</h2>
      </header>

      <ScenarioMonitor studio={studio} onOpenStudio={onOpenStudio} />

      <section className="navigator-event" aria-label="Событие">
        {event ? (
          <article className="event-card">
            <header className="event-heading">
              <h3 aria-live="polite">{event.ticker} <span className="event-drop figures">{percent.format(event.changePercent / 100)}</span></h3>
              <p className="event-context figures">{number.format(event.previousClose)} → {number.format(event.close)} ₽</p>
              <p className="event-window figures">
                {day.format(event.detectedAt * 1000)}, {hour.format(event.candleTime * 1000)}–{hour.format(event.detectedAt * 1000)} МСК
              </p>
            </header>
            {analysis && <EventAnalysis key={event.event_id} state={analysis} />}
            <details className="event-disclosure event-rule" key={event.event_id}>
              <summary>Как сработал сигнал <ChevronDown size={16} aria-hidden="true" /></summary>
              <p className="event-disclosure-content">{event.rule}</p>
            </details>
          </article>
        ) : (
          <p className="event-placeholder" role={issue ? 'alert' : 'status'}>
            {issue ?? (running ? 'Проверяем закрытия часовых свечей…'
              : replay ? 'В этом эпизоде сигнал не сработал.'
                : loading ? 'Загружаем исторический эпизод…'
                  : threshold == null ? 'Сигнал появится во время воспроизведения эпизода.'
                    : `Сигнал появится при снижении на ${threshold}% или больше за час.`)}
          </p>
        )}
      </section>
      <div className="replay-controls">
        <button type="button" className={canStop || event ? 'button button-stop' : 'button button-primary'}
          disabled={!canStop && loading} onClick={canStop ? onExit : onPlay}>
          <PlayIcon size={15} aria-hidden="true" />
          {canStop ? 'Остановить' : issue ? 'Повторить загрузку' : replay ? 'Повторить эпизод' : 'Воспроизвести эпизод'}
        </button>
        {replay && !canStop && (
          <button type="button" className="replay-exit" onClick={onExit}>Вернуться к рынку</button>
        )}
        {!replay && <span className="replay-caption">GAZP · 22 мая 2025</span>}
      </div>
    </aside>
  );
}

function ScenarioMonitor({ studio, onOpenStudio }: { studio: StudioState; onOpenStudio: () => void }) {
  const agents = new Map(studio.settings.agents.map((agent) => [agent.id, agent]));
  const rows = studio.scenarios.flatMap((scenario) => {
    const agent = scenario.agentId && agents.get(scenario.agentId);
    if (!scenario.enabled || !agent) return [];
    const Icon = signalIcons[scenario.trigger];
    return [(
      <li key={scenario.id} className="scenario-monitor-row">
        <span className="scenario-monitor-icon" data-trigger={scenario.trigger} aria-hidden="true"><Icon size={17} /></span>
        <div className="scenario-monitor-copy">
          <strong>{scenario.name}</strong>
          <span>{describeTrigger(scenario)}</span>
          <div className="scenario-monitor-meta">
            <span className="scenario-monitor-assets">{scenario.assets.join(', ')}</span>
            <span>{agent.name}</span>
          </div>
        </div>
      </li>
    )];
  });

  return (
    <section className="scenario-monitor" aria-labelledby="scenario-monitor-title">
      <header className="scenario-monitor-heading">
        <h3 id="scenario-monitor-title">Включённые сценарии</h3>
        <button className="scenario-monitor-manage" type="button" onClick={onOpenStudio}
          aria-label="Управлять сценариями в Agent Studio">Управлять</button>
      </header>
      {rows.length > 0 ? (
        <div className="scenario-monitor-panel">
          <ul className="scenario-monitor-list" role="list">{rows.slice(0, 4)}</ul>
          {rows.length > 4 && (
            <details className="scenario-monitor-more">
              <summary>Ещё {rows.length - 4} <ChevronDown size={14} aria-hidden="true" /></summary>
              <ul className="scenario-monitor-list" role="list">{rows.slice(4)}</ul>
            </details>
          )}
        </div>
      ) : (
        <p className="scenario-monitor-empty">{studio.issues.length > 0
          ? 'Не удалось загрузить сценарии. Проверьте настройки в Agent Studio.'
          : 'Включите сценарий с назначенным агентом в Agent Studio.'}</p>
      )}
    </section>
  );
}
