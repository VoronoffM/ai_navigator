// Command button adapted from DesignBookmark (https://designbookmark.com/motion), MIT.
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import { AnimatePresence, motion, useMotionValue, useReducedMotion, useSpring } from 'motion/react';
import { Check, Layers, Search, X } from 'lucide-react';
import { allSymbols as symbols, type Ticker } from './market';

const pressSpring = { stiffness: 520, damping: 34, mass: 0.6 };
const openSpring = { type: 'spring', stiffness: 300, damping: 28 } as const;
const swap = { duration: 0.18, ease: [0.23, 1, 0.32, 1] } as const;
const allAssets = symbols.map(({ ticker }) => ticker);
const shortcut = /Mac|iPhone|iPad|iPod/i.test(navigator.platform) ? '⌘K' : 'Ctrl K';

export function ScenarioAssets({ assets, onChange }: { assets: Ticker[]; onChange: (assets: Ticker[]) => void }) {
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
  const matches = symbols.filter(({ name, ticker }) =>
    ticker.toLowerCase().includes(search) || name.toLocaleLowerCase('ru').includes(search));
  const options = search ? matches : [null, ...matches];
  const allSelected = allAssets.every((ticker) => assets.includes(ticker));
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
    const dialog = root.current?.closest('dialog');
    function openWithShortcut(event: globalThis.KeyboardEvent) {
      const modifier = shortcut === '⌘K' ? event.metaKey : event.ctrlKey;
      if (!dialog?.open || !modifier || event.altKey || event.shiftKey || event.code !== 'KeyK') return;
      event.preventDefault();
      setOpen(true);
      input.current?.focus({ preventScroll: true });
    }
    dialog?.addEventListener('keydown', openWithShortcut);
    return () => dialog?.removeEventListener('keydown', openWithShortcut);
  }, []);

  useEffect(() => {
    if (!open) return;
    function closeOutside(event: PointerEvent) {
      if (shouldCloseOutside(event.target)) close();
    }
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [open]);

  function choose(ticker?: Ticker) {
    if (!ticker) onChange(allSelected ? [] : allAssets);
    else onChange(assets.includes(ticker) ? assets.filter((item) => item !== ticker) : [...assets, ticker]);
  }

  function searchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      if (options[active] !== undefined) choose(options[active]?.ticker);
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
    <fieldset ref={root} className="studio-assets scenario-assets"
      onBlur={(event) => { if (open && shouldCloseOutside(event.relatedTarget)) close(); }}
      onKeyDown={(event) => {
        if (open && event.key === 'Escape' && !event.nativeEvent.isComposing) {
          event.preventDefault();
          event.stopPropagation();
          close(true);
        }
      }}>
      <legend>Активы</legend>
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
              <input ref={input} value={query} placeholder="Введите тикер или название"
                aria-label="Поиск активов" role="combobox" aria-autocomplete="list" aria-expanded={open}
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
              aria-expanded={open} aria-keyshortcuts={shortcut === '⌘K' ? 'Meta+K' : 'Control+K'}
              initial={hiddenContent} animate={visibleContent} exit={{ ...hiddenContent, transition }}
              onClick={() => { pressTarget.set(1); setOpen(true); }}>
              <Search size={17} aria-hidden="true" /> Найти актив
              <kbd className="asset-command-key" aria-hidden="true">{shortcut}</kbd>
            </motion.button>
          )}
        </AnimatePresence>
      </motion.div>
      {open && (
        <motion.div className="asset-results" initial={reducedMotion ? false : { opacity: 0, y: -5 }}
          animate={{ opacity: 1, y: 0 }} transition={transition}>
          <ul ref={list} id={listId} role="listbox" aria-label="Доступные активы" aria-multiselectable="true">
            {options.map((symbol, index) => {
              const selected = symbol ? assets.includes(symbol.ticker) : allSelected;
              return (
                <li key={symbol?.ticker ?? 'all'} role="option" id={`${listId}-${index}`}
                  aria-selected={selected} data-active={active === index}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => { choose(symbol?.ticker); input.current?.focus({ preventScroll: true }); }}>
                  {symbol ? <img src={symbol.logo} alt="" width={32} height={32} />
                    : <span className="asset-results-icon"><Layers size={17} aria-hidden="true" /></span>}
                  <span className="asset-results-name">
                    <strong>{symbol?.ticker ?? 'Все активы'}</strong>
                    {symbol && <span>{symbol.name}</span>}
                  </span>
                  {symbol && <span className="asset-results-exchange" title={symbol.ticker === 'DEMO' ? 'Учебный инструмент' : 'Московская биржа'}>{symbol.ticker === 'DEMO' ? 'DEMO' : 'MOEX'}</span>}
                  <span className="asset-results-check" aria-hidden="true">{selected && <Check size={17} />}</span>
                </li>
              );
            })}
          </ul>
          {!matches.length && <p role="status">Активы не найдены</p>}
        </motion.div>
      )}
      <ul className="asset-selection" aria-label="Выбранные активы" aria-hidden={assets.length === 0 || undefined}>
        {assets.map((ticker) => (
          <li key={ticker}>
            <button type="button" aria-label={`Убрать ${ticker}`} onClick={() => choose(ticker)}>
              {ticker} <X size={13} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
