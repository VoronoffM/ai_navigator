import { useEffect, useRef, useState, type Dispatch, type FormEvent, type MouseEvent, type ReactNode, type SetStateAction } from 'react';
import {
  Activity, ArrowRight, AudioWaveform, BriefcaseBusiness, CalendarDays,
  ChartNoAxesColumnIncreasing, ChevronRight, CodeXml, Database, Laptop, Newspaper, Plus, Send,
  Trash2, Workflow, X,
} from 'lucide-react';
import type { AnalysisConfig, Profile } from './analysis';
import { AgentCards } from './AgentCards';
import {
  defaultScenarioChecks, describeTrigger, draftFrom, scenarioChecks,
  scenarioNotifications, storageKey, type Scenario, type ScenarioSettings,
} from './scenarios';
import { ScenarioAssets, ScenarioEditor } from './ScenarioEditor';
import {
  library, readStudioScenarios, readStudioSettings, studioSettingsKey, templateDraft,
  type ExtraIntegration, type StudioAgent, type StudioSettings, type StudioState,
} from './studioSettings';
import { ExtraSettings, ProviderSettings, TelegramSettings } from './StudioIntegrations';
import { WeightWave } from './WeightWave';

const studioTitle = 'Создай своего AI-ассистента';
const libraryVisuals = [
  { Icon: Activity, tone: 'peach' },
  { Icon: ChartNoAxesColumnIncreasing, tone: 'amber' },
  { Icon: Newspaper, tone: 'orchid' },
  { Icon: BriefcaseBusiness, tone: 'blue' },
  { Icon: AudioWaveform, tone: 'orchid' },
  { Icon: CalendarDays, tone: 'mint' },
];
type Overlay =
  | { kind: 'agent'; id?: string }
  | { kind: 'template'; index: number }
  | { kind: 'scenario-create' }
  | { kind: 'scenario-details'; id: string }
  | { kind: 'provider'; provider: 'openai' | 'ollama' }
  | { kind: 'telegram' }
  | { kind: 'invest-mcp' }
  | { kind: 'extra'; id?: string };

type Props = {
  visible: boolean;
  studio: StudioState;
  setStudio: Dispatch<SetStateAction<StudioState>>;
  analysisConfig?: AnalysisConfig;
  analysisConfigFailed: boolean;
  profile: Profile;
  onProfileChange: (profile: Profile) => void;
  openaiKey: string;
  onOpenaiKeyChange: (key: string) => void;
};

