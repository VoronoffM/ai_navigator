// Motion adapted from Kokonut UI's AI State Loading (MIT).
// https://kokonutui.com/docs/ai/ai-loading
import { useEffect, useId, useState } from 'react';
import { ChevronDown, Minus, X } from 'lucide-react';
import './agentSteps.css';

type StepStatus = 'pending' | 'running' | 'done' | 'skipped' | 'error';
export type AgentStep = { id: string; label: string; status: StepStatus; log?: string[] };

const statusLabels: Record<StepStatus, string> = {
  pending: 'В ожидании', running: 'В работе', done: 'Завершено', skipped: 'Пропущено', error: 'Ошибка',
};

function formatElapsed(seconds: number) {
  if (seconds < 60) return `${seconds} с`;
  return `${Math.floor(seconds / 60)} мин ${String(seconds % 60).padStart(2, '0')} с`;
}

function useElapsed(active: boolean) {
  const [startedAt] = useState(() => performance.now());
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const tick = () => setSeconds(Math.floor((performance.now() - startedAt) / 1000));
    tick();
    if (!active) return;
    const interval = window.setInterval(tick, 500);
    return () => window.clearInterval(interval);
  }, [active, startedAt]);

  return seconds;
}

function StepIcon() {
  return <span className="agent-step-icon" aria-hidden="true">
    <span className="agent-step-dot" data-icon="pending" />
    <span className="agent-step-spinner" data-icon="running" />
    <svg data-icon="done" width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M3.5 8.5 6.5 11.5 12.5 4.5" pathLength="1" stroke="currentColor"
        strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" />
    </svg>
    <Minus data-icon="skipped" size={14} />
    <X data-icon="error" size={14} />
  </span>;
}

function StepRow({ step }: { step: AgentStep }) {
  const { label, status, log = [] } = step;
  const rowHeight = 24;
  const visibleRows = Math.min(log.length, 3);
  return <li className="agent-step" data-status={status}>
    <StepIcon />
    <div className="agent-step-content">
      <span className="agent-step-sr">{label}. {statusLabels[status]}.</span>
      <span aria-hidden="true" className="agent-step-label">
        {status === 'running' ? Array.from(label, (letter, index) =>
          <span key={index} style={{ animationDelay: `${index * 50}ms` }}>{letter}</span>) : label}
      </span>
      {status === 'running' && log.length > 0 && (
        <div className="agent-step-log" data-fade={visibleRows === 3}
          style={{ height: rowHeight * visibleRows }}>
          <div style={{ transform: `translateY(-${rowHeight * (log.length - visibleRows)}px)` }}>
            {log.map((line, index) => <p key={line}>
              <span aria-hidden="true">{index + 1}</span>{line}
            </p>)}
          </div>
        </div>
      )}
    </div>
  </li>;
}

export function AgentSteps({ steps }: { steps: AgentStep[] }) {
  const listId = useId();
  const running = steps.find((step) => step.status === 'running');
  const seconds = useElapsed(Boolean(running));
  const [expanded, setExpanded] = useState(true);
  const title = expanded ? 'ИИ-разбор в работе' : running?.label ?? 'Подготовка разбора';
  const elapsed = formatElapsed(seconds);

  return <div className="agent-steps">
    <button className="agent-steps-toggle" type="button" aria-expanded={expanded} aria-controls={listId}
      onClick={() => setExpanded(!expanded)}>
      <output className="agent-steps-title">{title}</output>
      {(running || seconds > 0) && <span className="agent-steps-time figures">{elapsed}</span>}
      <ChevronDown size={16} aria-hidden="true" />
    </button>
    <div className="agent-steps-drawer" data-expanded={expanded} id={listId} inert={!expanded}>
      <ol aria-label="Этапы разбора сигнала">
        {steps.map((step) => <StepRow key={step.id} step={step} />)}
      </ol>
    </div>
  </div>;
}
