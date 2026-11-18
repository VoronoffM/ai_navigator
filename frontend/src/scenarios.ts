import { allSymbols as symbols, type Ticker } from './market';
import type { CheckName } from './analysis';

export const scenarioChecks = {
  news: 'Новости',
  market: 'Свечи и индекс IMOEX',
  dividends: 'Дивиденды',
  reports: 'Отчётность',
} satisfies Record<CheckName, string>;

export const defaultScenarioChecks = Object.keys(scenarioChecks) as CheckName[];
export const scenarioActions = { mcp: 'T-Invest MCP', cbr: 'Изучить источник · ЦБ', source: 'Изучить источник', report: 'Отправка отчета' } as const;
export type ResearchSource = { kind: 'url' | 'cbr'; url: string; instructions: string };
export function workflowActions(scenario: Pick<ScenarioSettings, 'actions' | 'notification' | 'workflowVersion'>): SourceAction[] {
  const actions = scenario.actions ?? ['mcp'];
  if ('workflowVersion' in scenario && scenario.workflowVersion === 2) return actions;
  return actions.includes('report') || scenario.notification === 'none' ? actions : [...actions, 'report'];
}
export const cbrCalendarUrl = 'https://www.cbr.ru/dkp/cal_mp/';
export const reportFormats = { brief: 'Краткая сводка', detailed: 'Подробный разбор' } as const;
export type SourceAction = keyof typeof scenarioActions;
export const scenarioNotifications = {
  'in-app': 'В AI Штурман',
  telegram: 'Telegram',
  none: 'Без уведомлений',
} as const;
export const scenarioPeriods = [
  { value: '60', label: '1ч' },
  { value: '240', label: '4ч' },
  { value: '1440', label: '1д' },
] as const;

export const templates = {
  'price-z': {
    title: 'Аномальное изменение цены',
    description: 'Сравнивает движение цены с обычными колебаниями бумаги (Z-score с EWMA).',
    instructions: 'Проверь новости и динамику рынка. Отдели подтверждённые факты от возможных причин.',
  },
  'volume-spike': {
    title: 'Всплеск объёма торгов',
    description: 'Сравнивает объём с медианой за сопоставимые периоды предыдущих торговых дней.',
    instructions: 'Сопоставь всплеск объёма с изменением цены и новостями об эмитенте.',
  },
  relative: {
    title: 'Расхождение с рынком',
    description: 'Сравнивает движение бумаги и IMOEX и оценивает, насколько необычна разница.',
    instructions: 'Покажи изменения бумаги и IMOEX за один период и разницу между ними.',
  },
  price: {
    title: 'Изменение цены по фиксированному порогу',
    description: 'Резкий рост или падение котировки за выбранный период.',
    instructions: 'Проверь новости и динамику рынка. Отдели подтверждённые факты от возможных причин.',
  },
  news: {
    title: 'Анализ новостей',
    description: 'Новая публикация об эмитенте, при необходимости с фильтром по словам.',
    instructions: 'Выдели ключевые факты, укажи источник и опиши возможное влияние новости на эмитента.',
  },
  volume: {
    title: 'Необычный объём торгов',
    description: 'Объём торгов выше среднего за сопоставимый период.',
    instructions: 'Сопоставь всплеск объёма с изменением цены и новостями об эмитенте.',
  },
  volatility: {
    title: 'Изменение волатильности',
    description: 'Разница между минимумом и максимумом цены за период.',
    instructions: 'Объясни, какие события могли усилить колебания цены, и сопоставь их с динамикой рынка.',
  },
} as const;

export type Trigger = keyof typeof templates;
export const pilotTriggers = ['price-z', 'volume-spike', 'relative'] as const;

export function isPilotTrigger(trigger: Trigger) {
  return pilotTriggers.some((item) => item === trigger);
}
export type ScenarioSettings = {
  name: string;
  agentId?: string;
  assets: Ticker[];
  trigger: Trigger;
  direction: 'either' | 'up' | 'down';
  threshold: number;
  windowMinutes: number;
  keywords: string;
  depth: 'brief' | 'detailed';
  instructions: string;
  checks?: CheckName[];
  actions?: SourceAction[];
  workflowVersion?: 2;
  sources?: ResearchSource[];
  integrationIds?: string[];
  notification: keyof typeof scenarioNotifications;
};
export type Scenario = ScenarioSettings & { id: string; enabled: boolean };

export const storageKey = 'ai-navigator.scenarios.v1';
const decimal = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });

