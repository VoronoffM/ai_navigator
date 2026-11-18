import { useEffect, useId, useRef, useState } from 'react';
import { Info } from 'lucide-react';

export function SourceInfo({ label = 'Об изучении источника', text = 'По ссылке читается одна страница. Для исторического сигнала нужна дата публикации; поиск по всему сайту пока недоступен.' }: { label?: string; text?: string }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const element = tooltip.current;
    if (!element || !open) return;
    element.showPopover();
    function position() {
      const anchor = trigger.current?.getBoundingClientRect();
      if (!anchor || !element) return;
      const bounds = element.getBoundingClientRect();
      const viewport = window.visualViewport;
      const left = viewport?.offsetLeft ?? 0, top = viewport?.offsetTop ?? 0;
      const width = viewport?.width ?? window.innerWidth, height = viewport?.height ?? window.innerHeight;
      element.style.left = `${Math.max(left + 12, Math.min(anchor.left, left + width - bounds.width - 12))}px`;
      const below = anchor.bottom + 8;
      element.style.top = `${Math.max(top + 12, Math.min(below + bounds.height <= top + height - 12 ? below : anchor.top - bounds.height - 8, top + height - bounds.height - 12))}px`;
    }
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !trigger.current?.contains(event.target) && !element?.contains(event.target)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); }
    }
    position();
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    window.visualViewport?.addEventListener('resize', position);
    window.visualViewport?.addEventListener('scroll', position);
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', escape, true);
    return () => {
      if (element.isConnected && element.matches(':popover-open')) element.hidePopover();
      window.removeEventListener('resize', position);
      window.removeEventListener('scroll', position, true);
      window.visualViewport?.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('scroll', position);
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('keydown', escape, true);
    };
  }, [open]);
  return <span className="studio-source-info" onPointerEnter={(event) => {
    if (event.pointerType === 'mouse') setOpen(true);
  }} onPointerLeave={(event) => {
    if (event.pointerType === 'mouse' && document.activeElement !== trigger.current) setOpen(false);
  }}>
    <button ref={trigger} type="button" className="studio-source-info-trigger" aria-label={label}
      aria-describedby={open ? id : undefined} aria-expanded={open}
      onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setOpen(true)}>
      <Info size={15} aria-hidden="true" />
    </button>
    <div id={id} ref={tooltip} popover="manual" role="tooltip" className="studio-source-tooltip">
      {text}
    </div>
  </span>;
}
