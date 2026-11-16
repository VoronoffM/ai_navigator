import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, Check } from 'lucide-react';
import { symbols, type Ticker } from './market';
import { defaultScenarioChecks, draftFrom, scenarioChecks, scenarioNotifications, templates, type ScenarioSettings, type Trigger } from './scenarios';
import { ScenarioProgress } from './ScenarioProgress';
import type { ExtraIntegration, StudioAgent } from './studioSettings';

const triggers = Object.keys(templates) as Trigger[];
const allAssets = symbols.map(({ ticker }) => ticker);
const steps = [
  { label: 'Активы', title: 'Выберите активы' },
  { label: 'Сигнал', title: 'Настройте модель срабатывания сигнала' },
  { label: 'Действия', title: 'Выберите действия агента' },
  { label: 'Агент', title: 'Назначьте агента и канал уведомлений' },
] as const;
const stepLabels = steps.map(({ label }) => label);

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

export function ScenarioEditor({ initial, agents, integrations, onSave, onCancel }: {
  initial: ScenarioSettings; agents: StudioAgent[]; integrations: ExtraIntegration[];
  onSave: (settings: ScenarioSettings) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const checks = draft.checks ?? defaultScenarioChecks;
  const integrationIds = draft.integrationIds ?? [];

  useEffect(() => {
    stepHeading.current?.focus({ preventScroll: true });
    stepHeading.current?.closest('dialog')?.scrollTo(0, 0);
  }, [step]);

  function update(change: Partial<ScenarioSettings>) {
    setDraft((current) => ({ ...current, ...change }));
    setError('');
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
    onSave({ ...draft, checks, name: draft.name.trim(), keywords: draft.keywords.trim(), instructions: draft.instructions.trim() });
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
            <div className="studio-field">
              <select aria-labelledby="scenario-step-title" value={draft.trigger} onChange={(event) => {
                const trigger = event.target.value as Trigger;
                const { threshold, windowMinutes } = draftFrom(trigger);
                update({ trigger, threshold, windowMinutes });
              }}>
                {triggers.map((trigger) => <option value={trigger} key={trigger}>{templates[trigger].title}</option>)}
              </select>
            </div>
            {draft.trigger === 'price' && (
              <label className="studio-field">Направление цены
                <select value={draft.direction} onChange={(event) => update({ direction: event.target.value as ScenarioSettings['direction'] })}>
                  <option value="either">Рост или падение</option><option value="up">Только рост</option><option value="down">Только падение</option>
                </select>
              </label>
            )}
            {draft.trigger === 'news' ? (
              <label className="studio-field">Ключевые слова через запятую
                <input value={draft.keywords} maxLength={200} placeholder="Любые новости, если оставить пустым"
                  onChange={(event) => update({ keywords: event.target.value })} />
              </label>
            ) : (
              <div className="studio-fields">
                <label className="studio-field">{draft.trigger === 'volume' ? 'Объём к среднему, раз' : draft.trigger === 'volatility' ? 'Размах цены, %' : 'Изменение цены, %'}
                  <input type="number" required min={draft.trigger === 'volume' ? 1.01 : 0.01} step="0.01" value={draft.threshold || ''}
                    onChange={(event) => update({ threshold: Number(event.target.value) })} />
                </label>
                <label className="studio-field">Период, мин
                  <input type="number" required min={1} step={1} value={draft.windowMinutes || ''}
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
            <fieldset className="studio-assets">
              <legend>Инструменты T-Invest MCP</legend>
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
            <fieldset className="studio-assets studio-extra-sources">
              <legend>Другие интеграции</legend>
              {integrations.length === 0 ? (
                <p>Добавьте источник в разделе «Интеграции», чтобы выбрать его здесь.</p>
              ) : (
                <>
                  <div className="studio-asset-options">
                    {integrations.map(({ id, name }) => (
                      <label className="watch-chip" key={id}>
                        <input type="checkbox" checked={integrationIds.includes(id)} onChange={() => update({
                          integrationIds: integrationIds.includes(id)
                            ? integrationIds.filter((item) => item !== id) : [...integrationIds, id],
                        })} />
                        <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>
                        <span>{name}</span>
                      </label>
                    ))}
                  </div>
                  <p>Подключения пока сохраняются как черновики.</p>
                </>
              )}
            </fieldset>
            <label className="studio-field">Глубина разбора
              <select value={draft.depth} onChange={(event) => update({ depth: event.target.value as ScenarioSettings['depth'] })}>
                <option value="brief">Краткая сводка</option>
                <option value="detailed">Подробный разбор</option>
              </select>
            </label>
            <label className="studio-field">Инструкции для AI
              <textarea value={draft.instructions} rows={4} maxLength={1000} placeholder="Что важно проверить в первую очередь?"
                onChange={(event) => update({ instructions: event.target.value })} />
            </label>
          </>
        )}
        {step === 3 && (
          <>
            <label className="studio-field">Назначить агенту
              <select value={draft.agentId ?? ''} onChange={(event) => update({ agentId: event.target.value || undefined })}>
                <option value="">Без агента</option>
                {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
              </select>
            </label>
            <label className="studio-field">Канал уведомлений
              <select value={draft.notification} onChange={(event) => update({ notification: event.target.value as ScenarioSettings['notification'] })}>
                {Object.entries(scenarioNotifications).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
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
