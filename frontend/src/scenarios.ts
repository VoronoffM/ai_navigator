import { symbols, type Ticker } from './market';
import type { CheckName } from './analysis';

export const scenarioChecks = {
  news: 'Новости',
  market: 'Свечи и индекс IMOEX',
  dividends: 'Дивиденды',
  reports: 'Отчётность',
} satisfies Record<CheckName, string>;

export const defaultScenarioChecks = Object.keys(scenarioChecks) as CheckName[];
export const scenarioNotifications = {
  'in-app': 'В AI Штурман',
  telegram: 'Telegram',
  none: 'Без уведомлений',
} as const;

export const templates = {
  price: {
    title: 'Аномальное изменение цены',
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
  integrationIds?: string[];
  notification: keyof typeof scenarioNotifications;
};
export type Scenario = ScenarioSettings & { id: string; enabled: boolean };

export const storageKey = 'ai-navigator.scenarios.v1';
const decimal = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });

export function draftFrom(trigger: Trigger = 'price', fromTemplate = false): ScenarioSettings {
  const template = templates[trigger];
  return {
    name: fromTemplate ? template.title : '',
    assets: [],
    trigger,
    direction: 'either',
    threshold: 2,
    windowMinutes: 60,
    keywords: '',
    depth: 'brief',
    instructions: fromTemplate ? template.instructions : '',
    checks: defaultScenarioChecks,
    notification: 'in-app',
  };
}

export function describeTrigger(scenario: ScenarioSettings) {
  if (scenario.trigger === 'news') {
    return scenario.keywords ? `Новости · ${scenario.keywords}` : 'Новости об эмитенте';
  }
  const threshold = decimal.format(scenario.threshold);
  const window = `${scenario.windowMinutes} мин`;
  if (scenario.trigger === 'volume') return `Объём от ${threshold}× среднего · ${window}`;
  if (scenario.trigger === 'volatility') return `Размах цены от ${threshold}% · ${window}`;
  const direction = { either: 'Изменение цены', up: 'Рост цены', down: 'Падение цены' };
  return `${direction[scenario.direction]} от ${threshold}% · ${window}`;
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
    && (item.integrationIds === undefined || (Array.isArray(item.integrationIds) && item.integrationIds.every((id) => typeof id === 'string')))
    && typeof item.notification === 'string' && Object.hasOwn(scenarioNotifications, item.notification);
}

export function readScenarios(): Scenario[] {
  const stored = localStorage.getItem(storageKey);
  if (stored === null) return [];
  const value: unknown = JSON.parse(stored);
  if (!Array.isArray(value) || !value.every(isScenario)) throw new Error('Invalid scenario settings');
  return value;
}
