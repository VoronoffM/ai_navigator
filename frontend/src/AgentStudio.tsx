import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Activity, ArrowLeft, ArrowRight, ChartNoAxesColumnIncreasing, Check, Newspaper, Plus, Settings2 } from 'lucide-react';
import type { AnalysisConfig, CheckName, Profile } from './analysis';
import { symbols, type Ticker } from './market';
import { describeTrigger, draftFrom, readScenarios, storageKey, templates, type Scenario, type ScenarioSettings, type Trigger } from './scenarios';

const templateIcons = { price: Activity, news: Newspaper, volume: ChartNoAxesColumnIncreasing };
const triggers = ['price', 'news', 'volume'] as const;
const steps = [
  { label: 'Trigger', title: 'Условие срабатывания' },
  { label: 'Analysis', title: 'AI-анализ' },
  { label: 'Action', title: 'Уведомления' },
] as const;

function loadScenarios() {
  try {
    return { items: readScenarios(), issue: '' };
  } catch {
    return { items: [], issue: 'Не удалось прочитать настройки из хранилища браузера.' };
  }
}

export function AgentStudio({ visible, analysisConfig, analysisConfigFailed, profile, onProfileChange }: {
  visible: boolean;
  analysisConfig?: AnalysisConfig;
  analysisConfigFailed: boolean;
  profile: Profile;
  onProfileChange: (profile: Profile) => void;
}) {
  const [saved, setSaved] = useState(loadScenarios);
  const [editor, setEditor] = useState<{ settings: ScenarioSettings; id?: string }>();
  const [feedback, setFeedback] = useState('');
  const [profileError, setProfileError] = useState('');

  function updateProfile(next: Profile) {
    try {
      onProfileChange(next);
      setProfileError('');
    } catch {
      setProfileError('Профиль применён. Не удалось сохранить его в браузере.');
    }
  }
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    function sync(event: StorageEvent) {
      if (event.key === storageKey || event.key === null) setSaved(loadScenarios());
    }

    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  function persist(update: (items: Scenario[]) => Scenario[]) {
    try {
      const items = update(readScenarios());
      localStorage.setItem(storageKey, JSON.stringify(items));
      setSaved({ items, issue: '' });
      return true;
    } catch {
      setSaved((current) => ({ ...current, issue: 'Не удалось сохранить настройки в браузере.' }));
      return false;
    }
  }

  function saveScenario(settings: ScenarioSettings) {
    const editingId = editor?.id;
    const id = editingId ?? crypto.randomUUID();
    const success = persist((items) => {
      const current = items.find((item) => item.id === id);
      const scenario = { ...settings, id, enabled: current?.enabled ?? false };
      return current ? items.map((item) => item.id === id ? scenario : item) : [...items, scenario];
    });

    if (success) {
      setEditor(undefined);
      setFeedback(editingId ? 'Настройки сохранены.' : 'Сценарий сохранён.');
      heading.current?.focus();
    }
  }

  function openEditor(settings: ScenarioSettings, id?: string) {
    setFeedback('');
    setEditor({ settings, id });
  }

  function toggleScenario(scenario: Scenario) {
    setFeedback('');
    persist((items) => items.map((item) => item.id === scenario.id ? { ...item, enabled: !scenario.enabled } : item));
  }

  return (
    <main className="studio" hidden={!visible} aria-labelledby="studio-title">
      <header className="studio-header">
        <div>
          <h1 id="studio-title" ref={heading} tabIndex={-1}>Agent Studio</h1>
          <p>Настройте, какие события AI должен отслеживать и как их разбирать.</p>
        </div>
        {!editor && (
          <button className="button button-primary" type="button" onClick={() => openEditor(draftFrom())}>
            <Plus size={17} aria-hidden="true" /> Создать сценарий
          </button>
        )}
      </header>

      <section className="studio-analysis" aria-labelledby="analysis-profile-title">
        <h2 id="analysis-profile-title">Профиль исторического разбора</h2>
        {analysisConfig ? <>
          <label className="studio-field">Модель · {analysisConfig.provider}
            <select value={profile.model} onChange={(event) => updateProfile({ ...profile, model: event.target.value })}>
              {analysisConfig.models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </label>
          <fieldset className="studio-assets">
            <legend>Проверки</legend>
            <div className="studio-asset-options">
              {(Object.entries(analysisConfig.checks) as [CheckName, string][]).map(([name, label]) => (
                <label className="watch-chip" key={name}>
                  <input type="checkbox" checked={profile.checks?.includes(name) ?? false} onChange={(event) => {
                    const selected = profile.checks ?? [];
                    const checks = event.target.checked ? [...selected, name] : selected.filter((item) => item !== name);
                    updateProfile({ ...profile, checks });
                  }} />
                  <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>{label}
                </label>
              ))}
            </div>
          </fieldset>
          <p>Профиль применяется при следующем воспроизведении.</p>
          {profileError && <p className="studio-error" role="status">{profileError}</p>}
        </> : <p role="status">{analysisConfigFailed ? 'Настройки сервера недоступны.' : 'Загружаем настройки…'}</p>}
      </section>

      <p className="studio-notice">Сценарии ниже хранятся в этом браузере. Их можно редактировать и сохранять.</p>
      {saved.issue && <p className="studio-error" role="alert">{saved.issue}</p>}
      <span className="studio-feedback" role="status">{feedback}</span>

      <div className="studio-layout">
        {editor ? (
          <ScenarioEditor key={editor.id ?? 'new'} initial={editor.settings} editing={!!editor.id}
            onSave={saveScenario} onCancel={() => { setEditor(undefined); heading.current?.focus(); }} />
        ) : (
          <section aria-labelledby="my-scenarios-title">
            <h2 id="my-scenarios-title">Мои сценарии</h2>
            {saved.items.length === 0 ? (
              <p className="studio-empty">Сценариев пока нет. Создайте свой или выберите шаблон из библиотеки.</p>
            ) : (
              <ul className="studio-list">
                {saved.items.map((scenario) => (
                  <li className="studio-row" key={scenario.id}>
                    <div className="studio-row-copy">
                      <h3>{scenario.name}</h3>
                      <p>{scenario.assets.join(', ')} · {describeTrigger(scenario)}</p>
                    </div>
                    <div className="studio-row-controls">
                      <button className="studio-switch" type="button" role="switch" aria-checked={scenario.enabled}
                        aria-label={'Включение в настройках — ' + scenario.name} onClick={() => toggleScenario(scenario)}>
                        <span className="studio-switch-track" aria-hidden="true" />
                        <span aria-hidden="true">{scenario.enabled ? 'Включён локально' : 'Выключен'}</span>
                      </button>
                      <button className="icon-button" type="button" aria-label={'Настройки — ' + scenario.name}
                        title="Настройки" onClick={() => openEditor(scenario, scenario.id)}>
                        <Settings2 size={17} aria-hidden="true" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <aside className="studio-library" aria-labelledby="library-title">
          <h2 id="library-title">Библиотека сценариев</h2>
          <ul className="studio-list">
            {triggers.map((trigger) => {
              const template = templates[trigger];
              const Icon = templateIcons[trigger];
              return (
                <li key={trigger}>
                  <button className="studio-template" type="button" disabled={!!editor}
                    onClick={() => openEditor(draftFrom(trigger, true))}>
                    <span className="studio-template-icon"><Icon size={18} aria-hidden="true" /></span>
                    <span><strong>{template.title}</strong><small>{template.description}</small></span>
                    <ArrowRight size={16} aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>
      </div>
    </main>
  );
}

function ScenarioEditor({ initial, editing, onSave, onCancel }: {
  initial: ScenarioSettings; editing: boolean; onSave: (settings: ScenarioSettings) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');
  const stepHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    stepHeading.current?.focus();
  }, [step]);

  function update(change: Partial<ScenarioSettings>) {
    setDraft((current) => ({ ...current, ...change }));
    setError('');
  }

  function toggleAsset(ticker: Ticker) {
    update({ assets: draft.assets.includes(ticker) ? draft.assets.filter((item) => item !== ticker) : [...draft.assets, ticker] });
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
    onSave({ ...draft, name: draft.name.trim(), keywords: draft.keywords.trim(), instructions: draft.instructions.trim() });
  }

  return (
    <section className="studio-editor" aria-labelledby="editor-title">
      <h2 id="editor-title">{editing ? 'Настройки сценария' : 'Новый сценарий'}</h2>
      <ol className="studio-steps" aria-label="Этапы настройки" role="list">
        {steps.map(({ label }, index) => (
          <li key={label} aria-current={step === index ? 'step' : undefined} data-completed={index < step}>
            {index > 0 && <ArrowRight size={14} aria-hidden="true" />}{label}
          </li>
        ))}
      </ol>

      <form className="studio-form" onSubmit={next}>
        <h3 tabIndex={-1} ref={stepHeading}>{steps[step].title}</h3>
        {step === 0 && (
          <>
            <label className="studio-field">Название сценария
              <input value={draft.name} required maxLength={80} placeholder="Например, резкое движение GAZP"
                onChange={(event) => update({ name: event.target.value })} />
            </label>
            <fieldset className="studio-assets">
              <legend>Активы</legend>
              <div className="studio-asset-options">
                {symbols.map(({ ticker, name }) => (
                  <label className="watch-chip" key={ticker} title={name}>
                    <input type="checkbox" checked={draft.assets.includes(ticker)} onChange={() => toggleAsset(ticker)} />
                    <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>{ticker}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="studio-field">Тип события
              <select value={draft.trigger} onChange={(event) => {
                const trigger = event.target.value as Trigger;
                const { threshold, windowMinutes } = draftFrom(trigger);
                update({ trigger, threshold, windowMinutes });
              }}>
                {triggers.map((trigger) => <option value={trigger} key={trigger}>{templates[trigger].title}</option>)}
              </select>
            </label>
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
                <label className="studio-field">{draft.trigger === 'price' ? 'Изменение цены, %' : 'Объём к среднему, раз'}
                  <input type="number" required min={draft.trigger === 'price' ? 0.01 : 1.01} step="0.01" value={draft.threshold || ''}
                    onChange={(event) => update({ threshold: Number(event.target.value) })} />
                </label>
                <label className="studio-field">Период, мин
                  <input type="number" required min={1} step={1} value={draft.windowMinutes || ''}
                    onChange={(event) => update({ windowMinutes: Number(event.target.value) })} />
                </label>
              </div>
            )}
          </>
        )}
        {step === 1 && (
          <>
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
        {step === 2 && (
          <label className="studio-field">Канал уведомлений
            <select value={draft.notification} onChange={(event) => update({ notification: event.target.value as ScenarioSettings['notification'] })}>
              <option value="in-app">В AI Navigator</option><option value="none">Без уведомлений</option>
            </select>
          </label>
        )}
        {error && <p className="studio-error" role="alert">{error}</p>}
        <div className="studio-form-actions">
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
    </section>
  );
}
