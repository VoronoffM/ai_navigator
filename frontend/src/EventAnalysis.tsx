import { marketTime, number } from './market';
import type { AnalysisState, CheckName, Statement } from './analysis';

const checks: Record<CheckName, string> = {
  news: 'Новости', market: 'IMOEX', dividends: 'Дивиденды', reports: 'Отчётность',
};
const statuses = { ok: 'Проверено', empty: 'Данные не найдены', unavailable: 'Источник недоступен', disabled: 'Выключено' };
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

export function EventAnalysis({ state, articleId }: { state: AnalysisState; articleId?: string }) {
  if (state.status === 'collecting' || state.status === 'analyzing') {
    return <div className="event-analysis"><h4>{state.status === 'collecting' ? 'Собираем контекст' : 'Готовим ИИ-разбор'}</h4></div>;
  }
  if (state.status === 'error') {
    return <div className="event-analysis"><h4>ИИ-разбор не выполнен</h4><p>{state.reason}</p></div>;
  }

  const partial = Object.values(state.checks).some((check) => check.status === 'unavailable');
  const title = state.llm === 'failed' ? 'ИИ-разбор не выполнен'
    : state.llm === 'ready' ? (partial ? 'Разбор готов · часть источников недоступна' : 'Разбор готов')
      : 'Контекст сигнала';
  const comparison = state.checks.market.facts.comparison;
  const dividends = state.checks.dividends.facts;
  const recommendationCited = state.synthesis?.facts.some((fact) =>
    fact.citations.some((source) => source.id === dividends.materialId));
  const materials = [...new Map(Object.values(state.checks).flatMap(({ materials }) =>
    materials.map((item) => [item.id, item] as const))).values()].filter((item) => item.id !== articleId);

  return <div className="event-analysis">
    <h4>{title}</h4>
    {state.reason && <p>{state.reason}</p>}
    {comparison && <p className="figures">IMOEX {percent.format(comparison.changePercent / 100)} за тот же час</p>}
    {dividends.recommendation && !recommendationCited && <p>{dividends.recommendation}</p>}
    {dividends.payments?.map((item) => <p key={item.materialId}>
      {number.format(item.amount)} {item.currency.toUpperCase()} на акцию · объявлено {item.declaredDate} · последний день покупки {item.lastBuyDate}
      {item.possibleDividendGap && <>. Размер выплаты близок к ценовому разрыву и может его объяснять.</>}
    </p>)}
    {state.checks.reports.facts.calendar?.map((item) =>
      <p key={item.createdAt}>Дата в календаре · {item.scheduledDate}</p>)}
    {state.checks.reports.reason && state.checks.reports.status === 'ok' && <p>{state.checks.reports.reason}</p>}
    {state.checks.news.status === 'empty' && <p>{state.checks.news.reason}</p>}
    {materials.length > 0 && <ul>{materials.map((item) => <li key={item.id}>
      {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a> : item.title}
      <small className="event-news-source"> {item.source && `${item.source} · `}{marketTime(item.publishedAt)}
        {item.headlineOnly && ' · Только заголовок'}</small>
      {item.text && <p>{item.text}</p>}
    </li>)}</ul>}
    {state.synthesis && <>
      <Statements title="Подтверждённые факты" items={state.synthesis.facts} />
      <Statements title="Возможные объяснения" items={state.synthesis.hypotheses} />
      {state.synthesis.questions.length > 0 && <div>
        <h5>Открытые вопросы</h5>
        <ul>{state.synthesis.questions.map((question, index) => <li key={index}>{question}</li>)}</ul>
      </div>}
    </>}
    <dl className="event-sources" aria-label="Статус источников">
      {(Object.keys(checks) as CheckName[]).map((name) => {
        const { status, reason } = state.checks[name];
        return <div key={name} data-status={status}>
          <dt>{checks[name]}</dt><dd>{statuses[status]}</dd>
          {reason && status !== 'ok' && !(name === 'news' && status === 'empty') &&
            <dd className="event-source-reason">{reason}</dd>}
        </div>;
      })}
    </dl>
  </div>;
}
