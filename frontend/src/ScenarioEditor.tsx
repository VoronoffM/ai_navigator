import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, Globe2, GripVertical, Library, Link2, Plus, Send, X } from 'lucide-react';
import { ScenarioAssets } from './ScenarioAssets';
import {
  cbrCalendarUrl, defaultScenarioChecks, draftFrom, isPilotTrigger, pilotTriggers, scenarioActions, scenarioChecks,
  scenarioNotifications, scenarioPeriods, templates, workflowActions,
  type ScenarioSettings, type SourceAction,
} from './scenarios';
import { ScenarioProgress } from './ScenarioProgress';
import { SpringDropdown } from './SpringDropdown';
import type { ExtraIntegration, StudioAgent } from './studioSettings';
import { ExtraSettings } from './StudioIntegrations';
import { SourceInfo } from './SourceInfo';
import { SourceCatalog } from './SourceCatalog';

const steps = [
  { label: 'Активы', title: 'Выберите активы' },
  { label: 'Сигнал', title: 'Настройка сигнала' },
  { label: 'Агент и действия', title: 'Агент и действия' },
] as const;
const stepLabels = steps.map(({ label }) => label);
const priceDirections = [
  { value: 'either', label: 'Рост или падение' },
  { value: 'up', label: 'Только рост' },
  { value: 'down', label: 'Только падение' },
] as const;
const relativeDirections = [
  { value: 'either', label: 'Выше или ниже индекса' },
  { value: 'up', label: 'Выше индекса' },
  { value: 'down', label: 'Ниже индекса' },
] as const;
const notificationOptions = (Object.keys(scenarioNotifications) as ScenarioSettings['notification'][])
  .map((value) => ({ value, label: scenarioNotifications[value] }));

