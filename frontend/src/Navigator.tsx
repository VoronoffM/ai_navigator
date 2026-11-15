import { useEffect, useState } from 'react';
import { Activity, ArrowDownRight, ArrowRight, Check, FlaskConical, Radar, ScanLine, Sparkles, Square } from 'lucide-react';
import { symbols, type Ticker } from './market';

const scenario = { drop: '2,4%', period: '60 минут', time: '14:35 МСК' };
const steps = ['Обнаружение', 'Проверка', 'Разбор'] as const;
type Stage = 'event' | 'checking' | 'ready';
type DemoEvent = { ticker: Ticker; stage: Stage };

export function Navigator() {
  const [selected, setSelected] = useState<Ticker[]>(['GAZP']);
  const [active, setActive] = useState(false);
  const [event, setEvent] = useState<DemoEvent>();

  useEffect(() => {
    if (!active || !event || event.stage === 'ready') return;
    const next: Stage = event.stage === 'event' ? 'checking' : 'ready';
    const timer = window.setTimeout(() => {
      setEvent((current) => current === event ? { ...event, stage: next } : current);
    }, event.stage === 'event' ? 850 : 2800);
    return () => window.clearTimeout(timer);
  }, [active, event]);

  function toggleTicker(ticker: Ticker) {
    setSelected((current) => current.includes(ticker)
      ? current.filter((item) => item !== ticker)
      : [...current, ticker]);
  }

  function toggleMonitoring() {
    if (active) setEvent(undefined);
    setActive(!active);
  }

  const pending = event?.stage === 'event' || event?.stage === 'checking';
  const stageIndex = event?.stage === 'ready' ? 2 : event?.stage === 'checking' ? 1 : 0;

  return (
    <aside className="navigator" aria-labelledby="navigator-title" data-active={active}>
      <div className="navigator-heading">
        <div className="navigator-symbol"><Radar size={21} aria-hidden="true" /></div>
        <div>
          <h2 id="navigator-title">AI Navigator</h2>
          <span className="monitor-status" role="status">
            <i aria-hidden="true" />{active ? 'Наблюдение активно' : 'Наблюдение выключено'}
          </span>
        </div>
        <span className="demo-badge"><FlaskConical size={14} aria-hidden="true" /> Демо</span>
      </div>

      <div className="monitoring">
        <div className="section-title">
          <h3 id="watchlist-title">Отслеживаемые активы</h3>
          <span className="figures">{selected.length} из {symbols.length}</span>
        </div>
        <div className="watch-options" role="group" aria-labelledby="watchlist-title">
          {symbols.map(({ ticker }) => {
            const checked = selected.includes(ticker);
            return (
              <label className="watch-chip" key={ticker}>
                <input type="checkbox" checked={checked} disabled={active} onChange={() => toggleTicker(ticker)} />
                <span className="checkbox" aria-hidden="true"><Check size={11} strokeWidth={2.5} /></span>
                {ticker}
              </label>
            );
          })}
        </div>
        {(active || selected.length === 0) && (
          <p className="watch-hint">{active ? 'Остановите наблюдение, чтобы изменить список.' : 'Выберите хотя бы одну бумагу.'}</p>
        )}
        <button type="button" className={active ? 'button button-stop' : 'button button-primary'}
          disabled={!active && selected.length === 0} onClick={toggleMonitoring}>
          {active ? <Square size={14} aria-hidden="true" /> : <Radar size={17} aria-hidden="true" />}
          {active ? 'Остановить наблюдение' : 'Включить наблюдение'}
        </button>
      </div>

      <div className="scenario">
        <section className="scenario-section" aria-labelledby="event-title">
          <h3 id="event-title">Обнаруженное событие</h3>
          <div aria-live="polite">
            {event ? (
              <article className="event-card" aria-label="Демо-событие">
                <div className="event-heading">
                  <span className="event-icon"><ArrowDownRight size={17} aria-hidden="true" /></span>
                  <div><strong>{event.ticker}</strong><span>За {scenario.period} · {scenario.time}</span></div>
                  <strong className="event-drop figures" aria-label={`Снижение на ${scenario.drop}`}>−{scenario.drop}</strong>
                </div>
              </article>
            ) : (
              <div className="demo-empty">
                <span className="empty-icon"><ScanLine size={17} aria-hidden="true" /></span>
                <div>
                  <strong>{active ? 'Ожидание демо-события' : 'Событий пока нет'}</strong>
                  <p>{active ? 'Запустите демо, чтобы разобрать условное снижение цены.' : 'Включите наблюдение, чтобы запустить демо.'}</p>
                </div>
              </div>
            )}
          </div>
          {active && (
            <button type="button" className="button demo-trigger" disabled={pending}
              onClick={() => setEvent({ ticker: selected[0], stage: 'event' })}>
              <Activity size={16} aria-hidden="true" /> Показать демо-событие <ArrowRight className="button-arrow" size={15} aria-hidden="true" />
            </button>
          )}
        </section>

        <section className="scenario-section process" aria-labelledby="process-title">
          <div className="section-title">
            <h3 id="process-title">Ход анализа</h3>
            <span className="process-status" role="status">
              {event?.stage === 'ready' ? 'Разбор готов'
                : event?.stage === 'checking' ? 'Контекст проверяется'
                  : event ? 'Событие выявлено' : 'Ожидание события'}
            </span>
          </div>
          <ol className="scenario-steps" role="list">
            {steps.map((step, index) => (
              <li key={step} data-reached={!!event && index <= stageIndex}
                aria-current={event && index === stageIndex ? 'step' : undefined}>
                <i aria-hidden="true" /><span>{step}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="insight" aria-labelledby="analysis-title" data-ready={event?.stage === 'ready'}>
          <h3 id="analysis-title"><Sparkles size={18} aria-hidden="true" /> AI Insight</h3>
          {event?.stage === 'ready' ? (
            <dl className="analysis-details">
              <div>
                <dt>Что произошло</dt>
                <dd className="figures">{event.ticker}: −{scenario.drop} за {scenario.period}.</dd>
              </div>
              <div>
                <dt>Возможное объяснение</dt>
                <dd>Перенос квартального отчёта мог усилить неопределённость.</dd>
              </div>
              <div>
                <dt>Что подтверждено в демо</dt>
                <dd>Эмитент сообщил о переносе в 14:10 МСК. Цена снизилась.</dd>
              </div>
              <div>
                <dt>Что остаётся гипотезой</dt>
                <dd>Влияние сообщения на котировку.</dd>
              </div>
            </dl>
          ) : (
            <p className="insight-placeholder">Результат появится после проверки контекста.</p>
          )}
        </section>
      </div>
    </aside>
  );
}
