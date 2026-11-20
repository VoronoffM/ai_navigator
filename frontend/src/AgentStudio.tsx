import { useEffect, useMemo, useRef, useState, type Dispatch, type FormEvent, type MouseEvent, type ReactNode, type SetStateAction } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import {
  Activity, ArrowRight, AudioWaveform, ChartNoAxesColumnIncreasing, ChevronDown, CodeXml,
  Database, Laptop, Mail, Pencil, Plus, Send, Trash2, Workflow, X,
} from 'lucide-react';
import type { AnalysisConfig, Profile } from './analysis';
import { AgentCards } from './AgentCards';
import { allSymbols } from './market';
import {
  defaultScenarioChecks, describeTrigger, draftFrom, pilotTriggers, scenarioActions, scenarioChecks,
  scenarioNotifications, storageKey, templates, workflowActions, type Scenario, type ScenarioSettings,
} from './scenarios';
import { ScenarioAssets } from './ScenarioAssets';
import { AgentScenarioPicker } from './AgentScenarioPicker';
import { ScenarioEditor } from './ScenarioEditor';
import {
  activeStudioScenarios, readStudioScenarios, readStudioSettings, studioSettingsKey,
  type ExtraIntegration, type StudioAgent, type StudioSettings, type StudioState,
} from './studioSettings';
import { ExtraSettings, InvestMcpDetails, ProviderSettings, TelegramSettings, MailSettings, type MailConfig } from './StudioIntegrations';
import { SpringDropdown } from './SpringDropdown';
import { WeightWave } from './WeightWave';
import { SourceInfo } from './SourceInfo';

const notificationOptions = (Object.keys(scenarioNotifications) as ScenarioSettings['notification'][])
  .map((value) => ({ value, label: scenarioNotifications[value] }));

const studioTitle = 'Создай своего AI-ассистента';
const scenarioPreviewCount = 2;
const scenarioPlural = new Intl.PluralRules('ru');
function scenarioCountLabel(count: number) {
  const form = scenarioPlural.select(count);
  return `${count} ${form === 'one' ? 'сценарий' : form === 'few' ? 'сценария' : 'сценариев'}`;
}
type PilotTrigger = (typeof pilotTriggers)[number];
const libraryVisuals = {
  'price-z': { Icon: Activity, tone: 'peach' },
  'volume-spike': { Icon: ChartNoAxesColumnIncreasing, tone: 'amber' },
  relative: { Icon: AudioWaveform, tone: 'orchid' },
};
type Overlay =
  | { kind: 'agent'; id?: string }
  | { kind: 'template'; trigger: PilotTrigger }
  | { kind: 'scenario-create' }
  | { kind: 'scenario-edit'; id: string }
  | { kind: 'scenario-details'; id: string }
  | { kind: 'provider'; provider: 'cloud' | 'ollama' }
  | { kind: 'telegram' }
  | { kind: 'mail' }
  | { kind: 'invest-mcp' }
  | { kind: 'extra'; id?: string };

type Props = {
  visible: boolean;
  activeScenariosOnly: boolean;
  onActiveScenariosOnlyChange: (activeOnly: boolean) => void;
  studio: StudioState;
  setStudio: Dispatch<SetStateAction<StudioState>>;
  analysisConfig?: AnalysisConfig;
  analysisConfigFailed: boolean;
  profile: Profile;
  onProfileChange: (profile: Profile) => void;
  apiKey: string;
  onApiKeyChange: (key: string) => void;
};

