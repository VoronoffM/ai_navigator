// Adapted from SmoothUI AI Task List by Eduardo Calvo.
import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import './agentSteps.css';

type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';
export type AgentStep = {
  id: string;
  label: string;
  status: StepStatus;
  note?: string;
  children?: AgentStep[];
};

const statusLabels: Record<StepStatus, string> = {
  pending: 'В ожидании', running: 'В работе', done: 'Завершено', failed: 'Ошибка', skipped: 'Пропущено',
};
const marks: Partial<Record<StepStatus, string>> = {
  done: 'M 3.5 7.5 L 6 10 L 10.5 4.5',
  failed: 'M 5 5 L 9 9 M 9 5 L 5 9',
  skipped: 'M 4.5 7 L 9.5 7',
};

function StepRow({ step }: { step: AgentStep }) {
  const mark = marks[step.status];
  return <li>
    <div className="agent-step" data-status={step.status}>
      <svg className="agent-step-box" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <rect x={1} y={1} width={12} height={12} rx={3.5} strokeWidth={1.4} />
        {mark && <path className="agent-step-mark" d={mark} pathLength={1} strokeDasharray="1 1"
          strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} />}
      </svg>
      <span className="agent-step-label">{step.label}</span>
      <span className="agent-step-sr">{statusLabels[step.status]}</span>
      {step.note && <span className="agent-step-note figures">{step.note}</span>}
    </div>
    {!!step.children?.length && <ul>
      {step.children.map((child) => <StepRow key={child.id} step={child} />)}
    </ul>}
  </li>;
}

export function AgentSteps({ steps, initiallyOpen }: { steps: AgentStep[]; initiallyOpen: boolean }) {
  const listId = useId();
  const [expanded, setExpanded] = useState(initiallyOpen);
  const rows = steps.flatMap((step) => [step, ...(step.children ?? [])]);
  const done = rows.filter(({ status }) => status === 'done').length;

  return <div className="agent-steps">
    <button className="agent-steps-toggle" type="button" aria-expanded={expanded} aria-controls={listId}
      onClick={() => setExpanded(!expanded)}>
      <span>Журнал действий</span>
      <span className="agent-steps-count figures" aria-label={`Завершено ${done} из ${rows.length}`}>{done}/{rows.length}</span>
      <ChevronDown size={16} aria-hidden="true" />
    </button>
    <div className="agent-steps-drawer" data-expanded={expanded} id={listId} inert={!expanded}>
      <div className="agent-steps-clip">
        <ol aria-label="Этапы разбора сигнала">
          {steps.map((step) => <StepRow key={step.id} step={step} />)}
        </ol>
      </div>
    </div>
  </div>;
}
