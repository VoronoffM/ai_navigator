import { useMemo, useState } from 'react';
import { Play, RotateCcw, Square } from 'lucide-react';
import { number } from './market';
import { EventAnalysis } from './EventAnalysis';
import { SiriOrb } from './SiriOrb';
import { useAnalysis, type Profile } from './analysis';
import { matchesReplayScenario, type ReplayEvent } from './replay';
import { defaultScenarioChecks } from './scenarios';
import { activeStudioScenarios, agentPalette, type StudioState } from './studioSettings';

const percent = new Intl.NumberFormat('ru-RU', {
  style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2,
});
const scoreNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });

const hour = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
});
const day = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', day: 'numeric', month: 'long',
});

const scenarioPlural = new Intl.PluralRules('ru-RU');
const scenarioCountLabels: Partial<Record<Intl.LDMLPluralRule, string>> = {
  one: 'активный сценарий',
  few: 'активных сценария',
};

type NavigatorProps = {
  event: ReplayEvent | null;
  profile: Profile;
  apiKey: string;
  runId?: string;
  running: boolean;
  replay: boolean;
  loading: boolean;
  issue: string | null;
  studio: StudioState;
  replayStudio?: StudioState;
  onOpenStudio: () => void;
  onPlay: () => void;
  onExit: () => void;
};

const telegramStatus = {
  pending: 'Отправляем отчёт в Telegram…',
  sent: 'Отчёт отправлен в Telegram.',
  failed: 'Доставка отчёта в Telegram не подтверждена.',
  unconnected: 'Подключите Telegram в Agent Studio, чтобы получать отчёты.',
};

