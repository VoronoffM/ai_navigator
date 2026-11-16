import type { ReactNode } from 'react';
import { CircleAlert } from 'lucide-react';
import { AnalysisSummary } from './AnalysisSummary';
import { AgentSteps, type AgentStep } from './AgentSteps';
import { marketTime, number } from './market';
import type { AgentPalette } from './studioSettings';
import type { AnalysisResult, AnalysisState, CheckName, CheckStatus, Statement } from './analysis';

const checks: Record<CheckName, string> = {
  news: 'Новости', market: 'Индекс Мосбиржи', dividends: 'Дивиденды', reports: 'Отчётность',
};
const checkNames = Object.keys(checks) as CheckName[];
const statuses: Record<CheckStatus, string> = {
  ok: 'Проверено', empty: 'Нет данных', unavailable: 'Недоступно', disabled: 'Пропущено',
};
const checkHeadlines: Record<CheckName, Record<CheckStatus, string>> = {
  news: { ok: 'Есть новости к моменту сигнала', empty: 'Новостей не найдено', unavailable: 'Новости недоступны', disabled: 'Новости пропущены' },
  market: { ok: 'Индекс Мосбиржи проверен', empty: 'Нет данных для сравнения', unavailable: 'Индекс недоступен', disabled: 'Сравнение с индексом пропущено' },
  dividends: { ok: 'Есть данные о дивидендах', empty: 'Записей о выплатах нет', unavailable: 'Данные о дивидендах недоступны', disabled: 'Проверка дивидендов пропущена' },
  reports: { ok: 'Есть сведения об отчётности', empty: 'Отчётность не найдена', unavailable: 'Отчётность недоступна', disabled: 'Проверка отчётности пропущена' },
};
const sourceExplanations: Record<CheckStatus, string> = {
  ok: 'Источник проверен на момент сигнала.',
  empty: 'В источнике нет подходящих данных к моменту сигнала.',
  unavailable: 'Не удалось получить данные источника.',
  disabled: 'Проверка отключена в настройках разбора.',
};
const percent = new Intl.NumberFormat('ru-RU', {
  style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2,
});

function Citations({ items }: { items: Statement['citations'] }) {
  if (items.length === 0) return null;

  return <span className="event-citations">{items.map((source) => source.url
    ? <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer"
        title={source.title}>{source.source ?? 'Источник'}</a>
    : <span key={source.id} title={source.title}>{source.source ?? source.title}</span>)}</span>;
}

type AgentIdentity = { agentName?: string; palette?: AgentPalette };

export function EventAnalysis({ state, ...agent }: { state: AnalysisState } & AgentIdentity) {
  if (state.status === 'done') return <AnalysisDetails key={state.id} state={state} {...agent} />;
  if (state.status === 'error') {
    return <div className="event-analysis-status" role="alert">
      <CircleAlert size={16} aria-hidden="true" />
      <div>
        <h4>ИИ-разбор недоступен</h4>
        <p>{state.reason}</p>
      </div>
    </div>;
  }

  return <AgentSteps steps={activitySteps(state)} initiallyOpen />;
}

function activitySteps(state: Exclude<AnalysisState, { status: 'error' }>): AgentStep[] {
  const finished = state.status === 'done';
  const actions = state.actions ?? (state.cbr ? ['mcp', 'cbr'] : ['mcp']);
  const active = state.status === 'collecting'
    ? actions.find((action) => !state.completedActions?.includes(action))
    : undefined;
  const steps: AgentStep[] = [];

  for (const action of actions) {
    if (action === 'mcp') {
      const names = finished
        ? checkNames.filter((name) => state.checks[name].status !== 'disabled')
        : state.requestedChecks ?? checkNames;
      if (names.length === 0 && !state.actions) continue;
      const children: AgentStep[] = names.map((name) => {
        const result = finished ? state.checks[name].status : state.completedChecks?.[name];
        return {
          id: name, label: checks[name],
          status: result === 'unavailable' ? 'failed' : result ? 'done' : 'pending',
          note: result && statuses[result],
        };
      });
      const complete = state.status !== 'collecting' || state.completedActions?.includes('mcp');
      const failed = children.filter((step) => step.status === 'failed').length;
      steps.push({
        id: 'mcp', label: 'T-Invest MCP', children,
        status: complete ? (children.length && failed === children.length ? 'failed' : 'done')
          : active === 'mcp' ? 'running' : 'pending',
        note: failed > 0 && failed < children.length ? 'Частично' : undefined,
      });
    } else {
      const result = state.cbr?.status;
      steps.push({
        id: 'cbr', label: 'Календарь ЦБ',
        status: result === 'unavailable' ? 'failed' : result ? 'done'
          : finished ? 'skipped' : active === 'cbr' ? 'running' : 'pending',
        note: result === 'empty' ? 'Без решения по ставке'
          : result === 'ok' ? 'Решение найдено' : result && statuses[result],
      });
    }
  }

  const synthesisStatus = finished
    ? { ready: 'done', failed: 'failed', skipped: 'skipped' }[state.llm] as AgentStep['status']
    : state.status === 'analyzing' ? 'running' : 'pending';
  steps.push({
    id: 'synthesis', label: 'ИИ-разбор', status: synthesisStatus,
    note: synthesisStatus === 'skipped' ? 'Пропущено' : synthesisStatus === 'failed' ? 'Ошибка модели' : undefined,
  });
  return steps;
}

