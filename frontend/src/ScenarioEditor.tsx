import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, GripVertical, LockKeyhole, Plus, X } from 'lucide-react';
import { symbols, type Ticker } from './market';
import {
  cbrCalendarUrl, defaultScenarioChecks, draftFrom, isPilotTrigger, pilotTriggers, reportFormats, scenarioActions, scenarioChecks,
  scenarioNotifications, templates,
  type ScenarioSettings, type SourceAction,
} from './scenarios';
import { ScenarioProgress } from './ScenarioProgress';
import { SpringDropdown } from './SpringDropdown';
import type { StudioAgent } from './studioSettings';

const allAssets = symbols.map(({ ticker }) => ticker);
const steps = [
  { label: 'Активы', title: 'Выберите активы' },
  { label: 'Сигнал', title: 'Настройте модель срабатывания сигнала' },
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
const reportOptions = (Object.keys(reportFormats) as ScenarioSettings['depth'][])
  .map((value) => ({ value, label: reportFormats[value] }));
const notificationOptions = (Object.keys(scenarioNotifications) as ScenarioSettings['notification'][])
  .map((value) => ({ value, label: scenarioNotifications[value] }));

export function ScenarioAssets({ assets, onChange }: { assets: Ticker[]; onChange: (assets: Ticker[]) => void }) {
  const allSelected = allAssets.every((ticker) => assets.includes(ticker));
  return (
    <fieldset className="studio-assets">
      <legend>Активы</legend>
      <div className="studio-asset-options">
        <label className="watch-chip">
          <input type="checkbox" checked={allSelected} onChange={() => onChange(allSelected ? [] : allAssets)} />
          <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>Все активы
        </label>
        {symbols.map(({ ticker, name }) => {
          const selected = assets.includes(ticker);
          return (
            <label className="watch-chip" key={ticker} title={name}>
              <input type="checkbox" checked={selected} onChange={() => onChange(
                selected ? assets.filter((item) => item !== ticker) : [...assets, ticker],
              )} />
              <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>{ticker}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export function ScenarioEditor({ initial, agents, onSave, onCancel }: {
  initial: ScenarioSettings; agents: StudioAgent[];
  onSave: (settings: ScenarioSettings) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const agentOptions = useMemo(() => [
    { value: '', label: 'Выберите агента' },
    ...agents.map(({ id, name }) => ({ value: id, label: name })),
  ], [agents]);
  const selectedAgent = agents.find(({ id }) => id === draft.agentId)?.id ?? '';
  const [triggerOptions] = useState(() =>
    (isPilotTrigger(initial.trigger) ? pilotTriggers : [...pilotTriggers, initial.trigger])
      .map((value) => ({ value, label: templates[value].title })),
  );
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const checks = draft.checks ?? defaultScenarioChecks;
  const actions = draft.actions ?? ['mcp'];
  const [dragging, setDragging] = useState<SourceAction>();
  const [dropTarget, setDropTarget] = useState<SourceAction>();
  const [showActions, setShowActions] = useState(false);
  const availableActions = (Object.keys(scenarioActions) as SourceAction[]).filter((action) => !actions.includes(action));
  const pilot = isPilotTrigger(draft.trigger);
  const relative = draft.trigger === 'relative';
  const directionLabel = relative ? 'Динамика относительно IMOEX' : 'Направление цены';
  const volume = draft.trigger === 'volume-spike' || draft.trigger === 'volume';
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

  function moveAction(from: SourceAction, to: SourceAction) {
    if (from === to) return;
    const reordered = [...actions];
    reordered.splice(reordered.indexOf(from), 1);
    reordered.splice(actions.indexOf(to), 0, from);
    update({ actions: reordered });
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
    if (step < steps.length - 1) {
      setStep(step + 1);
      return;
    }
    if (!agents.some((agent) => agent.id === draft.agentId)) {
      setError('Выберите агента для сценария.');
      return;
    }
    if (actions.length === 0 || (actions.includes('mcp') && checks.length === 0)) {
      setError(actions.length === 0 ? 'Добавьте хотя бы одну проверку.' : 'Выберите хотя бы один инструмент T-Invest MCP.');
      return;
    }
    onSave({
      ...draft, actions, checks,
      name: draft.name.trim(), keywords: draft.keywords.trim(), instructions: draft.instructions.trim(),
    });
  }

  return (
    <div className="studio-editor">
      <ScenarioProgress labels={stepLabels} current={step} />

      <form className="studio-form" onSubmit={next}>
        <h3 id="scenario-step-title" tabIndex={-1} ref={stepHeading}>{steps[step].title}</h3>
        {step === 0 && (
          <>
            <label className="studio-field">Название сценария
              <input value={draft.name} required maxLength={80} placeholder="Например, резкое движение GAZP"
                onChange={(event) => update({ name: event.target.value })} />
            </label>
            <ScenarioAssets assets={draft.assets} onChange={(assets) => update({ assets })} />
          </>
        )}
        {step === 1 && (
          <>
            <SpringDropdown floating label="Модель сигнала" preserveDialogPosition
              options={triggerOptions} value={draft.trigger} onChange={(trigger) => {
              const { threshold, windowMinutes } = draftFrom(trigger);
              update({ trigger, threshold, windowMinutes });
            }} />
            {pilot && <p className="signal-description">{templates[draft.trigger].description}</p>}
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
                <label className="studio-field">Период, мин
                  <input type="number" required min={1} step={1} readOnly={pilot} value={draft.windowMinutes || ''}
                    onChange={(event) => update({ windowMinutes: Number(event.target.value) })} />
                </label>
              </div>
            )}
            <details className="studio-custom-trigger">
              <summary>Добавить свою модель</summary>
              <p>Свои модели пока недоступны. Выберите готовую модель, чтобы сохранить сценарий.</p>
            </details>
          </>
        )}
        {step === 2 && (
          <>
            <div className="studio-field">
              <span>Агент</span>
              <SpringDropdown floating label="Агент" options={agentOptions} value={selectedAgent}
                onChange={(agentId) => update({ agentId: agentId || undefined })} />
            </div>
            {agents.length === 0 && <p>Создайте агента в Agent Studio, затем вернитесь к сценарию.</p>}
            <ol className="studio-workflow" role="list" aria-label="Порядок действий">
              {actions.map((action, index) => {
                const neighbor = actions[index === 0 ? 1 : index - 1];
                const MoveIcon = index === 0 ? ArrowDown : ArrowUp;
                return <li className="studio-workflow-card" key={action} data-drop-target={dropTarget === action}
                  onDragOver={(event) => {
                    if (!dragging || dragging === action) return;
                    event.preventDefault();
                    event.dataTransfer.dropEffect = 'move';
                    setDropTarget(action);
                  }}
                  onDragLeave={(event) => {
                    if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) {
                      setDropTarget((current) => current === action ? undefined : current);
                    }
                  }}
                  onDrop={(event) => {
                    if (!dragging) return;
                    event.preventDefault();
                    moveAction(dragging, action);
                    endDrag();
                  }}>
                  <header>
                    <span className="studio-workflow-index">{index + 1}</span>
                    <h4>{scenarioActions[action]}</h4>
                    {neighbor && <button className="studio-workflow-icon studio-workflow-handle" type="button" draggable
                      title={index === 0 ? 'Переместить ниже' : 'Переместить выше'}
                      aria-label={`${index === 0 ? 'Переместить ниже' : 'Переместить выше'}: ${scenarioActions[action]}`}
                      onClick={() => moveAction(action, neighbor)}
                      onDragStart={(event) => {
                        event.dataTransfer.setData('text/plain', action);
                        event.dataTransfer.effectAllowed = 'move';
                        setDragging(action);
                      }}
                      onDragEnd={endDrag}>
                      <GripVertical size={17} aria-hidden="true" /><MoveIcon size={13} aria-hidden="true" />
                    </button>}
                    <button className="studio-workflow-icon" type="button" title="Убрать проверку"
                      aria-label={`Убрать проверку: ${scenarioActions[action]}`}
                      onClick={() => update({ actions: actions.filter((item) => item !== action) })}>
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
                  ) : (
                    <a href={cbrCalendarUrl} target="_blank" rel="noopener noreferrer">Календарь решений по ключевой ставке</a>
                  )}
                </li>;
              })}
              {availableActions.length > 0 && <li className="studio-workflow-add" role="presentation">
                  <button className="studio-workflow-add-button" type="button" aria-expanded={showActions}
                    onClick={() => setShowActions(!showActions)}>
                    <Plus size={16} aria-hidden="true" /> Добавить действие
                  </button>
                  {showActions && <div className="studio-workflow-options">
                    {availableActions.map((action) => <button type="button" key={action} onClick={() => {
                      update({ actions: [...actions, action] });
                      setShowActions(false);
                    }}>{scenarioActions[action]}</button>)}
                  </div>}
              </li>}
              <li className="studio-workflow-card studio-workflow-report">
                <header>
                  <span className="studio-workflow-index">{actions.length + 1}</span>
                  <h4>Отчёт в AI Штурмане</h4>
                  <LockKeyhole size={16} aria-label="Всегда последний" role="img" />
                </header>
                <div className="studio-field">
                  <span>Формат отчёта</span>
                  <SpringDropdown floating label="Формат отчёта" options={reportOptions}
                    value={draft.depth} onChange={(depth) => update({ depth })} />
                </div>
                <div className="studio-field">
                  <span>Уведомления</span>
                  <SpringDropdown floating label="Уведомления" options={notificationOptions}
                    value={draft.notification} onChange={(notification) => update({ notification })} />
                </div>
                <label className="studio-field">На чём сделать акцент
                  <textarea value={draft.instructions} rows={2} maxLength={1000}
                    placeholder="Например, сравни движение бумаги с IMOEX"
                    onChange={(event) => update({ instructions: event.target.value })} />
                </label>
              </li>
            </ol>
          </>
        )}
        {error && <p className="studio-error" role="alert">{error}</p>}
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
      </form>
    </div>
  );
}