export function Navigator({ event, profile, apiKey, runId, running, replay, loading, issue,
  studio, replayStudio, onOpenStudio, onPlay, onExit }: NavigatorProps) {
  const [selectedScenario, setSelectedScenario] = useState('');
  const agents = replayStudio?.settings.agents ?? [];
  const matching = event && replayStudio ? replayStudio.scenarios.filter((scenario) => matchesReplayScenario(scenario, event)
    && agents.some((agent) => agent.id === scenario.agentId)) : [];
  const workflows = matching.filter((item) => item.actions);
  const scenario = workflows.find((item) => item.id === selectedScenario) ?? workflows.at(-1);
  const legacyScenario = matching.find((item) => agents.some((agent) =>
    agent.id === item.agentId && agent.provider === (profile.provider ?? 'ollama')));
  const matchedScenario = scenario ?? legacyScenario;
  const agentIndex = agents.findIndex((item) =>
    item.id === matchedScenario?.agentId);
  const agent = agents[agentIndex];
  const executionProfile = useMemo<Profile>(() => {
    if (!scenario?.actions || !agent) return profile;
    return {
      ...profile,
      provider: agent.provider,
      checks: scenario.checks ?? defaultScenarioChecks,
      workflow: { actions: scenario.actions, depth: scenario.depth, instructions: scenario.instructions },
    };
  }, [agent, profile, scenario]);
  const telegram = useMemo(() => runId && matchedScenario?.notification === 'telegram'
    ? { run_id: runId, scenario_id: matchedScenario.id, name: matchedScenario.name }
    : undefined, [runId, matchedScenario]);
  const analysis = useAnalysis(event?.event_id, executionProfile, apiKey, telegram);
  const analysisPending = analysis?.status === 'collecting' || analysis?.status === 'analyzing';
  const canStop = running || analysisPending;
  const PlayIcon = canStop ? Square : replay || issue ? RotateCcw : Play;
  const eventStatus = issue ?? (replay && !running ? 'В этом эпизоде сигнал не сработал.' : null);
  const loadingStatus = analysisPending ? (analysis.status === 'analyzing' ? 'Готовим ИИ-разбор' : 'Собираем данные для разбора')
    : running && !event ? 'Воспроизводим эпизод'
      : loading ? 'Загружаем исторический эпизод' : null;

  return (
    <aside className="navigator" aria-labelledby="navigator-title">
      <header className="navigator-heading">
        <SiriOrb />
        <h2 id="navigator-title">AI Штурман</h2>
        <div className="navigator-loading" role="status">
          {loadingStatus && <>
            <span className="navigator-spinner" aria-hidden="true" />
            <span className="navigator-loading-label">{loadingStatus}</span>
          </>}
        </div>
      </header>

      <ScenarioMonitor studio={studio} onOpenStudio={onOpenStudio} />

      {(event || eventStatus) && <section className="navigator-event" aria-label="Событие">
        {event ? (
          <article className="event-card">
            <header className="event-heading">
              <h3 aria-live="polite">{event.ticker} <span className="event-drop figures">{percent.format(event.changePercent / 100)}</span></h3>
              <p className="event-context figures">{number.format(event.previousClose)} → {number.format(event.close)} ₽</p>
              <p className="event-window figures">
                {day.format(event.detectedAt * 1000)}, {hour.format(event.candleTime * 1000)}–{hour.format(event.detectedAt * 1000)} МСК
              </p>
              {event.priceZ != null && matching.some((item) => item.trigger === 'price-z') &&
                <p className="event-context figures">Движение цены · {scoreNumber.format(Math.abs(event.priceZ))}σ</p>}
              {event.volumeRatio != null && matching.some((item) => item.trigger === 'volume-spike') &&
                <p className="event-context figures">Объём · {scoreNumber.format(event.volumeRatio)}× обычного</p>}
              {event.indexChangePercent != null && event.marketZ != null && matching.some((item) => item.trigger === 'relative') &&
                <p className="event-context figures">IMOEX {percent.format(event.indexChangePercent / 100)} · разница {scoreNumber.format(event.changePercent - event.indexChangePercent)} п.п.</p>}
              {scenario && workflows.length > 1 && <label className="event-workflow">Сценарий
                <select value={scenario.id} onChange={(change) => setSelectedScenario(change.target.value)}>
                  {workflows.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
              </label>}
              {scenario && agent && analysis?.status !== 'done' && <p className="event-window">{agent.name}</p>}
              {analysis?.status === 'done' && analysis.telegram &&
                <p className="event-window" role="status">{telegramStatus[analysis.telegram]}</p>}
            </header>
            {analysis && <EventAnalysis key={event.event_id} state={analysis}
              agentName={agent?.name} palette={agentPalette(agentIndex)} />}
          </article>
        ) : (
          <p className="event-placeholder" role={issue ? 'alert' : 'status'}>
            {eventStatus}
          </p>
        )}
      </section>}
      <div className="replay-controls">
        <button type="button" className={canStop || event ? 'button button-stop' : 'button button-primary'}
          disabled={!canStop && loading} onClick={canStop ? onExit : onPlay}>
          <PlayIcon size={15} aria-hidden="true" />
          {canStop ? 'Остановить' : issue ? 'Повторить загрузку' : replay ? 'Повторить эпизод' : 'Воспроизвести эпизод'}
        </button>
      </div>
    </aside>
  );
}

function ScenarioMonitor({ studio, onOpenStudio }: {
  studio: StudioState;
  onOpenStudio: () => void;
}) {
  const count = activeStudioScenarios(studio).length;
  const hasIssue = studio.issues.length > 0;
  const countLabel = scenarioCountLabels[scenarioPlural.select(count)] ?? 'активных сценариев';

  return (
    <section className="scenario-monitor" aria-labelledby="scenario-monitor-title">
      <h3 id="scenario-monitor-title" className="figures" aria-live="polite" aria-atomic="true">
        {hasIssue ? 'Сценарии' : `${count} ${countLabel}`}
      </h3>
      <button className="scenario-monitor-manage" type="button" onClick={onOpenStudio}
        aria-label="Управлять сценариями в Agent Studio">Управлять</button>
    </section>
  );
}