export function AgentStudio(props: Props) {
  const { visible, studio, setStudio, activeScenariosOnly, onActiveScenariosOnlyChange,
    analysisConfig, analysisConfigFailed, profile, apiKey } = props;
  const [overlay, setOverlay] = useState<Overlay>();
  const [error, setError] = useState('');
  const [scenariosExpanded, setScenariosExpanded] = useState(false);
  const reducedMotion = useReducedMotion();
  const [mailConfig, setMailConfig] = useState<MailConfig | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void fetch('/api/studio/mail', { cache: 'no-store', signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((connection) => { if (!controller.signal.aborted) setMailConfig(connection?.settings ?? null); })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  const [telegramChat, setTelegramChat] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    void fetch('/api/studio/telegram', { cache: 'no-store', signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((connection) => {
        if (!controller.signal.aborted && typeof connection?.chat_id === 'string') setTelegramChat(connection.chat_id);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  const opener = useRef<HTMLElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const scenariosTitle = useRef<HTMLHeadingElement>(null);
  const activeFilter = useRef<HTMLInputElement>(null);
  const { agents, integrations } = studio.settings;
  // A scenario remains reusable when its assigned agent is removed from the catalog.
  const agentIds = new Set(agents.map((agent) => agent.id));
  const scenarios = studio.scenarios.map((item) =>
    item.agentId && !agentIds.has(item.agentId) ? { ...item, agentId: undefined } : item);
  const activeScenarios = activeStudioScenarios(studio);
  const listedScenarios = activeScenariosOnly ? activeScenarios : scenarios;
  const hiddenScenarioCount = Math.max(0, listedScenarios.length - scenarioPreviewCount);
  const agentOptions = useMemo(() => [
    { value: '', label: 'Без агента' },
    ...agents.map(({ id, name }) => ({ value: id, label: name })),
  ], [agents]);
  const apiConfigured = Boolean(analysisConfig?.cloud && apiKey.trim());

  function open(next: Overlay, event: MouseEvent<HTMLButtonElement>) {
    opener.current = event.currentTarget;
    setError('');
    setOverlay(next);
  }

  function close() {
    setOverlay(undefined);
    setError('');
    requestAnimationFrame(() => (
      opener.current?.isConnected ? opener.current : activeScenariosOnly ? scenariosTitle.current : title.current
    )?.focus());
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
    return persistScenarios((items) => items.map((scenario) =>
      scenario.id === item.id && item.agentId && scenario.agentId === item.agentId
        ? { ...scenario, enabled: !item.enabled }
        : scenario));
  }

  function detachScenario(item: Scenario) {
    return persistScenarios((items) => items.map((scenario) =>
      scenario.id === item.id && scenario.agentId === item.agentId
        ? { ...scenario, agentId: undefined, enabled: false }
        : scenario));
  }

  function assignScenario(item: Scenario, agentId: string) {
    if (!agentId) return detachScenario(item);
    return persistScenarios((items) => items.map((scenario) =>
      scenario.id === item.id ? { ...scenario, agentId, enabled: Boolean(item.agentId) && scenario.enabled } : scenario));
  }

  function saveScenario(settings: ScenarioSettings) {
    const scenario = { ...settings, id: crypto.randomUUID(), enabled: Boolean(settings.agentId) };
    if (persistScenarios((items) => [...items, scenario])) {
      close();
    }
  }

  function deleteScenario(scenario: Scenario) {
    if (persistScenarios((items) => items.filter((item) => item.id !== scenario.id))) {
      close();
    }
  }

  function saveAgent(agent: StudioAgent, editing: boolean, scenarioIds: string[], enabledIds: string[]) {
    try {
      const previousSettings = localStorage.getItem(studioSettingsKey);
      const settings = readStudioSettings();
      const items = readStudioScenarios();
      if (scenarioIds.some((id) => !items.some((item) => item.id === id))) {
        setError('Один из выбранных сценариев больше недоступен. Откройте форму заново.');
        return;
      }
      const nextSettings = { ...settings, agents: editing
        ? settings.agents.map((item) => item.id === agent.id ? agent : item)
        : [...settings.agents, agent] };
      const nextScenarios = items.map((item) => scenarioIds.includes(item.id)
        ? { ...item, agentId: agent.id, enabled: enabledIds.includes(item.id) }
        : item.agentId === agent.id ? { ...item, agentId: undefined, enabled: false } : item);
      localStorage.setItem(studioSettingsKey, JSON.stringify(nextSettings));
      try {
        localStorage.setItem(storageKey, JSON.stringify(nextScenarios));
      } catch (cause) {
        if (previousSettings === null) localStorage.removeItem(studioSettingsKey);
        else localStorage.setItem(studioSettingsKey, previousSettings);
        throw cause;
      }
      setStudio((current) => ({ ...current, settings: nextSettings, scenarios: nextScenarios }));
      close();
    } catch {
      setError('Не удалось сохранить агента со сценариями в браузере. Попробуйте ещё раз.');
    }
  }

  function deleteAgent(agent: StudioAgent) {
    const saved = persistSettings((settings) => ({
      ...settings,
      agents: settings.agents.filter((item) => item.id !== agent.id),
    }));
    if (saved) {
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
      close();
    }
  }

  const scenarioRows = listedScenarios.map((item) => {
    const agent = agents.find(({ id }) => id === item.agentId);
    const status = agent ? `${agent.name} · ${item.enabled ? 'Включён' : 'На паузе'}` : 'Без агента';
    return (
      <div className="studio-saved-row" key={item.id}>
        <button className="studio-row" type="button" aria-haspopup="dialog"
          aria-label={`Изменить сценарий «${item.name}»`}
          onClick={(event) => open({ kind: 'scenario-edit', id: item.id }, event)}>
          <strong className="studio-item-title" title={item.name}>{item.name}</strong>
          <span className="studio-item-meta" title={status}>{status}</span>
          <span className="studio-saved-edit" aria-hidden="true">
            <Pencil size={16} strokeWidth={1.7} />
            <span>Изменить</span>
          </span>
        </button>
        {agent && <ScenarioSwitch scenario={item} onToggle={() => {
          if (toggleScenario(item) && activeScenariosOnly) activeFilter.current?.focus();
        }} />}
      </div>
    );
  });

  let modalTitle = '';
  let modalInfo: string | undefined;
  let modalContent: ReactNode = null;
  if (overlay?.kind === 'agent') {
    const agent = agents.find((item) => item.id === overlay.id);
    modalTitle = agent ? 'Настройки агента' : 'Новый агент';
    modalContent = <AgentSettings agent={agent} error={error} onClearError={() => setError('')}
      scenarios={scenarios.filter((item) => agent && item.agentId === agent.id)}
      availableScenarios={scenarios}
      onSave={saveAgent} onCancel={close} onDelete={deleteAgent} />;
  } else if (overlay?.kind === 'template') {
    const entry = templates[overlay.trigger];
    const initial: ScenarioSettings = { ...draftFrom(overlay.trigger, true), actions: ['mcp'] };
    modalTitle = entry.title;
    modalInfo = `${entry.description} ${describeTrigger(initial)}`;
    modalContent = <TemplateScenario initial={initial} agents={agents}
      telegramConnected={Boolean(telegramChat)} mailConnected={Boolean(mailConfig)} onSave={saveScenario} onCancel={close} />;
  } else if (overlay?.kind === 'scenario-create' || overlay?.kind === 'scenario-edit') {
    const editingId = overlay.kind === 'scenario-edit' ? overlay.id : undefined;
    const existing = scenarios.find((item) => item.id === editingId);
    modalTitle = existing ? 'Редактирование сценария' : 'Новый сценарий';
    modalContent = <ScenarioEditor key={editingId} initial={existing ?? draftFrom()} agents={agents} isNew={!existing} mailConnected={Boolean(mailConfig)} telegramConnected={Boolean(telegramChat)}
      onSaveIntegration={(integration) => persistSettings((settings) => ({
        ...settings, integrations: [...settings.integrations, integration],
      }))}
      onSave={(settings) => {
        if (!existing) saveScenario(settings);
        else if (persistScenarios((items) => items.map((item) => item.id === existing.id
          ? { ...item, ...settings, enabled: Boolean(existing.agentId) && item.enabled } : item))) {
          close();
        }
      }} onCancel={close} />;
  } else if (overlay?.kind === 'scenario-details') {
    const scenario = scenarios.find((item) => item.id === overlay.id);
    modalTitle = scenario?.name ?? 'Сценарий';
    modalContent = scenario ? (
      <ScenarioDetails scenario={scenario} agentOptions={agentOptions}
        onAgentChange={(agentId) => assignScenario(scenario, agentId)}
        onNotificationChange={(notification) => persistScenarios((items) => items.map((item) => {
          if (item.id !== scenario.id) return item;
          const actions = workflowActions(item);
          return { ...item, notification, workflowVersion: 2,
            actions: notification === 'none' ? actions.filter((action) => action !== 'report')
              : actions.includes('report') ? actions : [...actions, 'report'] };
        }))}
        integrations={integrations} onDelete={() => deleteScenario(scenario)}
        onEdit={() => setOverlay({ kind: 'scenario-edit', id: scenario.id })} />
    ) : <p className="studio-dialog-copy">Сценарий недоступен.</p>;
  } else if (overlay?.kind === 'provider') {
    modalTitle = overlay.provider === 'cloud' ? 'LLM API' : 'Локальное выполнение';
    modalContent = <ProviderSettings config={analysisConfig} failed={analysisConfigFailed} provider={overlay.provider}
      profile={profile} apiKey={apiKey} onProfileChange={props.onProfileChange}
      onKeyChange={props.onApiKeyChange} onClose={close} />;
  } else if (overlay?.kind === 'mail') {
    modalTitle = 'Подключение почты';
    modalContent = <MailSettings connected={mailConfig} onConnect={setMailConfig} />;
  } else if (overlay?.kind === 'telegram') {
    modalTitle = 'Подключение Telegram';
    modalContent = <TelegramSettings connectedChat={telegramChat} onConnect={setTelegramChat} />;
  } else if (overlay?.kind === 'invest-mcp') {
    modalTitle = 'T-Invest MCP';
    modalContent = <InvestMcpDetails />;
  } else if (overlay?.kind === 'extra') {
    const integration = integrations.find((item) => item.id === overlay.id);
    modalTitle = integration ? 'Настройки интеграции' : 'Новая интеграция';
    modalContent = <ExtraSettings integration={integration} onSave={saveIntegration} onCancel={close}
      onRemove={() => {
        if (persistSettings((settings) => ({ ...settings, integrations: settings.integrations.filter((item) => item.id !== overlay.id) }))) {
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
          activeScenarioCount: activeScenarios.filter((item) => item.agentId === id).length,
        }))}
        onOpen={(id, event) => open({ kind: 'agent', id }, event)}
        onAdd={(event) => open({ kind: 'agent' }, event)} />
      {!overlay && error && <p className="studio-error" role="alert">{error}</p>}
      {studio.issues.map((issue) => <p className="studio-error" role="alert" key={issue}>{issue}</p>)}

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
            {pilotTriggers.map((trigger) => {
              const entry = templates[trigger];
              const { Icon, tone } = libraryVisuals[trigger];
              return (
                <button className="studio-template" data-tone={tone} type="button" key={trigger} aria-haspopup="dialog"
                  onClick={(event) => open({ kind: 'template', trigger }, event)}>
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
          <section className="studio-saved" aria-labelledby="saved-scenarios-title">
            <header className="studio-saved-header">
              <h3 id="saved-scenarios-title" ref={scenariosTitle} tabIndex={-1}>Сохранённые сценарии</h3>
              <span className="studio-saved-count" aria-live="polite">{listedScenarios.length}</span>
              <label className="studio-scenario-filter">
                <input ref={activeFilter} type="checkbox" checked={activeScenariosOnly}
                  onChange={(event) => {
                    setScenariosExpanded(false);
                    onActiveScenariosOnlyChange(event.target.checked);
                  }} />
                Только активные
              </label>
            </header>
            {listedScenarios.length ? (
              <div className="studio-list" id="saved-scenarios-list">
                <div className="studio-list-rows">{scenarioRows.slice(0, scenarioPreviewCount)}</div>
                {hiddenScenarioCount > 0 && (
                  <motion.div className="studio-list-disclosure" initial={false}
                    animate={{ height: scenariosExpanded ? 'auto' : 0, opacity: scenariosExpanded ? 1 : 0 }}
                    transition={{ duration: reducedMotion ? 0 : 0.24, ease: [0.22, 0.78, 0.32, 1] }}
                    inert={!scenariosExpanded} aria-hidden={!scenariosExpanded}>
                    <div className="studio-list-rows studio-list-extra">{scenarioRows.slice(scenarioPreviewCount)}</div>
                  </motion.div>
                )}
              </div>
            ) : (
              <p className="studio-item-meta">{activeScenariosOnly ? 'Нет активных сценариев.' : 'Пока нет сохранённых сценариев.'}</p>
            )}
            {hiddenScenarioCount > 0 && (
              <button className="studio-scenarios-expand" type="button"
                aria-expanded={scenariosExpanded} aria-controls="saved-scenarios-list"
                onClick={() => setScenariosExpanded((expanded) => !expanded)}>
                {scenariosExpanded ? 'Свернуть список' : `Показать ещё ${scenarioCountLabel(hiddenScenarioCount)}`}
                <ChevronDown size={18} aria-hidden="true" />
              </button>
            )}
          </section>
        </section>

        <section className="studio-connections" aria-labelledby="connections-title">
          <div className="studio-section-header">
            <h2 id="connections-title">Интеграции</h2>
          </div>
          <ul className="studio-connection-list" role="list">
            <Connection active={overlay?.kind === 'invest-mcp'} icon={Database} title="T-Invest MCP" connected
              onClick={(event) => open({ kind: 'invest-mcp' }, event)} />
            <Connection active={overlay?.kind === 'provider' && overlay.provider === 'cloud'} icon={CodeXml} title="LLM API" connected={apiConfigured}
              onClick={(event) => open({ kind: 'provider', provider: 'cloud' }, event)} />
            <Connection active={overlay?.kind === 'provider' && overlay.provider === 'ollama'} icon={Laptop} title="Локальное выполнение"
              connected={Boolean(profile.localConfigured)}
              onClick={(event) => open({ kind: 'provider', provider: 'ollama' }, event)} />
            <Connection active={overlay?.kind === 'mail'} icon={Mail} title="Почта" connected={Boolean(mailConfig)}
              onClick={(event) => open({ kind: 'mail' }, event)} />
            <Connection active={overlay?.kind === 'telegram'} icon={Send} title="Telegram" connected={Boolean(telegramChat)}
              onClick={(event) => open({ kind: 'telegram' }, event)} />
            {integrations.map((item) => (
              <Connection active={overlay?.kind === 'extra' && overlay.id === item.id} key={item.id} icon={CodeXml} title={item.name}
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
        <StudioDialog title={modalTitle} info={modalInfo} scenarioDetails={overlay.kind === 'scenario-details'} onClose={close}>
          <div key={overlay.kind}>{modalContent}</div>
          {overlay.kind !== 'agent' && error && <p className="studio-error" role="alert">{error}</p>}
        </StudioDialog>
      )}
    </main>
  );
}

function Connection({ icon: Icon, title, connected = false, active, onClick }: {
  icon: typeof CodeXml;
  title: string;
  connected?: boolean;
  active?: boolean;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <li>
      <button data-active={active} className="studio-connection" type="button" aria-haspopup="dialog" onClick={onClick}>
        <span className="studio-icon"><Icon size={18} strokeWidth={1.75} aria-hidden="true" /></span>
        <span className="studio-connection-copy">
          <strong className="studio-item-title">{title}</strong>
          <span className="studio-item-meta">{connected ? 'Подключено' : 'Не подключено'}</span>
        </span>
        <span className="studio-connection-end">
          <Pencil size={14} aria-hidden="true" />
          Настроить
        </span>
      </button>
    </li>
  );
}

function StudioDialog({ title, info, scenarioDetails, children, onClose }: {
  title: string;
  info?: string;
  scenarioDetails: boolean;
  children: ReactNode;
  onClose: () => void;
}) {
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
    <dialog ref={dialog} className="studio-dialog" data-scenario-details={scenarioDetails}
      aria-labelledby="studio-dialog-title"
      onCancel={(event) => {
        if (event.target !== event.currentTarget) return;
        event.preventDefault();
        onClose();
      }}>
      <header>
        <div className={`studio-dialog-heading${info ? ' studio-dialog-heading-with-info' : ''}`}>
          <h2 id="studio-dialog-title" tabIndex={-1} ref={heading}>{title}</h2>
          {info && <SourceInfo label="О сценарии" text={info} />}
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Закрыть"><X size={20} aria-hidden="true" /></button>
      </header>
      {children}
    </dialog>
  );
}

function TemplateScenario({ initial, agents, telegramConnected, mailConnected, onSave, onCancel }: {
  initial: ScenarioSettings;
  agents: StudioAgent[];
  telegramConnected: boolean;
  mailConnected: boolean;
  onSave: (settings: ScenarioSettings) => void;
  onCancel: () => void;
}) {
  const [assets, setAssets] = useState(initial.assets);
  const [agentId, setAgentId] = useState('');
  const agentOptions = useMemo(() => [
    { value: '', label: 'Выбрать позже' },
    ...agents.map(({ id, name }) => ({ value: id, label: name })),
  ], [agents]);
  const [notification, setNotification] = useState(initial.notification);
  const [error, setError] = useState('');

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (assets.length === 0) {
      setError('Выберите хотя бы один актив.');
      return;
    }
    onSave({ ...initial, assets, notification, workflowVersion: 2,
      actions: notification === 'none' ? (initial.actions ?? ['mcp']).filter((action) => action !== 'report')
        : [...(initial.actions ?? ['mcp']).filter((action) => action !== 'report'), 'report'],
      agentId: agentId || undefined });
  }

  return (
    <form className="studio-form studio-template-form" onSubmit={save}>
      <div className="studio-fields studio-template-fields">
        <div className="studio-field">
          <span>Назначить агенту</span>
          <SpringDropdown floating label="Назначить агенту" options={agentOptions} value={agentId} onChange={setAgentId} />
        </div>
        <div className="studio-field">
          <span>Куда отправлять отчёт</span>
          <SpringDropdown floating preserveDialogPosition label="Куда отправлять отчёт" options={notificationOptions}
            value={notification} onChange={setNotification} />
        </div>
      </div>
      {notification === 'mail' && !mailConnected &&
        <p className="studio-template-hint" role="status">Для доставки отчётов подключите почту в разделе «Интеграции».</p>}
      {notification === 'telegram' && !telegramConnected &&
        <p className="studio-template-hint" role="status">Для доставки отчётов подключите Telegram в разделе «Интеграции».</p>}
      <ScenarioAssets assets={assets} onChange={(selected) => { setAssets(selected); setError(''); }} />
      {error && <p className="studio-error" role="alert">{error}</p>}
      <div className="studio-actions">
        <button className="button button-stop" type="button" onClick={onCancel}>Отмена</button>
        <button className="button button-primary" type="submit">Сохранить сценарий</button>
      </div>
    </form>
  );
}

function ScenarioDetails({ scenario, agentOptions, onAgentChange, onNotificationChange, integrations, onDelete, onEdit }: {
  scenario: Scenario;
  agentOptions: { value: string; label: string }[];
  onAgentChange: (agentId: string) => void;
  onNotificationChange: (notification: ScenarioSettings['notification']) => void;
  integrations: ExtraIntegration[];
  onDelete: () => void;
  onEdit: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const cancelDelete = useRef<HTMLButtonElement>(null);
  const checks = (scenario.checks ?? defaultScenarioChecks).map((check) => scenarioChecks[check]);
  const sources = scenario.integrationIds?.map((id) =>
    integrations.find((item) => item.id === id)?.name ?? 'Удалённая интеграция') ?? [];
  const actions = scenario.actions ?? ['mcp'];
  const sourceGroups = [...new Set((scenario.sources ?? []).map((source) => source.groupId))];
  const assets = scenario.assets.map((ticker) => allSymbols.find((symbol) => symbol.ticker === ticker)
    ?? { ticker, name: 'Неизвестный актив', logo: '/logos/marketing.svg' });
  const signalMethod = scenario.trigger === 'price-z' ? 'Z-score с EWMA' : scenario.trigger === 'relative' ? 'Z-score' : null;

  function requestDelete() {
    setConfirmDelete(true);
    requestAnimationFrame(() => cancelDelete.current?.focus());
  }

  function cancelDeleteRequest() {
    setConfirmDelete(false);
    requestAnimationFrame(() => deleteButton.current?.focus());
  }

  return (
    <div className="studio-scenario-details">
      <div className="studio-scenario-overview">
        <section className="studio-scenario-fact">
          <h3>{assets.length === 1 ? 'Актив' : 'Активы'}</h3>
          <ul className="studio-scenario-assets" role="list">
            {assets.map(({ ticker, name, logo }, index) => (
              <li key={`${ticker}-${index}`}>
                <img src={logo} alt="" width="36" height="36" />
                <div>
                  <strong>{ticker}</strong>
                  <span>{name}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
        <section className="studio-scenario-fact">
          <h3>Модель сигнала</h3>
          <div className="studio-scenario-model">
            <strong>{templates[scenario.trigger].title}</strong>
            <p className="figures">{[signalMethod, describeTrigger(scenario)].filter(Boolean).join(' · ')}</p>
          </div>
        </section>
      </div>

      <section className="studio-scenario-workflow">
        <h3>После сигнала</h3>
        <ol className="studio-scenario-flow" role="list">
          {actions.map((action, index) => (
            <li key={`${action}-${index}`}>
              <strong>{scenarioActions[action]}</strong>
              {action === 'report' && <span> — {scenarioNotifications[scenario.notification]}</span>}
              {action === 'source' && <span> — {scenario.sources?.filter((source) => source.groupId === sourceGroups[actions.slice(0, index).filter((item) => item === 'source').length])
                .map((source) => source.kind === 'cbr' ? 'Банк России' : source.url).join(', ')}</span>}
              {action === 'mcp' && (
                <span> — сбор рыночных данных ({checks.join(', ') || 'инструменты не выбраны'})</span>
              )}
            </li>
          ))}

        </ol>
        {!scenario.actions && sources.length > 0 && (
          <p className="studio-scenario-sources"><strong>Другие интеграции</strong> {sources.join(', ')}</p>
        )}
      </section>

      {scenario.instructions && (
        <section className="studio-scenario-instructions">
          <h3>Акцент отчёта</h3>
          <p>{scenario.instructions}</p>
        </section>
      )}

      <dl className="studio-scenario-meta">
        <div>
          <dt>Агент</dt>
          <dd><SpringDropdown floating label="Агент" options={agentOptions} value={scenario.agentId ?? ''}
            onChange={onAgentChange} /></dd>
        </div>
        <div>
          <dt>Уведомления</dt>
          <dd><SpringDropdown floating preserveDialogPosition label="Уведомления" options={notificationOptions}
            value={scenario.notification} onChange={onNotificationChange} /></dd>
        </div>
      </dl>

      <footer className="studio-scenario-footer">
        {confirmDelete ? (
          <>
            <p id="studio-scenario-delete-prompt">Удалить сценарий «{scenario.name}»?</p>
            <div className="studio-actions">
              <button ref={cancelDelete} className="button button-stop" type="button"
                aria-describedby="studio-scenario-delete-prompt" onClick={cancelDeleteRequest}>Отмена</button>
              <button className="button button-stop studio-delete-button studio-confirm-delete" type="button"
                aria-describedby="studio-scenario-delete-prompt" onClick={onDelete}>Удалить</button>
            </div>
          </>
        ) : (
          <div className="studio-actions studio-scenario-actions">
            <button ref={deleteButton} className="button button-stop studio-delete-button" type="button" onClick={requestDelete}>
              Удалить сценарий
            </button>
            <button className="button button-primary" type="button" onClick={onEdit}>Редактировать</button>
          </div>
        )}
      </footer>
    </div>
  );
}

const agentProviderOptions = [
  { value: 'ollama', label: 'Локально' },
  { value: 'cloud', label: 'Через API' },
] as const;

function AgentSettings({ agent, error, scenarios, availableScenarios, onSave, onCancel, onDelete, onClearError }: {
  agent?: StudioAgent;
  error: string;
  scenarios: Scenario[];
  availableScenarios: Scenario[];
  onSave: (agent: StudioAgent, editing: boolean, scenarioIds: string[], enabledIds: string[]) => void;
  onDelete: (agent: StudioAgent) => void;
  onCancel: () => void;
  onClearError: () => void;
}) {
  const [provider, setProvider] = useState<StudioAgent['provider']>(agent?.provider ?? 'ollama');
  const [selectedScenarioIds, setSelectedScenarioIds] = useState(() => scenarios.map(({ id }) => id));
  const [enabledScenarioIds, setEnabledScenarioIds] = useState(() => scenarios.filter(({ enabled }) => enabled).map(({ id }) => id));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const cancelDelete = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!confirmDelete) return;
    const dialog = deleteDialog.current;
    dialog?.showModal();
    cancelDelete.current?.focus();
    return () => dialog?.close();
  }, [confirmDelete]);

  function dismissDelete() {
    deleteDialog.current?.close();
    setConfirmDelete(false);
    onClearError();
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSave({
      id: agent?.id ?? crypto.randomUUID(),
      name: String(data.get('name')).trim(),
      provider,
    }, Boolean(agent), selectedScenarioIds, enabledScenarioIds);
  }

  return (
    <>
      <form className="studio-form studio-agent-form" onSubmit={save}>
        <label className="studio-field">
          <span className="studio-agent-field-label">Название</span>
          <input name="name" defaultValue={agent?.name} required pattern=".*\S.*" maxLength={60} placeholder="Например, Рыночный радар" />
        </label>
        <div className="studio-field">
          <span className="studio-agent-field-label">Где выполнять анализ</span>
          <SpringDropdown floating label="Где выполнять анализ" options={agentProviderOptions}
            value={provider} onChange={setProvider} />
        </div>
        <AgentScenarioPicker scenarios={availableScenarios} selectedIds={selectedScenarioIds}
          enabledIds={enabledScenarioIds}
          onToggle={(id) => {
            setEnabledScenarioIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]);
            onClearError();
          }}
          onChange={(ids) => {
            setSelectedScenarioIds(ids);
            setEnabledScenarioIds((enabled) => enabled.filter((id) => ids.includes(id)));
            onClearError();
          }} />
        {error && !confirmDelete && <p className="studio-error" role="alert">{error}</p>}
        <div className={agent ? 'studio-actions studio-agent-actions' : 'studio-actions'}>
          {agent && (
            <button className="button button-stop studio-delete-button" type="button" aria-haspopup="dialog"
              onClick={(event) => {
                event.currentTarget.focus();
                onClearError();
                setConfirmDelete(true);
              }}>
              <Trash2 size={18} aria-hidden="true" /> Удалить агента
            </button>
          )}
          <button className="button button-stop" type="button" onClick={onCancel}>Отмена</button>
          <button className="button button-primary" type="submit">{agent ? 'Сохранить настройки' : 'Создать агента'}</button>
        </div>
      </form>
      {agent && confirmDelete && (
        <dialog ref={deleteDialog} className="studio-dialog studio-agent-confirm" role="alertdialog"
          aria-labelledby="studio-agent-confirm-title" aria-describedby="studio-agent-confirm-copy"
          onCancel={(event) => {
            event.preventDefault();
            event.stopPropagation();
            dismissDelete();
          }}>
          <h2 id="studio-agent-confirm-title">Удалить агента?</h2>
          <p className="studio-dialog-copy" id="studio-agent-confirm-copy">Сохранённые сценарии останутся без изменений</p>
          {error && <p className="studio-error" role="alert">{error}</p>}
          <div className="studio-actions">
            <button ref={cancelDelete} className="button button-stop" type="button" onClick={dismissDelete}>Отмена</button>
            <button className="button button-stop studio-delete-button" type="button" onClick={() => onDelete(agent)}>Удалить</button>
          </div>
        </dialog>
      )}
    </>
  );
}

function ScenarioSwitch({ scenario, onToggle }: { scenario: Scenario; onToggle: (item: Scenario) => void }) {
  return (
    <button className="studio-switch" type="button" role="switch" aria-checked={scenario.enabled}
      aria-label={`Сценарий «${scenario.name}»`} onClick={() => onToggle(scenario)} />
  );
}
