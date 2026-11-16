import { useId, useLayoutEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';
import { advance, clamp, settled, spring } from './spring';
import './springDropdown.css';

const rowHeight = 44;
const padding = 6;

export function SpringDropdown<T extends string>({
  options, value, onChange, label, floating = false, preserveDialogPosition = false,
}: {
  options: readonly { value: T; label: string; disabled?: boolean }[];
  value: T;
  onChange?: (value: T) => void;
  label: string;
  floating?: boolean;
  preserveDialogPosition?: boolean;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const scrollBeforeChoice = useRef<number | undefined>(undefined);
  const current = useRef({ value, onChange });
  useLayoutEffect(() => {
    current.current = { value, onChange };
    const scrollTop = scrollBeforeChoice.current;
    scrollBeforeChoice.current = undefined;
    const dialog = root.current?.closest('dialog');
    if (scrollTop === undefined || !dialog) return;

    // A shorter form can reduce the scroll range when switching models.
    dialog.style.removeProperty('--signal-scroll-room');
    const missingRoom = scrollTop - (dialog.scrollHeight - dialog.clientHeight);
    if (missingRoom > 0) dialog.style.setProperty('--signal-scroll-room', `${missingRoom}px`);
    if (dialog.scrollTop !== scrollTop) dialog.scrollTop = scrollTop;
  }, [value, onChange]);

  useLayoutEffect(() => {
    const element = root.current!;
    const dialog = element.closest('dialog');
    const trigger = element.querySelector('button')!;
    const menu = element.querySelector<HTMLElement>('[role="listbox"]')!;
    const highlight = element.querySelector<HTMLElement>('.signal-highlight')!;
    const chevron = element.querySelector<SVGElement>('.signal-chevron')!;
    const slots = Array.from(element.querySelectorAll<HTMLElement>('.signal-slot'));
    const rows = Array.from(menu.querySelectorAll<HTMLElement>('[role="option"]')).map((row, index) => ({
      row, check: row.querySelector('path')!, entry: spring(0, 300, 24),
      tick: spring(Number(options[index].value === current.current.value), 260, 26),
    }));
    // DesignBookmark's dropdown uses local spring settings alongside the shared soft and lead presets.
    const height = spring(0, 300, 23);
    const rotation = spring(0, 300, 18);
    const opacity = spring(0, 400, 34);
    const press = spring(1, 500, 18);
    const roll = spring(1, 340, 26);
    const top = spring(padding, 620, 36);
    const bottom = spring(padding + rowHeight, 620, 36);
    const highlightOpacity = spring(0, 400, 32);
    const springs = [height, rotation, opacity, press, roll, top, bottom, highlightOpacity,
      ...rows.flatMap(({ entry, tick }) => [entry, tick])];
    const menuHeight = padding * 2 + rows.length * rowHeight;
    let availableHeight = menuHeight;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const timers = new Set<number>();
    let rowTimers: number[] = [];
    let closeTimer = 0;
    let open = false;
    let selected = options.findIndex(({ value }) => value === current.current.value);
    let active = -1;
    let revealActive = false;
    let front = 0;
    let frame = 0;
    let previous = 0;

    function paint() {
      trigger.style.transform = `scale(${press.value})`;
      chevron.style.transform = `rotate(${180 * rotation.value}deg)`;
      menu.style.height = `${Math.max(0, Math.min(height.value, availableHeight))}px`;
      menu.style.visibility = height.value < 1 ? 'hidden' : 'visible';
      menu.style.opacity = String(clamp(opacity.value));
      menu.style.transform = `scaleX(${.9 + .1 * Math.min(1.06, Math.max(0, height.value / availableHeight))})`;
      const highlightTop = Math.max(padding, Math.min(top.value, bottom.value - 16, menuHeight - padding - 16));
      const highlightBottom = Math.min(menuHeight - padding, Math.max(bottom.value, highlightTop + 16));
      highlight.style.height = `${highlightBottom - highlightTop}px`;
      highlight.style.transform = `translateY(${highlightTop}px)`;
      highlight.style.opacity = String(clamp(highlightOpacity.value) * clamp(opacity.value));
      rows.forEach(({ row, check, entry, tick }) => {
        row.style.opacity = String(clamp(entry.value));
        row.style.transform = `translateY(${(entry.value - 1) * 14}px)`;
        check.style.strokeDashoffset = String(1 - clamp(tick.value));
      });
      if (floating && revealActive && height.value >= availableHeight - 1 && rows[active]) {
        const start = padding + active * rowHeight;
        const end = start + rowHeight + padding;
        menu.scrollTop = Math.max(end - menu.clientHeight, Math.min(menu.scrollTop, start - padding));
        revealActive = false;
      }
      if (floating && !open && height.value < 1 && menu.matches(':popover-open')) menu.hidePopover();
      slots[front].style.opacity = String(clamp(roll.value));
      slots[front].style.transform = `translateY(${(1 - roll.value) * 20}px)`;
      slots[front ^ 1].style.opacity = String(clamp(1 - roll.value));
      slots[front ^ 1].style.transform = `translateY(${-roll.value * 20}px)`;
    }

    function animate(now: number) {
      frame = 0;
      const dt = Math.min((now - previous) / 1000, 1 / 30);
      previous = now;
      for (const motion of springs) {
        if (reduced.matches || settled(motion)) {
          motion.value = motion.target;
          motion.velocity = 0;
        } else {
          for (let step = 0; step < 4; step++) advance(motion, dt / 4);
        }
      }
      paint();
      if (springs.some((motion) => !settled(motion))) frame = requestAnimationFrame(animate);
    }

    function run() {
      if (frame) return;
      previous = performance.now();
      if (reduced.matches) animate(previous);
      else frame = requestAnimationFrame(animate);
    }

    function later(delay: number, action: () => void) {
      if (reduced.matches) { action(); return 0; }
      const timer = window.setTimeout(() => { timers.delete(timer); action(); }, delay);
      timers.add(timer);
      return timer;
    }

    function cancel(timer: number) {
      clearTimeout(timer);
      timers.delete(timer);
    }

    function highlightRow(index: number, snap = false) {
      if (index === active || !rows[index] || options[index].disabled) return;
      top.target = padding + index * rowHeight;
      bottom.target = top.target + rowHeight;
      if (snap) {
        top.value = top.target;
        bottom.value = bottom.target;
        top.velocity = bottom.velocity = 0;
      } else {
        const [lead, trail] = index > active ? [bottom, top] : [top, bottom];
        Object.assign(lead, { stiffness: 620, damping: 36 });
        Object.assign(trail, { stiffness: 200, damping: 20 });
      }
      active = index;
      highlightOpacity.target = 1;
      trigger.setAttribute('aria-activedescendant', rows[index].row.id);
      run();
    }

    function positionMenu() {
      const anchor = element.getBoundingClientRect();
      const top = anchor.bottom + 7;
      availableHeight = Math.min(menuHeight, Math.max(rowHeight + 2 * padding, window.innerHeight - top - 8));
      menu.style.top = `${top}px`;
      menu.style.left = `${anchor.left}px`;
      menu.style.width = `${anchor.width}px`;
      menu.style.overflowY = availableHeight < menuHeight ? 'auto' : 'hidden';
      height.target = open ? availableHeight : 0;
    }

    function setOpen(next: boolean) {
      cancel(closeTimer);
      if (open === next) return;
      open = next;
      trigger.setAttribute('aria-expanded', String(open));
      menu.setAttribute('aria-hidden', String(!open));
      menu.style.pointerEvents = open ? 'auto' : 'none';
      height.target = open ? menuHeight : 0;
      if (floating && open) {
        positionMenu();
        menu.showPopover();
        menu.scrollTop = 0;
        revealActive = true;
      }
      rotation.target = opacity.target = Number(open);
      rowTimers.forEach(cancel);
      rowTimers = rows.map(({ entry }, index) => later(open ? 50 + index * 45 : (rows.length - 1 - index) * 20, () => {
        entry.target = Number(open);
        run();
      }));
      if (open) highlightRow(selected, true);
      else {
        active = -1;
        highlightOpacity.target = 0;
        trigger.removeAttribute('aria-activedescendant');
      }
      run();
    }

    function fillSlot(slot: HTMLElement, index: number) {
      slot.lastElementChild!.textContent = options[index]?.label ?? '';
    }

    function anchorDialog() {
      if (!dialog) return;
      dialog.style.removeProperty('--signal-dialog-top');
      dialog.style.setProperty('--signal-dialog-top', `${dialog.getBoundingClientRect().top}px`);
    }

    function choose(index: number) {
      if (!options[index] || options[index].disabled) return;
      if (index !== selected) {
        // Fields or hints can change the dialog height. Keep its top edge in place.
        if (preserveDialogPosition) {
          if (!dialog?.style.getPropertyValue('--signal-dialog-top')) anchorDialog();
          scrollBeforeChoice.current = dialog?.scrollTop;
        }
        selected = index;
        front ^= 1;
        fillSlot(slots[front], index);
        roll.value = roll.velocity = 0;
        current.current.onChange?.(options[index].value);
      }
      rows.forEach(({ tick }, row) => { tick.target = Number(row === index); });
      press.value = .955;
      cancel(closeTimer);
      closeTimer = later(240, () => setOpen(false));
      run();
    }

    const listeners = new AbortController();
    const eventOptions = { signal: listeners.signal };
    function reposition() {
      if (!floating || !open) return;
      positionMenu();
      run();
    }
    const observer = floating ? new ResizeObserver(reposition) : undefined;
    if (observer && dialog) observer.observe(dialog);
    if (floating) (dialog ?? window).addEventListener('scroll', reposition, eventOptions);
    window.addEventListener('resize', () => {
      if (preserveDialogPosition) {
        dialog?.style.removeProperty('--signal-scroll-room');
        if (dialog?.style.getPropertyValue('--signal-dialog-top')) anchorDialog();
      }
      reposition();
    }, eventOptions);
    trigger.setAttribute('aria-expanded', 'false');
    trigger.removeAttribute('aria-activedescendant');
    menu.setAttribute('aria-hidden', 'true');
    fillSlot(slots[0], selected);
    menu.style.pointerEvents = 'none';
    paint();
    trigger.addEventListener('click', () => { press.value = .965; setOpen(!open); }, eventOptions);
    trigger.addEventListener('blur', () => setOpen(false), eventOptions);
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (!open) setOpen(true);
        else {
          const direction = event.key === 'ArrowDown' ? 1 : -1;
          let next = active + direction;
          while (options[next]?.disabled) next += direction;
          revealActive = true;
          highlightRow(next);
        }
      } else if (open && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        choose(active);
      } else if (open && event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
      }
    }, eventOptions);
    rows.forEach(({ row }, index) => {
      row.addEventListener('pointermove', () => { if (open) highlightRow(index); }, eventOptions);
      row.addEventListener('pointerdown', (event) => event.preventDefault(), eventOptions);
      row.addEventListener('click', () => { if (open) choose(index); }, eventOptions);
    });
    document.addEventListener('pointerdown', (event) => {
      if (!event.composedPath().includes(element)) setOpen(false);
    }, eventOptions);

    return () => {
      listeners.abort();
      observer?.disconnect();
      if (floating && menu.matches(':popover-open')) menu.hidePopover();
      if (preserveDialogPosition) {
        dialog?.style.removeProperty('--signal-dialog-top');
        dialog?.style.removeProperty('--signal-scroll-room');
      }
      timers.forEach(cancel);
      cancelAnimationFrame(frame);
    };
  }, [options, floating, preserveDialogPosition]);

  const selectedLabel = options.find((option) => option.value === value)?.label;
  return (
    <div className="signal-dropdown" ref={root}>
      <button className="signal-select" type="button" role="combobox" aria-haspopup="listbox"
        aria-expanded="false" aria-controls={id} aria-label={selectedLabel ? `${label}, ${selectedLabel}` : label}>
        <span className="signal-value" data-value={selectedLabel} aria-hidden="true">
          <span className="signal-slot"><b /></span>
          <span className="signal-slot"><b /></span>
        </span>
        <ChevronDown className="signal-chevron" size={20} aria-hidden="true" />
      </button>
      <div className="signal-options" id={id} role="listbox" aria-label={label} aria-hidden="true"
        popover={floating ? 'manual' : undefined}>
        <i className="signal-highlight" aria-hidden="true" />
        {options.map((option, index) => (
          <div className="signal-option" key={option.value} id={`${id}-${index}`} role="option"
            aria-selected={value === option.value} aria-disabled={option.disabled || undefined}>
            <b>{option.label}</b>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M5 12.5l4.5 4.5L19 7.5" pathLength="1" strokeDasharray="1" />
            </svg>
          </div>
        ))}
      </div>
    </div>
  );
}
