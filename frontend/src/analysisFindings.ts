import type { AnalysisResult, CheckName, CheckStatus, Citation, InformationKind, Material } from './analysis';
import { marketTime, number } from './market';

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

export type AnalysisFinding = {
  id: string;
  title: string;
  kind: InformationKind;
  paragraphs?: string[];
  citations?: Citation[];
};

function materialFinding(check: CheckName | 'cbr', title: string, item: Material): AnalysisFinding {
  return {
    id: `${check}:${item.id}`,
    title,
    kind: item.kind ?? 'unverified',
    paragraphs: [item.title],
    citations: [item],
  };
}

export function analysisFindings(
  state: AnalysisResult, names: CheckName[], showCbr: boolean,
): AnalysisFinding[] {
  const { synthesis, checks, cbr } = state;
  const findings: AnalysisFinding[] = [];
  for (const [index, source] of (state.sources ?? []).entries()) {
    if (source.status !== 'ok') findings.push({
      id: `source-status-${index}`, title: 'Изучение источника', kind: 'unverified',
      paragraphs: [source.reason ?? sourceExplanations[source.status]],
      citations: [{ id: `source-${index}`, title: source.url, source: source.url, url: source.url }],
    });
    else if (!synthesis) for (const item of source.materials) findings.push({
      id: item.id, title: item.title, kind: item.kind ?? 'unverified',
      paragraphs: [item.text?.slice(0, 600) ?? item.title], citations: [item],
    });
  }
  const shownTitles = new Set<string>();
  const shownMaterials = new Set<string>();

  for (const statement of [...(synthesis?.facts ?? []), ...(synthesis?.hypotheses ?? [])]) {
    if (shownTitles.has(statement.text)) continue;
    findings.push({
      id: `statement:${findings.length}`, title: statement.text,
      kind: statement.kind ?? 'unverified', citations: statement.citations,
    });
    shownTitles.add(statement.text);
    for (const item of statement.citations) {
      if (statement.text === item.title && statement.kind && statement.kind !== 'unverified') {
        shownMaterials.add(item.id);
      }
    }
  }

  for (const name of names) {
    const check = checks[name];
    const title = checkHeadlines[name][check.status];
    const initialCount = findings.length;

    if (name === 'market' && checks.market.facts.comparison) {
      const { changePercent, ticker } = checks.market.facts.comparison;
      findings.push({
        id: name, title: `${ticker === 'DEMO-INDEX' ? 'Учебный индекс' : 'Индекс Мосбиржи'} ${percent.format(changePercent / 100)}`,
        kind: 'fact', paragraphs: ['Изменение индекса за тот же час.'],
      });
    }
    if (name === 'dividends') {
      const { recommendation, materialId, payments } = checks.dividends.facts;
      const source = check.materials.find((item) => item.id === materialId);
      const newsAlreadyShown = names.includes('news') && checks.news.materials.some((item) => item.id === materialId);
      const showRecommendation = recommendation && !newsAlreadyShown && !shownMaterials.has(materialId ?? '');
      if (showRecommendation) {
        findings.push({
          id: name, title: recommendation, kind: source?.kind ?? 'unverified',
          paragraphs: source ? [`${source.source ?? 'Опубликовано'} · ${marketTime(source.publishedAt)}`] : undefined,
          citations: source?.kind === 'opinion' ? [source] : undefined,
        });
      }
      if (payments?.length) {
        findings.push({ id: `${name}:payments`, title, kind: 'fact', paragraphs: payments.map((item) =>
          `${number.format(item.amount)} ${item.currency.toUpperCase()} на акцию · объявлено ${item.declaredDate} · последний день покупки ${item.lastBuyDate}` +
          (item.possibleDividendGap ? '. Размер выплаты близок к ценовому разрыву.' : '')),
        });
      }
      if (recommendation) continue;
    }
    if (name === 'reports' && checks.reports.facts.calendar?.length) {
      const { calendar } = checks.reports.facts;
      findings.push({
        id: name, title, kind: 'fact',
        paragraphs: [...(check.reason ? [check.reason] : []), ...calendar.map((item) => `Дата в календаре · ${item.scheduledDate}`)],
      });
    }
    if ((name === 'news' || name === 'reports') && check.materials.length) {
      for (const item of check.materials) {
        if (!shownMaterials.has(item.id)) findings.push(materialFinding(name, title, item));
        shownMaterials.add(item.id);
      }
      continue;
    }
    if (findings.length === initialCount) {
      findings.push({ id: name, title, kind: 'unverified', paragraphs: [check.reason ?? sourceExplanations[check.status]] });
    }
  }

  if (showCbr && cbr) {
    const title = 'Проверка календаря ЦБ';
    for (const item of cbr.materials) {
      if (!shownMaterials.has(item.id)) findings.push(materialFinding('cbr', title, item));
    }
    if (!cbr.materials.length) {
      findings.push({ id: 'cbr', title, kind: 'unverified', paragraphs: [cbr.reason ?? sourceExplanations[cbr.status]] });
    }
  }
  return findings;
}
