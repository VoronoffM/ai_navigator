import { symbols } from './market';
import { draftFrom, readScenarios, storageKey, templates, type Scenario, type ScenarioSettings, type Trigger } from './scenarios';

export type StudioAgent = {
  id: string;
  name: string;
  provider: 'ollama' | 'openai';
};

export type ExtraIntegration = { id: string; name: string; endpoint: string };
export type StudioSettings = { agents: StudioAgent[]; integrations: ExtraIntegration[] };
export type StudioState = { settings: StudioSettings; scenarios: Scenario[]; issues: string[] };

export const studioSettingsKey = 'ai-navigator.studio.v1';

export const starterAgents: StudioAgent[] = [
  { id: 'market-watch', name: 'Рыночный радар', provider: 'ollama' },
  { id: 'news-watch', name: 'Новостной аналитик', provider: 'ollama' },
  { id: 'portfolio-watch', name: 'Портфельный наблюдатель', provider: 'ollama' },
];

type LibraryEntry = { title: string; description: string; trigger: Trigger; settings?: Partial<ScenarioSettings> };

export const library = [
  {
    title: 'Аномальное падение цены', description: 'Замечает резкое снижение котировок.',
    trigger: 'price', settings: { direction: 'down' },
  },
  {
    title: 'Резкий рост объёмов', description: 'Находит всплески торговой активности.',
    trigger: 'volume',
  },
  {
    title: 'Анализ рыночных новостей', description: 'Выделяет факты и оценивает их влияние.',
    trigger: 'news',
  },
  {
    title: 'Мониторинг портфеля', description: 'Отслеживает движение выбранных бумаг.',
    trigger: 'price', settings: {
      assets: symbols.map(({ ticker }) => ticker),
      instructions: 'Сопоставь движения выбранных бумаг, отметь наиболее заметные изменения и возможные причины.',
    },
  },
  {
    title: templates.volatility.title, description: 'Отмечает широкий диапазон колебаний.',
    trigger: 'volatility',
  },
  {
    title: 'Корпоративные события', description: 'Следит за отчётностью и дивидендами.',
    trigger: 'news', settings: {
      keywords: 'дивиденд, отчёт, собрание акционеров',
      instructions: 'Укажи даты, решения и условия события. Объясни, какие данные важны держателям бумаг.',
    },
  },
] satisfies LibraryEntry[];

export function templateDraft(entry: LibraryEntry): ScenarioSettings {
  return { ...draftFrom(entry.trigger, true), ...entry.settings, name: entry.title };
}

export function starterScenarios(): Scenario[] {
  return [
    { template: 0, agent: 0 },
    { template: 1, agent: 0 },
    { template: 2, agent: 1 },
    { template: 3, agent: 2 },
  ].map(({ template, agent }) => {
    const settings = templateDraft(library[template]);
    return {
      ...settings,
      id: `starter-${template}`,
      agentId: starterAgents[agent].id,
      assets: settings.assets.length ? settings.assets : ['GAZP'],
      enabled: true,
    };
  });
}

export function readStudioSettings(): StudioSettings {
  const stored = localStorage.getItem(studioSettingsKey);
  if (stored === null) return { agents: starterAgents, integrations: [] };

  const value: StudioSettings = JSON.parse(stored);
  if (!Array.isArray(value?.agents) || !Array.isArray(value.integrations)
    || !value.agents.every((agent) => typeof agent?.id === 'string' && typeof agent.name === 'string'
      && (agent.provider === 'ollama' || agent.provider === 'openai'))
    || !value.integrations.every((item) => typeof item?.id === 'string' && typeof item.name === 'string'
      && typeof item.endpoint === 'string')) throw new Error('Invalid Studio settings');
  return value;
}

export function readStudioScenarios() {
  return localStorage.getItem(storageKey) === null ? starterScenarios() : readScenarios();
}

export function loadStudio(): StudioState {
  const issues: string[] = [];
  let settings: StudioSettings = { agents: [], integrations: [] };
  let scenarios: Scenario[] = [];
  try {
    settings = readStudioSettings();
  } catch {
    issues.push('Не удалось прочитать настройки агентов и интеграций.');
  }
  try {
    scenarios = readStudioScenarios();
  } catch {
    issues.push('Не удалось прочитать сохранённые сценарии.');
  }
  return { settings, scenarios, issues };
}
