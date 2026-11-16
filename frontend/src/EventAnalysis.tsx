import { ChevronDown, CircleAlert, CircleCheck } from 'lucide-react';
import { AgentSteps, type AgentStep } from './AgentSteps';
import { marketTime, number } from './market';
import type { AnalysisResult, AnalysisState, CheckName, CheckStatus, Statement } from './analysis';

const checks: Record<CheckName, string> = {
  news: 'Новости', market: 'Индекс Мосбиржи', dividends: 'Дивиденды', reports: 'Отчётность',
};
const statuses: Record<CheckStatus, string> = {
  ok: 'Проверено', empty: 'Данные не найдены', unavailable: 'Источник недоступен', disabled: 'Выключено',
};
const percent = new Intl.NumberFormat('ru-RU', {
  style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2,
});

function Statements({ title, items }: { title: string; items: Statement[] }) {
  if (items.length === 0) return null;
  return <div>
    <h5>{title}</h5>
    <ul>{items.map((item, index) => <li key={index}>
      {item.text}
      <span className="event-citations">{item.citations.map((source) => source.url
        ? <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer"
            title={source.title}>{source.source ?? 'Источник'}</a>
        : <span key={source.id} title={source.title}>{source.source ?? source.title}</span>)}</span>
    </li>)}</ul>
  </div>;
}

export function EventAnalysis({ state }: { state: AnalysisState }) {
  if (state.status === 'error' || state.status === 'done') {
    const status = state.status === 'error' || state.llm === 'failed' ? 'failed' : state.llm;
    const partial = state.status === 'done' && Object.values(state.checks).some(({ status }) => status === 'unavailable');
    return <>
      <div className="event-analysis-status" data-status={status} role={status === 'failed' ? 'alert' : 'status'}>
        {status === 'failed' && <CircleAlert size={16} aria-hidden="true" />}
        {status === 'ready' && <CircleCheck size={16} aria-hidden="true" />}
        <div>
          <h4>{status === 'failed' ? 'ИИ-разбор недоступен'
            : status === 'ready' ? 'ИИ-разбор готов' : 'ИИ-разбор пропущен'}</h4>
          {state.reason && <p>{state.reason}</p>}
          {partial && <p>Часть источников недоступна.</p>}
        </div>
      </div>
      {state.status === 'done' && <AnalysisDetails state={state} />}
    </>;
  }

  const collecting = state.status === 'collecting';
  const steps: AgentStep[] = [
    {
      id: 'sources', label: 'Проверяем источники',
      status: collecting ? 'running' : 'done',
      log: collecting ? ['Собираем данные на момент сигнала',
        ...(Object.entries(state.completedChecks ?? {}) as [CheckName, CheckStatus][]).map(([name, status]) =>
          `${checks[name]} · ${statuses[status]}`)] : undefined,
    },
    {
      id: 'synthesis', label: 'Готовим ИИ-разбор',
      status: collecting ? 'pending' : 'running',
      log: ['Модель анализирует данные и источники'],
    },
  ];
  return <AgentSteps steps={steps} />;
}

function AnalysisDetails({ state }: { state: AnalysisResult }) {
  const comparison = state.checks.market.facts.comparison;
  const dividends = state.checks.dividends.facts;
  const recommendationCited = state.synthesis?.facts.some((fact) =>
    fact.citations.some((source) => source.id === dividends.materialId));
  const materials = [...new Map(Object.values(state.checks).flatMap(({ materials }) =>
    materials.map((item) => [item.id, item] as const))).values()];
  const recommendationInMaterials = materials.some((item) => item.id === dividends.materialId);

  return <>
    {state.synthesis && <div className="event-analysis">
      <Statements title="Подтверждённые факты" items={state.synthesis.facts} />
      <Statements title="Возможные объяснения" items={state.synthesis.hypotheses} />
      {state.synthesis.questions.length > 0 && <div>
        <h5>Открытые вопросы</h5>
        <ul>{state.synthesis.questions.map((question, index) => <li key={index}>{question}</li>)}</ul>
      </div>}
    </div>}
    <details className="event-disclosure">
      <summary>Проверка источников <ChevronDown size={16} aria-hidden="true" /></summary>
      <div className="event-analysis event-disclosure-content">
        <dl className="event-sources" aria-label="Статус источников">
          {(Object.keys(checks) as CheckName[]).map((name) => {
            const { status, reason } = state.checks[name];
            return <div key={name} data-status={status}>
              <dt>{checks[name]}</dt><dd>{statuses[status]}</dd>
              {reason && (status !== 'ok' || name === 'reports') && <dd className="event-source-reason">{reason}</dd>}
            </div>;
          })}
        </dl>
        {comparison && <p>Индекс Мосбиржи <strong className="figures">{percent.format(comparison.changePercent / 100)}</strong> за тот же час</p>}
        {dividends.recommendation && !recommendationInMaterials && !recommendationCited && <p>{dividends.recommendation}</p>}
        {dividends.payments?.map((item) => <p key={item.materialId}>
          {number.format(item.amount)} {item.currency.toUpperCase()} на акцию · объявлено {item.declaredDate} · последний день покупки {item.lastBuyDate}
          {item.possibleDividendGap && <>. Размер выплаты близок к ценовому разрыву и может его объяснять.</>}
        </p>)}
        {state.checks.reports.facts.calendar?.map((item) =>
          <p key={item.createdAt}>Дата в календаре · {item.scheduledDate}</p>)}
        {materials.length > 0 && <ul>{materials.map((item) => <li key={item.id}>
          {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a> : item.title}
          <small className="event-news-source"> {item.source && `${item.source} · `}{marketTime(item.publishedAt)}
            {item.headlineOnly && ' · Только заголовок'}</small>
          {item.text && <p>{item.text}</p>}
        </li>)}</ul>}
      </div>
    </details>
  </>;
}