export function AgentStudio(props: Props) {
  const { visible, studio, setStudio, analysisConfig, analysisConfigFailed, profile, openaiKey } = props;
  const [overlay, setOverlay] = useState<Overlay>();
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [telegramChat, setTelegramChat] = useState('');
  const opener = useRef<HTMLElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const { agents, integrations } = studio.settings;
  // A scenario remains reusable when its assigned agent is removed from the catalog.
  const agentIds = new Set(agents.map((agent) => agent.id));
  const scenarios = studio.scenarios.map((item) =>
    item.agentId && !agentIds.has(item.agentId) ? { ...item, agentId: undefined } : item);
  const apiConfigured = Boolean(analysisConfig?.openaiModel && openaiKey.trim());

  function open(next: Overlay, event: MouseEvent<HTMLButtonElement>) {
    opener.current = event.currentTarget;
    setFeedback('');
    setError('');
    setOverlay(next);
  }

  function close() {
    setOverlay(undefined);
    setError('');
    requestAnimationFrame(() => (opener.current?.isConnected ? opener.current : title.current)?.focus());
  }

  function persistSettings(update: (settings: StudioSettings) => StudioSettings) {
    try {
      const settings = update(readStudioSettings());
      localStorage.setItem(studioSettingsKey, JSON.stringify(settings));
      setStudio((current) => ({ ...current, settings }));
      return true;
    } catch {
      setError('Не удалось сохранить настройки в браузере.');
      return false;
    }
  }

  function persistScenarios(update: (items: Scenario[]) => Scenario[]) {
    try {
      const items = update(readStudioScenarios());
      localStorage.setItem(storageKey, JSON.stringify(items));
      setStudio((current) => ({ ...current, scenarios: items }));
      setError('');
      return true;
    } catch {
      setError('Не удалось сохранить сценарий в браузере.');
      return false;
    }
  }

  function toggleScenario(item: Scenario) {
    persistScenarios((items) => items.map((scenario) =>
      scenario.id === item.id ? { ...scenario, enabled: !scenario.enabled } : scenario));
  }

  function saveScenario(settings: ScenarioSettings) {
    const scenario = { ...settings, id: crypto.randomUUID(), enabled: Boolean(settings.agentId) };
    const saved = persistScenarios((items) => [...items, scenario]);
    if (saved) {
      const agent = agents.find((item) => item.id === settings.agentId);
      setFeedback(agent ? `Сценарий «${settings.name}» сохранён у агента «${agent.name}».` : `Сценарий «${settings.name}» сохранён.`);
      close();
    }
  }

  function deleteScenario(scenario: Scenario) {
    if (persistScenarios((items) => items.filter((item) => item.id !== scenario.id))) {
      setFeedback(`Сценарий «${scenario.name}» удалён.`);
      close();
    }
  }

  function saveAgent(agent: StudioAgent, editing: boolean) {
    const saved = persistSettings((settings) => ({
      ...settings,
      agents: editing ? settings.agents.map((item) => item.id === agent.id ? agent : item) : [...settings.agents, agent],
    }));
    if (saved) {
      setFeedback(editing ? 'Настройки агента сохранены.' : `Агент «${agent.name}» добавлен.`);
      close();
    }
  }

  function deleteAgent(agent: StudioAgent) {
    const saved = persistSettings((settings) => ({
      ...settings,
      agents: settings.agents.filter((item) => item.id !== agent.id),
    }));
    if (saved) {
      setFeedback(`Агент «${agent.name}» удалён.`);
      close();
    }
  }

  function saveIntegration(integration: ExtraIntegration, editing: boolean) {
    const saved = persistSettings((settings) => ({
      ...settings,
      integrations: editing ? settings.integrations.map((item) => item.id === integration.id ? integration : item)
        : [...settings.integrations, integration],
    }));
    if (saved) {
      setFeedback('Настройки интеграции сохранены.');
      close();
    }
  }

  const configStatus = analysisConfigFailed ? 'Сервер недоступен' : 'Загрузка настроек';
  const apiSelected = apiConfigured && profile.provider === 'openai';
  const localSelected = Boolean(analysisConfig && profile.provider === 'ollama');
  const apiStatus = !analysisConfig ? configStatus : !analysisConfig.openaiModel ? 'Недоступно на сервере'
    : !apiConfigured ? 'Нужен API-ключ' : apiSelected ? 'Выбрано' : 'Ключ добавлен';
  const savedScenarios = scenarios.filter((scenario) => !scenario.agentId || !scenario.id.startsWith('starter-'));
  let modalTitle = '';
  let modalContent: ReactNode = null;
  if (overlay?.kind === 'agent') {
    const agent = agents.find((item) => item.id === overlay.id);
    const channels = agent ? [
      agent.provider === 'openai' && apiConfigured ? 'API' : '',
      agent.provider === 'ollama' && analysisConfig ? 'Локально' : '',
    ].filter(Boolean) : [];
    modalTitle = agent ? 'Настройки агента' : 'Новый агент';
    modalContent = <AgentSettings agent={agent} channels={channels}
      scenarios={scenarios.filter((item) => agent && item.agentId === agent.id)}
      onSave={saveAgent} onCancel={close} onDelete={deleteAgent}
      onOpenScenario={(item) => setOverlay({ kind: 'scenario-details', id: item.id })}
      onToggleScenario={toggleScenario} />;
  } else if (overlay?.kind === 'template') {
    const entry = library[overlay.index];
    modalTitle = entry.title;
    modalContent = <TemplateScenario initial={templateDraft(entry)} description={entry.description} agents={agents}
      onSave={saveScenario} onCancel={close} />;
  } else if (overlay?.kind === 'scenario-create') {
    modalTitle = 'Новый сценарий';
    modalContent = <ScenarioEditor initial={draftFrom()} agents={agents} integrations={integrations}
      onSave={saveScenario} onCancel={close} />;
  } else if (overlay?.kind === 'scenario-details') {
    const scenario = scenarios.find((item) => item.id === overlay.id);
    modalTitle = scenario?.name ?? 'Сценарий';
    modalContent = scenario ? (
      <ScenarioDetails scenario={scenario} agent={agents.find((item) => item.id === scenario.agentId)}
        integrations={integrations} onDelete={() => deleteScenario(scenario)} />
    ) : <p className="studio-dialog-copy">Сценарий удалён.</p>;
  } else if (overlay?.kind === 'provider') {
    modalTitle = overlay.provider === 'openai' ? 'API · OpenAI' : 'Локальное выполнение';
    modalContent = <ProviderSettings config={analysisConfig} failed={analysisConfigFailed} provider={overlay.provider}
      profile={profile} apiKey={openaiKey} onProfileChange={props.onProfileChange}
      onKeyChange={props.onOpenaiKeyChange} onClose={close} />;
  } else if (overlay?.kind === 'telegram') {
    modalTitle = 'Подключение Telegram';
    modalContent = <TelegramSettings connectedChat={telegramChat} onConnect={setTelegramChat} />;
  } else if (overlay?.kind === 'invest-mcp') {
    modalTitle = 'T-Invest MCP';
    modalContent = <p className="studio-dialog-copy">Исторический разбор использует сохранённые из T-Invest MCP свечи «Газпрома» и индекса Мосбиржи.</p>;
  } else if (overlay?.kind === 'extra') {
    const integration = integrations.find((item) => item.id === overlay.id);
    modalTitle = integration ? 'Настройки интеграции' : 'Новая интеграция';
    modalContent = <ExtraSettings integration={integration} onSave={saveIntegration} onCancel={close}
      onRemove={() => {
        if (persistSettings((settings) => ({ ...settings, integrations: settings.integrations.filter((item) => item.id !== overlay.id) }))) {
          setFeedback('Интеграция удалена.');
          close();
        }
      }} />;
  }

  return (
    <main className="studio" hidden={!visible} aria-labelledby="studio-title">
      <header className="studio-header">
        <h1 id="studio-title" ref={title} tabIndex={-1} aria-label={studioTitle}>
          <WeightWave text={studioTitle} active={visible} />
        </h1>
      </header>

      <AgentCards
        cards={agents.map(({ id, name }) => ({
          id, name,
          activeScenarioCount: scenarios.filter((item) => item.agentId === id && item.enabled).length,
        }))}
        onOpen={(id, event) => open({ kind: 'agent', id }, event)}
        onAdd={(event) => open({ kind: 'agent' }, event)} />
      {!overlay && error && <p className="studio-error" role="alert">{error}</p>}
      {studio.issues.map((issue) => <p className="studio-error" role="alert" key={issue}>{issue}</p>)}
      <p className="studio-feedback" role="status">{feedback}</p>

      <div className="studio-layout">
        <section className="studio-library" aria-labelledby="library-title">
          <div className="studio-section-header">
            <h2 id="library-title">Библиотека сценариев</h2>
            <button className="studio-create" type="button" aria-haspopup="dialog"
              onClick={(event) => open({ kind: 'scenario-create' }, event)}>
              <Workflow size={18} aria-hidden="true" /> Создать свой workflow
            </button>
          </div>
          <div className="studio-templates">
            {library.map((entry, index) => {
              const { Icon, tone } = libraryVisuals[index];
              return (
                <button className="studio-template" data-tone={tone} type="button" key={entry.title} aria-haspopup="dialog"
                  onClick={(event) => open({ kind: 'template', index }, event)}>
                  <span className="studio-template-top">
                    <span className="studio-icon"><Icon size={23} strokeWidth={1.7} aria-hidden="true" /></span>
                    <ArrowRight size={17} aria-hidden="true" />
                  </span>
                  <span className="studio-template-copy">
                    <strong className="studio-card-title">{entry.title}</strong>
                    <span>{entry.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {savedScenarios.length > 0 && (
            <details className="studio-saved">
              <summary>Сохранённые сценарии ({savedScenarios.length})</summary>
              <div className="studio-list">
                {savedScenarios.map((item) => (
                  <div className="studio-saved-row" key={item.id}>
                    <button className="studio-row" type="button" aria-haspopup="dialog"
                      onClick={(event) => open({ kind: 'scenario-details', id: item.id }, event)}>
                      <span><strong className="studio-card-title">{item.name}</strong><span>{agents.find((agent) => agent.id === item.agentId)?.name ?? 'Без агента'}</span></span>
                      <ChevronRight size={19} aria-hidden="true" />
                    </button>
                    <ScenarioSwitch scenario={item} onToggle={toggleScenario} />
                  </div>
                ))}
              </div>
            </details>
          )}
        </section>

        <section className="studio-connections" aria-labelledby="connections-title">
          <div className="studio-section-header">
            <h2 id="connections-title">Интеграции</h2>
          </div>
          <ul className="studio-connection-list" role="list">
            <Connection icon={Database} title="T-Invest MCP" description="Исторические данные"
              onClick={(event) => open({ kind: 'invest-mcp' }, event)} />
            <Connection icon={CodeXml} title="OpenAI API" description="Разбор данных" label={apiStatus} selected={apiSelected}
              onClick={(event) => open({ kind: 'provider', provider: 'openai' }, event)} />
            <Connection icon={Laptop} title="Локальное выполнение"
              description={localSelected ? 'Разбор данных' : undefined}
              label={localSelected ? 'Выбрано' : analysisConfig ? 'Настроить' : configStatus}
              selected={localSelected} action={Boolean(analysisConfig && !localSelected)}
              onClick={(event) => open({ kind: 'provider', provider: 'ollama' }, event)} />
            <Connection icon={Send} title="Telegram" description={telegramChat ? undefined : 'Не подключён'}
              label={telegramChat ? 'Проверено в этой сессии' : 'Подключить'} action={!telegramChat}
              onClick={(event) => open({ kind: 'telegram' }, event)} />
            {integrations.map((item) => (
              <Connection key={item.id} icon={CodeXml} title={item.name} label="Черновик"
                onClick={(event) => open({ kind: 'extra', id: item.id }, event)} />
            ))}
          </ul>
          <button className="studio-add-integration" type="button" aria-haspopup="dialog"
            onClick={(event) => open({ kind: 'extra' }, event)}>
            <Plus size={17} aria-hidden="true" /> Добавить интеграцию
          </button>
        </section>
      </div>

      {visible && overlay && (
        <StudioDialog title={modalTitle} onClose={close}>
          <div key={overlay.kind}>{modalContent}</div>
          {error && <p className="studio-error" role="alert">{error}</p>}
        </StudioDialog>
      )}
    </main>
  );
}

function Connection({ icon: Icon, title, description, label, selected, action, onClick }: {
  icon: typeof CodeXml;
  title: string;
  description?: string;
  label?: string;
  selected?: boolean;
  action?: boolean;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <li>
      <button className="studio-connection" type="button" aria-haspopup="dialog" onClick={onClick}>
        <Icon size={19} aria-hidden="true" />
        <span className="studio-connection-copy">
          <strong>{title}</strong>
          {description && <span>{description}</span>}
        </span>
        <span className="studio-connection-end" data-labeled={Boolean(label)}>
          {label && <span data-selected={selected} data-action={action}>{label}</span>}
          {!action && <ChevronRight size={16} aria-hidden="true" />}
        </span>
      </button>
    </li>
  );
}

function StudioDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  useEffect(() => {
    heading.current?.focus();
    if (dialog.current) dialog.current.scrollTop = 0;
  }, [title]);

  return (
    <dialog ref={dialog} className="studio-dialog" aria-labelledby="studio-dialog-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}>
      <header>
        <h2 id="studio-dialog-title" tabIndex={-1} ref={heading}>{title}</h2>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} aria-hidden="true" /></button>
      </header>
      {children}
    </dialog>
  );
}

function TemplateScenario({ initial, description, agents, onSave, onCancel }: {
  initial: ScenarioSettings;
  description: string;
  agents: StudioAgent[];
  onSave: (settings: ScenarioSettings) => void;
  onCancel: () => void;
}) {
  const [assets, setAssets] = useState(initial.assets);
  const [error, setError] = useState('');

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (assets.length === 0) {
      setError('Выберите хотя бы один актив.');
      return;
    }
    const agentId = String(new FormData(event.currentTarget).get('agent') ?? '');
    onSave({ ...initial, assets, agentId: agentId || undefined });
  }

  return (
    <form className="studio-form studio-template-form" onSubmit={save}>
      <p>{description}</p>
      <p>{describeTrigger(initial)}</p>
      <ScenarioAssets assets={assets} onChange={(selected) => { setAssets(selected); setError(''); }} />
      <label className="studio-field">Назначить агенту
        <select name="agent" defaultValue="">
          <option value="">Выбрать позже</option>
          {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
        </select>
      </label>
      {error && <p className="studio-error" role="alert">{error}</p>}
      <div className="studio-actions">
        <button className="button button-stop" type="button" onClick={onCancel}>Отмена</button>
        <button className="button button-primary" type="submit">Сохранить сценарий</button>
      </div>
    </form>
  );
}

function ScenarioDetails({ scenario, agent, integrations, onDelete }: {
  scenario: Scenario;
  agent?: StudioAgent;
  integrations: ExtraIntegration[];
  onDelete: () => void;
}) {
  const checks = (scenario.checks ?? defaultScenarioChecks).map((check) => scenarioChecks[check]);
  const sources = scenario.integrationIds?.map((id) =>
    integrations.find((item) => item.id === id)?.name ?? 'Удалённая интеграция') ?? [];

  return (
    <>
      <dl className="studio-scenario-details">
        <dt>Активы</dt><dd>{scenario.assets.join(', ')}</dd>
        <dt>Сигнал</dt><dd>{describeTrigger(scenario)}</dd>
        <dt>T-Invest MCP</dt><dd>{checks.join(', ') || 'Инструменты не выбраны'}</dd>
        {sources.length > 0 && <><dt>Другие интеграции</dt><dd>{sources.join(', ')}</dd></>}
        <dt>Разбор</dt><dd>{scenario.depth === 'brief' ? 'Краткая сводка' : 'Подробный разбор'}</dd>
        {scenario.instructions && <><dt>Инструкции для AI</dt><dd>{scenario.instructions}</dd></>}
        <dt>Агент</dt><dd>{agent?.name ?? 'Без агента'}</dd>
        <dt>Уведомления</dt><dd>{scenarioNotifications[scenario.notification]}</dd>
        <dt>Статус</dt><dd>{scenario.enabled ? 'Включён' : 'Выключен'}</dd>
      </dl>
      <div className="studio-actions studio-scenario-actions">
        <button className="button button-stop studio-delete-button" type="button" onClick={onDelete}>
          <Trash2 size={18} aria-hidden="true" /> Удалить сценарий
        </button>
      </div>
    </>
  );
}

function AgentSettings({ agent, channels, scenarios, onSave, onCancel, onDelete, onOpenScenario, onToggleScenario }: {
  agent?: StudioAgent;
  channels: string[];
  scenarios: Scenario[];
  onSave: (agent: StudioAgent, editing: boolean) => void;
  onDelete: (agent: StudioAgent) => void;
  onCancel: () => void;
  onOpenScenario: (scenario: Scenario) => void;
  onToggleScenario: (scenario: Scenario) => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteControl = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirmDelete) deleteControl.current?.focus();
  }, [confirmDelete]);

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSave({
      id: agent?.id ?? crypto.randomUUID(),
      name: String(data.get('name')).trim(),
      provider: data.get('provider') === 'openai' ? 'openai' : 'ollama',
    }, Boolean(agent));
  }

  return (
    <>
      <form className="studio-form" onSubmit={save}>
        <label className="studio-field">Название
          <input name="name" defaultValue={agent?.name} required pattern=".*\S.*" maxLength={60} placeholder="Например, Рыночный радар" />
        </label>
        <label className="studio-field">Где выполнять анализ
          <select name="provider" defaultValue={agent?.provider ?? 'ollama'}><option value="ollama">Локально</option><option value="openai">Через API</option></select>
        </label>
        {agent && <p>{channels.length ? `Каналы · ${channels.join(' · ')}` : 'Каналы не настроены'}</p>}
        <div className="studio-actions">
          <button className="button button-stop" type="button" onClick={onCancel}>Отмена</button>
          <button className="button button-primary" type="submit">{agent ? 'Сохранить настройки' : 'Создать агента'}</button>
        </div>
      </form>
      {agent && (
        <section className="studio-agent-delete" aria-label="Удаление агента">
          <button ref={deleteControl} className="button button-stop studio-delete-button" type="button"
            aria-expanded={confirmDelete} aria-controls="studio-delete-agent"
            onClick={() => setConfirmDelete((current) => !current)}>
            {confirmDelete ? 'Отменить удаление' : <><Trash2 size={18} aria-hidden="true" /> Удалить агента</>}
          </button>
          <div id="studio-delete-agent" hidden={!confirmDelete}>
            <p>Удалить агента «{agent.name}»? Его сценарии останутся в списке сохранённых.</p>
            <button className="button button-stop studio-delete-button" type="button" onClick={() => onDelete(agent)}>
              Подтвердить удаление
            </button>
          </div>
        </section>
      )}
      {agent && (
        <section className="studio-agent-settings">
          <h3>Сценарии агента</h3>
          {scenarios.length === 0 && <p>Выберите шаблон или свой workflow в библиотеке и назначьте его этому агенту.</p>}
          {scenarios.map((item) => (
            <div className="studio-assigned-row" key={item.id}>
              <button className="studio-text-button" type="button" onClick={() => onOpenScenario(item)}>
                <strong>{item.name}</strong><span>{describeTrigger(item)}</span>
              </button>
              <ScenarioSwitch scenario={item} onToggle={onToggleScenario} />
            </div>
          ))}
        </section>
      )}
    </>
  );
}

function ScenarioSwitch({ scenario, onToggle }: { scenario: Scenario; onToggle: (item: Scenario) => void }) {
  return (
    <button className="studio-switch" type="button" role="switch" aria-checked={scenario.enabled}
      aria-label={`Сценарий «${scenario.name}»`} onClick={() => onToggle(scenario)}>
      {scenario.enabled ? 'Включён' : 'Выключен'}
    </button>
  );
}