export function draftFrom(trigger: Trigger = 'price-z', fromTemplate = false): ScenarioSettings {
  const template = templates[trigger];
  return {
    name: fromTemplate ? template.title : '',
    assets: [],
    trigger,
    direction: 'either',
    threshold: trigger === 'price-z' || trigger === 'relative' ? 2.5 : 2,
    windowMinutes: 60,
    keywords: '',
    depth: 'brief',
    instructions: fromTemplate ? template.instructions : '',
    workflowVersion: 2,
    actions: ['mcp'],
    checks: defaultScenarioChecks,
    notification: 'in-app',
  };
}

export function describeTriggerCondition(scenario: ScenarioSettings) {
  if (scenario.trigger === 'news') {
    return scenario.keywords ? `Новости · ${scenario.keywords}` : 'Новости об эмитенте';
  }
  const threshold = decimal.format(scenario.threshold);
  if (scenario.trigger === 'volume-spike') return `Объём от ${threshold}× обычного`;
  if (scenario.trigger === 'price-z' || scenario.trigger === 'relative') {
    const labels = scenario.trigger === 'price-z'
      ? { either: 'Изменение цены', up: 'Рост цены', down: 'Падение цены' }
      : { either: 'Расхождение с IMOEX', up: 'Выше IMOEX', down: 'Ниже IMOEX' };
    return `${labels[scenario.direction]} · от ${threshold}σ`;
  }
  if (scenario.trigger === 'volume') return `Объём от ${threshold}× среднего`;
  if (scenario.trigger === 'volatility') return `Размах цены от ${threshold}%`;
  const direction = { either: 'Изменение цены', up: 'Рост цены', down: 'Падение цены' };
  return `${direction[scenario.direction]} от ${threshold}%`;
}

export function describeTrigger(scenario: ScenarioSettings) {
  const condition = describeTriggerCondition(scenario);
  if (scenario.trigger === 'news') return condition;
  const period = scenarioPeriods.find(({ value }) => Number(value) === scenario.windowMinutes);
  return `${condition} · ${period?.label ?? `${scenario.windowMinutes} мин`}`;
}

function isScenario(value: unknown): value is Scenario {
  if (typeof value !== 'object' || value === null) return false;
  const item = value as Partial<Scenario>;
  return typeof item.id === 'string' && typeof item.enabled === 'boolean'
    && (item.agentId === undefined || typeof item.agentId === 'string')
    && typeof item.name === 'string' && !!item.name.trim()
    && Array.isArray(item.assets) && item.assets.length > 0
    && item.assets.every((ticker) => symbols.some((symbol) => symbol.ticker === ticker))
    && typeof item.trigger === 'string' && Object.hasOwn(templates, item.trigger)
    && (item.direction === 'either' || item.direction === 'up' || item.direction === 'down')
    && typeof item.threshold === 'number' && Number.isFinite(item.threshold)
    && typeof item.windowMinutes === 'number' && Number.isInteger(item.windowMinutes)
    && typeof item.keywords === 'string' && typeof item.instructions === 'string'
    && (item.depth === 'brief' || item.depth === 'detailed')
    && (item.checks === undefined || (Array.isArray(item.checks) && item.checks.every((check) => defaultScenarioChecks.includes(check))))
    && (item.actions === undefined || (Array.isArray(item.actions) && item.actions.length > 0
      && new Set(item.actions).size === item.actions.length
      && item.actions.every((action) => Object.hasOwn(scenarioActions, action))))
    && (item.sources === undefined || (Array.isArray(item.sources) && item.sources.length <= 5
      && item.sources.every((source) => source && (source.kind === 'url' || source.kind === 'cbr')
        && typeof source.url === 'string' && typeof source.instructions === 'string')))
    && (item.integrationIds === undefined || (Array.isArray(item.integrationIds) && item.integrationIds.every((id) => typeof id === 'string')))
    && typeof item.notification === 'string' && Object.hasOwn(scenarioNotifications, item.notification);
}

export function readScenarios(): Scenario[] {
  const stored = localStorage.getItem(storageKey);
  if (stored === null) return [];
  const value: unknown = JSON.parse(stored);
  if (!Array.isArray(value) || !value.every(isScenario)) throw new Error('Invalid scenario settings');
  return value.map((scenario) => ({
    ...scenario, workflowVersion: 2,
    actions: [...new Set(workflowActions(scenario).map((action) => action === 'cbr' ? 'source' : action))],
    sources: scenario.actions?.includes('cbr') ? [...(scenario.sources ?? []), {
      kind: 'cbr', url: cbrCalendarUrl,
      instructions: 'Проверь решения по ключевой ставке в окне сигнала и их возможное влияние.',
    }] : scenario.sources,
  }));
}