function AnalysisDetails({ state, agentName, palette }: { state: AnalysisResult } & AgentIdentity) {
  const comparison = state.checks.market.facts.comparison;
  const dividends = state.checks.dividends.facts;
  const { cbr } = state;
  const sources = [...Object.values(state.checks), ...(cbr ? [cbr] : [])];
  const materials = [...new Map(sources.flatMap(({ materials }) =>
    materials.map((item) => [item.id, item] as const))).values()];
  const recommendation = dividends.recommendation;
  const recommendationSource = materials.find((item) => item.id === dividends.materialId);
  const calendar = state.checks.reports.facts.calendar ?? [];
  const news = state.checks.news.materials[0];
  const headlines: Partial<Record<CheckName, string>> = {
    market: comparison && `Индекс Мосбиржи ${percent.format(comparison.changePercent / 100)}`,
    dividends: recommendation,
  };
  const findings: Partial<Record<CheckName, ReactNode>> = {
    news: news?.title,
    market: comparison && 'Изменение индекса за тот же час.',
    dividends: (recommendationSource || Boolean(dividends.payments?.length)) && <>
      {recommendationSource && <p>
        {recommendationSource.source ?? 'Опубликовано'} · {marketTime(recommendationSource.publishedAt)}
      </p>}
      {dividends.payments?.map((item) => <p key={item.materialId}>
        {number.format(item.amount)} {item.currency.toUpperCase()} на акцию · объявлено {item.declaredDate} · последний день покупки {item.lastBuyDate}
        {item.possibleDividendGap && <>. Размер выплаты близок к ценовому разрыву и может его объяснять.</>}
      </p>)}
    </>,
    reports: calendar.length > 0
      ? calendar.map((item) => <p key={item.createdAt}>Дата в календаре · {item.scheduledDate}</p>)
      : state.checks.reports.materials[0]?.title,
  };

  const { synthesis } = state;
  const modelSummary = synthesis?.summary ?? synthesis?.hypotheses[0]?.text ?? synthesis?.facts[0]?.text;
  const summary = modelSummary ?? (recommendation && state.checks.news.materials.some((item) => item.id === dividends.materialId)
    ? `${recommendation} Публикация в час сигнала даёт возможное объяснение движению цены.`
    : 'Доступных данных недостаточно, чтобы объяснить движение цены.');
  const evidence = synthesis?.evidenceChecks ?? [];
  const completedChecks = checkNames.filter((name) => synthesis?.summary
    ? evidence.includes(name)
    : !modelSummary && state.checks[name].status !== 'disabled');
  const citedFacts = synthesis?.facts.length ? synthesis.facts : synthesis?.hypotheses.slice(0, 1) ?? [];
  const showCbr = cbr && (!modelSummary || evidence.includes('cbr'));

  return (
    <AnalysisSummary title={modelSummary ? 'ИИ-разбор' : 'Сводка по источникам'}
      summary={summary} reason={state.reason} agentName={agentName} palette={palette}
      activity={<AgentSteps steps={activitySteps(state)} initiallyOpen={false} />}>
      {(citedFacts.length > 0 || completedChecks.length > 0 || showCbr) && <div className="event-findings">
        {citedFacts.map((fact, index) => <FindingCard key={index} title={fact.text}>
          <Citations items={fact.citations} />
        </FindingCard>)}
        {completedChecks.map((name) => {
          const { status, reason } = state.checks[name];
          const finding = findings[name];
          const explanation = (status !== 'ok' || name === 'reports') ? reason : null;
          return <FindingCard key={name} title={headlines[name] ?? checkHeadlines[name][status]}>
            {explanation && <p>{explanation}</p>}
            {finding || (!explanation && sourceExplanations[status])}
          </FindingCard>;
        })}
        {showCbr && <FindingCard title="Проверка календаря ЦБ">
          {cbr.reason ?? (cbr.materials.map((item) => item.title).join('. ') || sourceExplanations[cbr.status])}
        </FindingCard>}
      </div>}
    </AnalysisSummary>
  );
}

function FindingCard({ title, children }: {
  title: string;
  children: ReactNode;
}) {
  return <div className="event-finding-card">
    <strong>{title}</strong>
    <div className="event-finding-explanation">{children}</div>
  </div>;
}
