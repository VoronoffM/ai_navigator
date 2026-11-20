// Command button adapted from DesignBookmark (https://designbookmark.com/motion), MIT.
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import { AnimatePresence, motion, useMotionValue, useReducedMotion, useSpring } from 'motion/react';
import { Check, Search, X } from 'lucide-react';
import type { Scenario } from './scenarios';

const pressSpring = { stiffness: 520, damping: 34, mass: 0.6 };
const openSpring = { type: 'spring', stiffness: 300, damping: 28 } as const;
const swap = { duration: 0.18, ease: [0.23, 1, 0.32, 1] } as const;

export function AgentScenarioPicker({ scenarios, selectedIds, enabledIds, onChange, onToggle }: {
  scenarios: Scenario[];
  selectedIds: string[];
  enabledIds: string[];
  onToggle: (id: string) => void;
  onChange: (ids: string[]) => void;
}) {
  const allIds = scenarios.map(({ id }) => id);
  const root = useRef<HTMLFieldSetElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const restoreFocus = useRef(false);
  const listId = useId();
  const reducedMotion = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(-1);
  const pressTarget = useMotionValue(1);
  const scale = useSpring(pressTarget, pressSpring);
  const search = query.trim().toLocaleLowerCase('ru');
  const matches = scenarios.filter(({ name }) => name.toLocaleLowerCase('ru').includes(search));
  const options = search || !scenarios.length ? matches : [null, ...matches];
  const allSelected = allIds.length > 0 && allIds.every((id) => selectedIds.includes(id));
  const transition = reducedMotion ? { duration: 0 } : swap;
  const hiddenContent = { opacity: 0, filter: reducedMotion ? 'none' : 'blur(4px)' };
  const visibleContent = {
    opacity: 1,
    filter: 'none',
    transition: { ...transition, delay: reducedMotion ? 0 : 0.06 },
  };

  function close(focusTrigger = false) {
    restoreFocus.current = focusTrigger;
    setOpen(false);
    setQuery('');
    setActive(-1);
  }

  function shouldCloseOutside(target: EventTarget | null) {
    // Keep the layout stable until an outside button has handled its click.
    if (target instanceof Element && target.closest('button')) return false;
    return target instanceof Node && !root.current?.contains(target);
  }

  useLayoutEffect(() => {
    if (open) input.current?.focus({ preventScroll: true });
    else if (restoreFocus.current) {
      restoreFocus.current = false;
      trigger.current?.focus({ preventScroll: true });
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function closeOutside(event: PointerEvent) {
      if (shouldCloseOutside(event.target)) close();
    }
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [open]);

  function choose(id?: string) {
    if (!id) onChange(allSelected ? [] : allIds);
    else onChange(selectedIds.includes(id) ? selectedIds.filter((item) => item !== id) : [...selectedIds, id]);
  }

  function searchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      if (options[active] !== undefined) choose(options[active]?.id);
    }
    if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && options.length) {
      event.preventDefault();
      const next = event.key === 'ArrowDown' ? (active + 1) % options.length
        : active <= 0 ? options.length - 1 : active - 1;
      setActive(next);
      list.current?.children[next]?.scrollIntoView({ block: 'nearest' });
    }
  }

  return (
    <fieldset ref={root} className="studio-assets scenario-assets agent-scenario-search"
      onBlur={(event) => { if (open && shouldCloseOutside(event.relatedTarget)) close(); }}
      onKeyDown={(event) => {
        if (open && event.key === 'Escape' && !event.nativeEvent.isComposing) {
          event.preventDefault();
          event.stopPropagation();
          close(true);
        }
      }}>
      <legend className="studio-agent-field-label">Сценарии агента</legend>
      <motion.div className="asset-command" data-open={open} layout="size"
        transition={{ layout: reducedMotion ? { duration: 0 } : openSpring }}
        style={{ scale, borderRadius: 'var(--radius-card)' }}
        onPointerDown={() => { if (!open && !reducedMotion) pressTarget.set(0.97); }}
        onPointerUp={() => pressTarget.set(1)}
        onPointerCancel={() => pressTarget.set(1)}
        onPointerLeave={() => pressTarget.set(1)}>
        <AnimatePresence mode="popLayout" initial={false}>
          {open ? (
            <motion.div key="field" className="asset-command-field"
              initial={hiddenContent} animate={visibleContent} exit={{ ...hiddenContent, transition }}>
              <Search size={17} aria-hidden="true" />
              <input ref={input} value={query} placeholder="Введите название сценария"
                aria-label="Поиск сценариев" role="combobox" aria-autocomplete="list" aria-expanded={open}
                aria-controls={listId} aria-activedescendant={options[active] === undefined ? undefined : `${listId}-${active}`}
                autoComplete="off" onKeyDown={searchKeyDown}
                onChange={(event) => { setQuery(event.target.value); setActive(event.target.value.trim() ? 0 : -1); }} />
              {query && <button type="button" className="asset-command-clear" aria-label="Очистить поиск"
                onClick={() => { input.current?.focus(); setQuery(''); setActive(-1); }}>
                <X size={16} aria-hidden="true" />
              </button>}
              <button className="asset-command-key" type="button" aria-label="Закрыть поиск"
                onClick={() => close(true)}>Esc</button>
            </motion.div>
          ) : (
            <motion.button key="button" ref={trigger} type="button" className="asset-command-trigger"
              aria-expanded={open}
              initial={hiddenContent} animate={visibleContent} exit={{ ...hiddenContent, transition }}
              onClick={() => { pressTarget.set(1); setOpen(true); }}>
              <Search size={17} aria-hidden="true" /> Добавить сценарий
            </motion.button>
          )}
        </AnimatePresence>
      </motion.div>
      {open && (
        <motion.div className="asset-results" initial={reducedMotion ? false : { opacity: 0, y: -5 }}
          animate={{ opacity: 1, y: 0 }} transition={transition}>
          <ul ref={list} id={listId} role="listbox" aria-label="Доступные сценарии" aria-multiselectable="true">
            {options.map((symbol, index) => {
              const selected = symbol ? selectedIds.includes(symbol.id) : allSelected;
              return (
                <li key={symbol?.id ?? 'all'} role="option" id={`${listId}-${index}`}
                  aria-selected={selected} data-active={active === index} data-all-scenarios={!symbol}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => { choose(symbol?.id); input.current?.focus({ preventScroll: true }); }}>
                  <span className="asset-results-name">
                    <strong>{symbol?.name ?? 'Все сценарии'}</strong>
                  </span>
                  <span className="asset-results-check" aria-hidden="true">{selected && <Check size={17} />}</span>
                </li>
              );
            })}
          </ul>
          {!matches.length && <p role="status">{scenarios.length ? 'Сценарии не найдены' : 'Пока нет сохранённых сценариев'}</p>}
        </motion.div>
      )}
      {selectedIds.length > 0 && (
        <ul className="asset-selection" aria-label="Выбранные сценарии">
          {scenarios.filter(({ id }) => selectedIds.includes(id)).map(({ id, name }) => (
            <li key={id} className="agent-scenario-chip">
              <span className="agent-scenario-chip-name">{name}</span>
              <button type="button" className="studio-switch" role="switch"
                aria-checked={enabledIds.includes(id)} aria-label={`Сценарий «${name}»`}
                title={enabledIds.includes(id) ? 'Выключить сценарий' : 'Включить сценарий'}
                onClick={() => onToggle(id)} />
              <button className="agent-scenario-chip-remove" type="button" aria-label={`Убрать сценарий «${name}»`} onClick={() => choose(id)}>
                <X size={13} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}