export function ScenarioEditor({ initial, agents, isNew, onSave, onCancel, onSaveIntegration }: {
  initial: ScenarioSettings; agents: StudioAgent[]; isNew: boolean;
  onSave: (settings: ScenarioSettings) => void; onCancel: () => void;
  onSaveIntegration: (integration: ExtraIntegration) => boolean;
}) {
  const [draft, setDraft] = useState(() => {
    const legacyTask = [...new Set((initial.sources ?? []).filter((source) => !source.groupId)
      .map((source) => source.instructions).filter(Boolean))].join('\n');
    return { ...initial, actions: workflowActions(initial), sources: (initial.sources ?? []).map((source) =>
      source.groupId ? source : { ...source, groupId: 'legacy', instructions: legacyTask }) };
  });
  const [entries, setEntries] = useState(() => {
    const groups = [...new Set(draft.sources.map((source) => source.groupId))];
    let sourceIndex = 0;
    return draft.actions.map((action) => ({ action,
      id: action === 'source' ? groups[sourceIndex++] ?? crypto.randomUUID() : crypto.randomUUID() }));
  });
  const agentOptions = useMemo(() => [
    { value: '', label: 'Выберите агента' },
    ...agents.map(({ id, name }) => ({ value: id, label: name })),
  ], [agents]);
  const selectedAgent = agents.find(({ id }) => id === draft.agentId)?.id ?? '';
  const [triggerOptions] = useState(() =>
    [...new Set([...pilotTriggers, initial.trigger])]
      .map((value) => ({ value, label: templates[value].title })),
  );
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const nameId = useId();
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const customModelDialog = useRef<HTMLDialogElement>(null);
  const customModelAcknowledge = useRef<HTMLButtonElement>(null);
  const checks = draft.checks ?? defaultScenarioChecks;
  const actions = entries.map(({ action }) => action);

  const [addingIntegration, setAddingIntegration] = useState(false);
  const [integrationError, setIntegrationError] = useState('');
  const integrationDialog = useRef<HTMLDialogElement>(null);
  const integrationOpener = useRef<HTMLButtonElement>(null);
  const [dragging, setDragging] = useState<string>();
  const [dropTarget, setDropTarget] = useState<string>();
  const [showActions, setShowActions] = useState(false);
  const availableActions = (Object.keys(scenarioActions) as SourceAction[]).filter((action) => action !== 'cbr' && (action === 'source' ? actions.length < 32 : !actions.includes(action)));
  const pilot = isPilotTrigger(draft.trigger);
  const relative = draft.trigger === 'relative';
  const directionLabel = relative ? 'Динамика относительно IMOEX' : 'Направление цены';
  const volume = draft.trigger === 'volume-spike' || draft.trigger === 'volume';
  const period = scenarioPeriods.find(({ value }) => Number(value) === draft.windowMinutes);
  const newScenarioAssets = isNew && step === 0;
  const thresholdLabel = {
    'price-z': 'Порог необычности (Z-score)',
    'volume-spike': 'Объём выше обычного, раз',
    relative: 'Порог расхождения (Z-score)',
    volume: 'Объём к среднему, раз',
    volatility: 'Размах цены, %',
    price: 'Изменение цены, %',
    news: '',
  }[draft.trigger];

  useEffect(() => {
    stepHeading.current?.focus({ preventScroll: true });
    stepHeading.current?.closest('dialog')?.scrollTo(0, 0);
  }, [step]);

  function update(change: Partial<ScenarioSettings>) {
    setDraft((current) => ({ ...current, ...change }));
    setError('');
  }

  useEffect(() => {
    if (addingIntegration) integrationDialog.current?.showModal();
  }, [addingIntegration]);

  function closeIntegration() {
    integrationDialog.current?.close();
    setAddingIntegration(false);
    setIntegrationError('');
    requestAnimationFrame(() => integrationOpener.current?.focus());
  }

  function moveAction(from: string, to: string) {
    if (from === to) return;
    setEntries((current) => {
      const reordered = [...current];
      const fromIndex = current.findIndex(({ id }) => id === from);
      const toIndex = current.findIndex(({ id }) => id === to);
      if (fromIndex < 0 || toIndex < 0) return current;
      const [entry] = reordered.splice(fromIndex, 1);
      reordered.splice(toIndex, 0, entry);
      return reordered;
    });
  }

  function endDrag() {
    setDragging(undefined);
    setDropTarget(undefined);
  }

  function next(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step === 0 && (!draft.name.trim() || draft.assets.length === 0)) {
      setError(!draft.name.trim() ? 'Введите название сценария.' : 'Выберите хотя бы один актив.');
      return;
    }
    if (step === 1 && draft.trigger !== 'news' && !period) {
      setError('Выберите период.');
      return;
    }
    if (step < steps.length - 1) {
      setStep(step + 1);
      return;
    }
    if (!agents.some((agent) => agent.id === draft.agentId)) {
      setError('Выберите агента для сценария.');
      return;
    }
    if (actions.length === 0 || (actions.includes('mcp') && checks.length === 0)) {
      setError(actions.length === 0 ? 'Добавьте хотя бы одно действие.' : 'Выберите хотя бы один инструмент T-Invest MCP.');
      return;
    }
    const sources = entries.filter(({ action }) => action === 'source')
      .flatMap(({ id }) => draft.sources.filter((source) => source.groupId === id));
    if (entries.some(({ action, id }) => action === 'source' && !sources.some((source) => source.groupId === id))
      || sources.some((source) => {
      try { const url = new URL(source.url); return url.protocol !== 'https:' || !!url.username || !!url.password || !source.instructions.trim(); }
      catch { return true; }
    })) {
      setError('Для каждого источника укажите HTTPS-ссылку и задачу агенту.');
      return;
    }
    onSave({
      ...draft, actions, sources, checks, workflowVersion: 2,
      notification: actions.includes('report') ? (draft.notification === 'none' ? 'in-app' : draft.notification) : 'none',
      name: draft.name.trim(), keywords: draft.keywords.trim(), instructions: draft.instructions.trim(),
    });
  }


  return (
    <div className="studio-editor">
      <ScenarioProgress labels={stepLabels} current={step} />

      <form className={`studio-form${newScenarioAssets ? ' new-scenario-assets' : step === 1 ? ' scenario-signal' : ''}`} onSubmit={next}>
        {!newScenarioAssets && step === 0 && (
          <h3 id="scenario-step-title" tabIndex={-1} ref={stepHeading}>{steps[step].title}</h3>
        )}
        {step === 0 && (
          <>
            <div className="studio-field">
              {newScenarioAssets ? (
                <h3 id="scenario-step-title" tabIndex={-1} ref={stepHeading}>
                  <label htmlFor={nameId}>Название сценария</label>
                </h3>
              ) : <label htmlFor={nameId}>Название сценария</label>}
              <input id={nameId} value={draft.name} required maxLength={80} placeholder="Например, резкое движение GAZP"
                onChange={(event) => update({ name: event.target.value })} />
            </div>
            <ScenarioAssets assets={draft.assets} onChange={(assets) => update({ assets })} />
          </>
        )}
        {step === 1 && (
          <>
            <div className="scenario-signal-heading">
              <h3 id="scenario-step-title" tabIndex={-1} ref={stepHeading}>{steps[step].title}</h3>
              <SourceInfo label="Что такое сигнал" text="Сигнал — это условие, при котором сценарий срабатывает. Например: падение цены, рост объёма или выход новости." />
              <button className="studio-custom-trigger" type="button" aria-haspopup="dialog"
                  onClick={() => {
                    customModelDialog.current?.showModal();
                    customModelAcknowledge.current?.focus();
                  }}>
                  <Plus size={16} aria-hidden="true" /> Добавить свою модель
              </button>
            </div>
            <section className="scenario-signal-section" aria-label="Модель сигнала">
              <SpringDropdown floating label="Модель сигнала" preserveDialogPosition
                options={triggerOptions} value={draft.trigger} onChange={(trigger) => {
                const { threshold, windowMinutes } = draftFrom(trigger);
                update({ trigger, threshold, windowMinutes });
              }} />
              {(pilot || draft.trigger === 'price') && <p className="signal-description">{templates[draft.trigger].description}</p>}
            </section>
            <section className="scenario-signal-section scenario-signal-parameters" aria-labelledby="signal-parameters-title">
              <h4 id="signal-parameters-title">Параметры сигнала</h4>
              {(draft.trigger === 'price' || draft.trigger === 'price-z' || relative) && (
                <div className="studio-field">
                  <span>{directionLabel}</span>
                  <SpringDropdown floating label={directionLabel} options={relative ? relativeDirections : priceDirections}
                    value={draft.direction} onChange={(direction) => update({ direction })} />
                </div>
              )}
              {draft.trigger === 'news' ? (
                <label className="studio-field">Ключевые слова через запятую
                  <input value={draft.keywords} maxLength={200} placeholder="Любые новости, если оставить пустым"
                    onChange={(event) => update({ keywords: event.target.value })} />
                </label>
              ) : (
                <div className="studio-fields">
                  <label className="studio-field">{thresholdLabel}
                    <input type="number" required min={volume ? 1.01 : 0.01} step="0.01" value={draft.threshold || ''}
                      onChange={(event) => update({ threshold: Number(event.target.value) })} />
                  </label>
                  <div className="studio-field">
                    <span>{period ? 'Период' : 'Выберите период'}</span>
                    <SpringDropdown floating label="Период" options={scenarioPeriods}
                      value={period?.value ?? ''} onChange={(value) => update({ windowMinutes: Number(value) })} />
                  </div>
                </div>
              )}
            </section>
          </>
        )}
        {step === 2 && (
          <>
            <section className="studio-workflow-section" aria-labelledby="workflow-agent-title">
              <h4 id="workflow-agent-title" tabIndex={-1} ref={stepHeading}>Агент</h4>
              <div className="studio-field">
              <SpringDropdown floating label="Агент" options={agentOptions} value={selectedAgent}
                onChange={(agentId) => update({ agentId: agentId || undefined })} />
            </div>
              {agents.length === 0 && <p>Создайте агента в Agent Studio, затем вернитесь к сценарию.</p>}
            </section>
            <section className="studio-workflow-section studio-workflow-actions" aria-labelledby="workflow-actions-title">
            <h4 id="workflow-actions-title">Действия</h4>
            {actions.length === 0 && <p className="studio-workflow-empty">Действий пока нет. Добавьте первое действие.</p>}
            <ol className="studio-workflow" role="list" aria-label="Порядок действий">
              {entries.map(({ action, id }, index) => {
                const sources = draft.sources.filter((source) => source.groupId === id);
                const task = sources[0]?.instructions ?? '';
                function updateSources(nextSources: typeof sources) {
                  update({ sources: [...draft.sources.filter((source) => source.groupId !== id),
                    ...nextSources.map((source) => ({ ...source, groupId: id }))] });
                }
                const neighbor = entries[index === 0 ? 1 : index - 1]?.id;
                const MoveIcon = index === 0 ? ArrowDown : ArrowUp;
                return <li className={`studio-workflow-card${action === 'source' ? ' studio-research-card' : action === 'report' ? ' studio-workflow-report' : ''}`} key={id} data-drop-target={dropTarget === id}
                  onDragOver={(event) => {
                    if (!dragging || dragging === id) return;
                    event.preventDefault();
                    event.dataTransfer.dropEffect = 'move';
                    setDropTarget(id);
                  }}
                  onDragLeave={(event) => {
                    if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) {
                      setDropTarget((current) => current === id ? undefined : current);
                    }
                  }}
                  onDrop={(event) => {
                    if (!dragging) return;
                    event.preventDefault();
                    moveAction(dragging, id);
                    endDrag();
                  }}>
                  <header>
                    <span className="studio-workflow-index">{index + 1}</span>
                    <div className="studio-workflow-title"><h5>{scenarioActions[action]}</h5>{action === 'source' && <SourceInfo />}</div>
                    {neighbor && <button className="studio-workflow-icon studio-workflow-handle" type="button" draggable
                      title={index === 0 ? 'Переместить ниже' : 'Переместить выше'}
                      aria-label={`${index === 0 ? 'Переместить ниже' : 'Переместить выше'}: ${scenarioActions[action]}`}
                      onClick={() => moveAction(id, neighbor)}
                      onDragStart={(event) => {
                        event.dataTransfer.setData('text/plain', id);
                        event.dataTransfer.effectAllowed = 'move';
                        setDragging(id);
                      }}
                      onDragEnd={endDrag}>
                      <GripVertical size={17} aria-hidden="true" /><MoveIcon size={13} aria-hidden="true" />
                    </button>}
                    <button className="studio-workflow-icon" type="button" title="Убрать действие"
                      aria-label={`Убрать действие: ${scenarioActions[action]}`}
                      onClick={() => {
                        setEntries(entries.filter((entry) => entry.id !== id));
                        update({ sources: draft.sources.filter((source) => source.groupId !== id) });
                      }}>
                      <X size={16} aria-hidden="true" />
                    </button>
                  </header>
                  {action === 'mcp' ? (
                    <fieldset className="studio-assets" aria-label="Инструменты T-Invest MCP">
                      <div className="studio-asset-options">
                        {defaultScenarioChecks.map((check) => (
                          <label className="watch-chip" key={check}>
                            <input type="checkbox" checked={checks.includes(check)} onChange={() => update({
                              checks: checks.includes(check) ? checks.filter((item) => item !== check) : [...checks, check],
                            })} />
                            <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>
                            {scenarioChecks[check]}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  ) : action === 'report' ? (
                    <div className="studio-field">
                      <Send size={18} aria-hidden="true" />
                      <SpringDropdown floating label="Куда отправлять отчёт"
                        options={notificationOptions.filter(({ value }) => value !== 'none')}
                        value={draft.notification === 'none' ? 'in-app' : draft.notification}
                        onChange={(notification) => update({ notification })} />
                    </div>
                  ) : action === 'cbr' ? (
                    <a href={cbrCalendarUrl} target="_blank" rel="noopener noreferrer">Календарь решений по ключевой ставке</a>
                  ) : (
                    <div className="studio-research">
                      <section className="studio-research-section" aria-label="Источники информации">
                        <div className="studio-research-section-heading">
                        {sources.length < 5 && <div className="studio-research-add">
                          <button className="studio-research-link" type="button" aria-label="Добавить URL" title="Добавить URL"
                            onClick={() => updateSources([...sources, { kind: 'url', url: '', instructions: task }])}>
                            <Plus size={15} aria-hidden="true" /> <span className="studio-research-add-label">Добавить</span> URL
                          </button>
                          <SourceCatalog>
                            <button type="button" className="studio-research-catalog-option" onClick={() => {
                              const readySource = {
                                kind: 'cbr' as const, url: cbrCalendarUrl,
                                instructions: task || 'Проверь решения по ключевой ставке в окне сигнала и их возможное влияние.',
                              };
                              const emptyIndex = sources.findIndex((source) => !source.url.trim());
                              const nextSources = emptyIndex < 0 ? [...sources, readySource]
                                : sources.map((item, i) => i === emptyIndex ? readySource : item);
                              updateSources(nextSources.map((source) => ({ ...source, instructions: readySource.instructions })));
                            }}>
                              <Library size={18} aria-hidden="true" />
                              <span><strong>Банк России</strong><small>Календарь решений по ключевой ставке</small></span>
                              <Plus size={16} aria-hidden="true" />
                            </button>
                          </SourceCatalog>
                        </div>}
                        </div>
                        {sources.length > 0 && <ul className="studio-research-sources" aria-label="Выбранные источники">
                          {sources.map((source, sourceIndex) => <li className="studio-research-source" key={sourceIndex}>
                            <span className="studio-research-symbol" aria-hidden="true">
                              <Globe2 size={18} />
                            </span>
                            <div className="studio-research-source-content">
                              <div className="studio-research-url studio-field">
                                <Link2 size={15} aria-hidden="true" />
                                <input type="url" required maxLength={2048} value={source.url}
                                  aria-label={`URL источника ${sourceIndex + 1}`} title={source.url}
                                  placeholder="https://example.com/article" autoComplete="url" spellCheck={false}
                                  onChange={(event) => updateSources(sources.map((item, i) =>
                                    i === sourceIndex ? { ...item, kind: 'url', url: event.target.value } : item))} />
                              </div>
                            </div>
                            <button type="button" className="studio-workflow-icon studio-research-remove"
                              title="Удалить источник" aria-label={`Удалить источник ${sourceIndex + 1}`}
                              onClick={() => updateSources(sources.filter((_, i) => i !== sourceIndex))}>
                              <X size={16} aria-hidden="true" />
                            </button>
                          </li>)}
                        </ul>}

                      </section>
                      {sources.length > 0 && <section className="studio-research-section studio-research-task" aria-label="Задача для агента">
                        <h6>Задача для агента</h6>
                        <label className="studio-field">
                            <textarea required maxLength={1000} rows={2} value={task}
                              aria-label="Задача для агента"
                              placeholder="Например, найди заявления о ставке перед сигналом"
                              onChange={(event) => updateSources(sources.map((source) =>
                                ({ ...source, instructions: event.target.value })))} />
                          </label>
                      </section>}
                    </div>
                  )}
                </li>;
              })}
            </ol>
              <div className="studio-workflow-add">
                  <button className="studio-workflow-add-button" type="button" aria-expanded={showActions}
                    onClick={() => setShowActions(!showActions)}>
                    <Plus size={16} aria-hidden="true" /> Добавить действие
                  </button>
                  {showActions && <div className="studio-workflow-options">
                    {availableActions.map((action) => <button type="button" key={action} onClick={() => {
                      const id = crypto.randomUUID();
                      setEntries([...entries, { action, id }]);
                      if (action === 'source') update({ sources: [...draft.sources,
                        { groupId: id, kind: 'url', url: '', instructions: '' }] });
                      setShowActions(false);
                    }}>{scenarioActions[action]}</button>)}
                    <button type="button" ref={integrationOpener} aria-haspopup="dialog" onClick={() => setAddingIntegration(true)}>
                      Подключить через API / MCP
                    </button>
                  </div>}
              </div>
            </section>
          </>
        )}
        {error && <p className="studio-error" role="alert">{error}</p>}
        <div className={step === 0 ? 'studio-assets-footer' : step === 1 ? 'studio-signal-footer' : undefined}>
          <div className="studio-actions">
            <button className="button button-stop" type="button" onClick={() => {
              if (step === 0) onCancel();
              else setStep(step - 1);
            }}>
              {step > 0 && <ArrowLeft size={16} aria-hidden="true" />}{step === 0 ? 'Отмена' : 'Назад'}
            </button>
            <button className="button button-primary" type="submit">
              {step === steps.length - 1 ? 'Сохранить сценарий' : <>Далее <ArrowRight size={16} aria-hidden="true" /></>}
            </button>
          </div>
        </div>
      </form>
      {addingIntegration && <dialog ref={integrationDialog} className="studio-dialog" aria-labelledby="scenario-integration-title"
        onCancel={(event) => { event.preventDefault(); closeIntegration(); }}>
        <header><h2 id="scenario-integration-title">Новая интеграция</h2>
          <button type="button" className="icon-button" aria-label="Закрыть интеграцию" onClick={closeIntegration}><X size={20} /></button>
        </header>
        {integrationError && <p className="studio-error" role="alert">{integrationError}</p>}
        <ExtraSettings onSave={(integration) => {
          if (onSaveIntegration(integration)) {
            update({ integrationIds: [...new Set([...(draft.integrationIds ?? []), integration.id])] });
            closeIntegration();
          } else setIntegrationError('Не удалось сохранить интеграцию в браузере. Попробуйте ещё раз.');
        }} onCancel={closeIntegration} onRemove={closeIntegration} />
      </dialog>}
      {step === 1 && (
        <dialog className="studio-dialog studio-model-info" ref={customModelDialog}
          aria-labelledby="custom-model-title" aria-describedby="custom-model-description">
          <header>
            <h2 id="custom-model-title">Своя модель</h2>
            <button className="icon-button studio-model-info-close" type="button" aria-label="Закрыть"
              onClick={() => customModelDialog.current?.close()}>
              <X size={16} aria-hidden="true" />
            </button>
          </header>
          <p className="studio-dialog-copy" id="custom-model-description">
            Подключение своих моделей пока недоступно. Вы можете выбрать одну из готовых моделей
          </p>
          <footer className="studio-actions">
            <button className="button button-stop" type="button" ref={customModelAcknowledge}
              onClick={() => customModelDialog.current?.close()}>
              Понятно
            </button>
          </footer>
        </dialog>
      )}
    </div>
  );
}
