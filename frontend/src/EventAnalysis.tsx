import { CircleAlert } from 'lucide-react';
import { AnalysisSummary } from './AnalysisSummary';
import { AgentSteps, type AgentStep } from './AgentSteps';
import { analysisFindings, type AnalysisFinding } from './analysisFindings';
import type { AgentPalette } from './studioSettings';
import type { AnalysisResult, AnalysisState, CheckName, CheckStatus, Citation, InformationKind } from './analysis';

const checks: Record<CheckName, string> = {
  news: 'Новости', market: 'Индекс Мосбиржи', dividends: 'Дивиденды', reports: 'Отчётность',
};
const checkNames = Object.keys(checks) as CheckName[];
const statuses: Record<CheckStatus, string> = {
  ok: 'Проверено', empty: 'Нет данных', unavailable: 'Недоступно', disabled: 'Пропущено',
};
const findingLabels: Record<Exclude<InformationKind, 'unverified'>, string> = {
  fact: 'Факт', ai_analysis: 'Анализ ИИ', opinion: 'Мнение',
};

function Citations({ items }: { items: Citation[] }) {
  const attributed = items.filter((item) => item.source || item.url);
  if (attributed.length === 0) return null;

  return <span className="event-citations">{attributed.map((source) => source.url
    ? <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer"
        title={source.title}>{source.source ?? 'Источник'}</a>
    : <span key={source.id} title={source.title}>{source.source}</span>)}</span>;
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
          id: name, label: state.synthetic && name === 'market' ? 'Учебный индекс' : checks[name],
          status: result === 'unavailable' ? 'failed' : result ? 'done' : 'pending',
          note: result && statuses[result],
        };
      });
      const complete = state.status !== 'collecting' || state.completedActions?.includes('mcp');
      const failed = children.filter((step) => step.status === 'failed').length;
      steps.push({
        id: 'mcp', label: state.dataSource ?? 'T-Invest MCP', children,
        status: complete ? (children.length && failed === children.length ? 'failed' : 'done')
          : active === 'mcp' ? 'running' : 'pending',
        note: failed > 0 && failed < children.length ? 'Частично' : undefined,
      });
    } else if (action === 'source') {
      const complete = state.status !== 'collecting' || state.completedActions?.includes('source');
      const children: AgentStep[] = (state.sources ?? []).map((source, index) => ({
        id: `source-${index}`, label: source.url,
        status: source.status === 'unavailable' ? 'failed' : 'done', note: source.reason ?? statuses[source.status],
      }));
      steps.push({ id: 'source', label: 'Изучить источник', children,
        status: complete ? (children.length > 0 && children.every((child) => child.status === 'failed') ? 'failed' : 'done')
          : active === 'source' ? 'running' : 'pending' });
    } else if (action === 'cbr') {
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
  if (actions.includes('report')) steps.push({
    id: 'report', label: 'Отправка отчета',
    status: state.telegram === 'failed' || state.telegram === 'unconnected' ? 'failed'
      : state.telegram === 'pending' ? 'running' : finished ? 'done' : 'pending',
    note: state.telegram === 'sent' ? 'Telegram' : state.telegram === 'unconnected' ? 'Telegram не подключён' : undefined,
  });
  return steps;
}

function AnalysisDetails({ state, agentName, palette }: { state: AnalysisResult } & AgentIdentity) {
  const { synthesis } = state;
  const dividends = state.checks.dividends.facts;
  const recommendation = dividends.recommendation;
  const modelSummary = synthesis?.summary ?? synthesis?.hypotheses[0]?.text ?? synthesis?.facts[0]?.text;
  const firstMaterial = state.checks.news.materials[0];
  const noContext = state.checks.news.status === 'unavailable'
    ? 'Движение цены обнаружено, но новостная лента недоступна. Подтверждённую причину определить нельзя.'
    : 'Движение цены обнаружено. В сохранённых материалах подтверждённая причина не установлена; это само по себе не доказывает рыночный шум.';
  const summary = modelSummary ?? (recommendation && state.checks.news.materials.some((item) => item.id === dividends.materialId)
    ? `${recommendation} Публикация в час сигнала даёт возможное объяснение движению цены.`
    : firstMaterial ? `${firstMaterial.text ?? firstMaterial.title}${firstMaterial.kind === 'unverified' ? ' Связь с движением цены не подтверждена.' : ''}` : noContext);
  const evidence = synthesis?.evidenceChecks ?? [];
  const completedChecks = checkNames.filter((name) => synthesis?.summary
    ? evidence.includes(name)
    : !modelSummary && state.checks[name].status !== 'disabled');
  const findings = analysisFindings(state, completedChecks, !modelSummary || evidence.includes('cbr'));

  return (
    <AnalysisSummary title={modelSummary ? 'ИИ-разбор' : 'Сводка по источникам'}
      summary={summary} reason={state.reason} agentName={agentName} palette={palette}
      disclaimer={modelSummary ? 'Не индивидуальная инвестиционная рекомендация' : undefined}
      activity={<AgentSteps steps={activitySteps(state)} initiallyOpen={false} />}>
      {findings.length > 0 && <div className="event-findings">
        {findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)}
      </div>}
    </AnalysisSummary>
  );
}

function FindingCard({ finding }: { finding: AnalysisFinding }) {
  const { title, kind, paragraphs, citations } = finding;
  const label = kind === 'unverified' ? undefined : findingLabels[kind];

  return <div className="event-finding-card">
    <div className="event-finding-heading">
      <strong>{title}</strong>
      {label && <span className="event-finding-badge" data-kind={kind}>{label}</span>}
    </div>
    <div className="event-finding-explanation">
      {paragraphs?.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
      {citations && <Citations items={citations} />}
    </div>
  </div>;
}
