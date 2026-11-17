import { draftFrom, readScenarios, storageKey, type Scenario } from './scenarios';

export type StudioAgent = {
  id: string;
  name: string;
  provider: 'ollama' | 'cloud';
};

export type ExtraIntegration = { id: string; name: string; endpoint: string };
export type StudioSettings = { agents: StudioAgent[]; integrations: ExtraIntegration[] };
export type StudioState = { settings: StudioSettings; scenarios: Scenario[]; issues: string[] };

const agentPalettes = ['amber', 'orchid', 'peach'] as const;
export type AgentPalette = (typeof agentPalettes)[number];

export function agentPalette(index: number): AgentPalette | undefined {
  return index < 0 ? undefined : agentPalettes[index % agentPalettes.length];
}

export const studioSettingsKey = 'ai-navigator.studio.v1';

export const starterAgents: StudioAgent[] = [
  { id: 'market-watch', name: 'Рыночный радар', provider: 'ollama' },
  { id: 'news-watch', name: 'Новостной аналитик', provider: 'ollama' },
  { id: 'portfolio-watch', name: 'Портфельный наблюдатель', provider: 'ollama' },
];

export function starterScenarios(): Scenario[] {
  return [
    {
      ...draftFrom('price-z', true),
      id: 'starter-0',
      name: 'Аномальное падение цены',
      agentId: starterAgents[0].id,
      assets: ['GAZP'],
      direction: 'down',
      enabled: true,
    },
    {
      ...draftFrom('volume-spike', true),
      id: 'starter-1',
      name: 'Резкий рост объёмов',
      agentId: starterAgents[0].id,
      assets: ['GAZP'],
      enabled: false,
    },
  ];
}

export function readStudioSettings(): StudioSettings {
  const stored = localStorage.getItem(studioSettingsKey);
  if (stored === null) return { agents: starterAgents, integrations: [] };

  const value: Omit<StudioSettings, 'agents'> & {
    agents: (Omit<StudioAgent, 'provider'> & { provider: StudioAgent['provider'] | 'openai' })[];
  } = JSON.parse(stored);
  if (!Array.isArray(value?.agents) || !Array.isArray(value.integrations)
    || !value.agents.every((agent) => typeof agent?.id === 'string' && typeof agent.name === 'string'
      && (agent.provider === 'ollama' || agent.provider === 'cloud' || agent.provider === 'openai'))
    || !value.integrations.every((item) => typeof item?.id === 'string' && typeof item.name === 'string'
      && typeof item.endpoint === 'string')) throw new Error('Invalid Studio settings');
  return {
    ...value,
    agents: value.agents.map((agent) => ({ ...agent, provider: agent.provider === 'openai' ? 'cloud' : agent.provider })),
  };
}

export function readStudioScenarios() {
  return localStorage.getItem(storageKey) === null ? starterScenarios() : readScenarios();
}

export function activeStudioScenarios({ settings, scenarios }: StudioState) {
  const agentIds = new Set(settings.agents.map(({ id }) => id));
  return scenarios.filter(({ enabled, agentId }) => enabled && agentId && agentIds.has(agentId));
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
