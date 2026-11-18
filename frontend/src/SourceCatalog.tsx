import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { Library } from 'lucide-react';

/** Keep the catalog in the top layer so it never resizes or clips the action card. */
export function SourceCatalog({ children }: { children: ReactNode }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const element = popover.current;
    if (!open || !element) return;
    function position() {
      const anchor = trigger.current?.getBoundingClientRect();
      if (!anchor || !element) return;
      const viewport = window.visualViewport;
      const left = viewport?.offsetLeft ?? 0, top = viewport?.offsetTop ?? 0;
      const width = viewport?.width ?? window.innerWidth, height = viewport?.height ?? window.innerHeight;
      element.style.maxHeight = `${Math.max(0, height - 24)}px`;
      const bounds = element.getBoundingClientRect();
      element.style.left = `${Math.max(left + 12, Math.min(anchor.right - bounds.width, left + width - bounds.width - 12))}px`;
      const below = anchor.bottom + 6;
      element.style.top = `${Math.max(top + 12, Math.min(below + bounds.height <= top + height - 12 ? below : anchor.top - bounds.height - 6, top + height - bounds.height - 12))}px`;
    }
    position();
    element.querySelector('button')?.focus({ preventScroll: true });
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    window.visualViewport?.addEventListener('resize', position);
    window.visualViewport?.addEventListener('scroll', position);
    return () => {
      window.removeEventListener('resize', position);
      window.removeEventListener('scroll', position, true);
      window.visualViewport?.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('scroll', position);
    };
  }, [open]);

  return <div className="studio-research-catalog">
    <button ref={trigger} type="button" className="studio-research-catalog-trigger"
      popoverTarget={id} aria-expanded={open} aria-controls={id}>
      <Library size={15} aria-hidden="true" /> Из каталога
    </button>
    <div ref={popover} id={id} popover="auto" className="studio-research-catalog-popover"
      aria-label="Каталог источников" onToggle={(event) => setOpen(event.newState === 'open')}
      onClick={(event) => {
        if (event.target instanceof Element && event.target.closest('button')) {
          popover.current?.hidePopover();
          trigger.current?.focus({ preventScroll: true });
        }
      }}>
      {children}
    </div>
  </div>;
}
