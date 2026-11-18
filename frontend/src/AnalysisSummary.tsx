import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Info, Sparkles } from 'lucide-react';
import { advance, clamp, settled, spring } from './spring';
import type { AgentPalette } from './studioSettings';

type AnalysisSummaryProps = {
  title: string;
  summary: string;
  reason: string | null;
  agentName?: string;
  palette?: AgentPalette;
  activity: ReactNode;
  children: ReactNode;
  disclaimer?: string;
};

export function AnalysisSummary({ title, summary, reason, agentName, palette, activity, children, disclaimer }: AnalysisSummaryProps) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const card = useRef<HTMLDivElement>(null);
  // Profile Card uses its own spring pairs in profile.js, alongside the shared presets.
  const motion = useRef({ button: spring(0, 300, 22), badge: spring(1, 520, 14), started: false });

  useLayoutEffect(() => {
    const element = card.current!;
    const { button, badge } = motion.current;
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let previousTime = 0;

    button.target = Number(expanded);
    if (!motion.current.started || expanded) badge.velocity = 4;
    motion.current.started = true;

    function render() {
      element.style.setProperty('--analysis-morph', String(clamp(button.value)));
      element.style.setProperty('--analysis-badge-scale', String(badge.value));
    }

    function tick(time: number) {
      const dt = Math.min((time - previousTime) / 1000, 1 / 30);
      previousTime = time;
      for (let step = 0; step < 4; step++) {
        advance(button, dt / 4);
        advance(badge, dt / 4);
      }
      if (settled(button) && settled(badge)) {
        snap();
        return;
      }
      render();
      frame = requestAnimationFrame(tick);
    }

    function snap() {
      button.value = button.target;
      button.velocity = 0;
      badge.value = badge.target;
      badge.velocity = 0;
      render();
    }

    function syncMotion() {
      cancelAnimationFrame(frame);
      if (reducedMotion.matches) {
        snap();
        return;
      }
      previousTime = performance.now();
      frame = requestAnimationFrame(tick);
    }

    syncMotion();
    reducedMotion.addEventListener('change', syncMotion);
    return () => {
      cancelAnimationFrame(frame);
      reducedMotion.removeEventListener('change', syncMotion);
    };
  }, [expanded]);

  return (
    <div className="event-report-summary" ref={card}>
      <div className="event-report-heading">
        <span className="event-report-badge agent-gradient" data-palette={palette} aria-hidden="true">
          <Sparkles size={20} />
        </span>
        <div>
          <h4>{title}</h4>
          {agentName && <span className="event-report-agent">{agentName}</span>}
        </div>
      </div>
      <p>{summary}</p>
      {reason && <small className="event-report-note">{reason}</small>}
      {children && <button className="event-report-toggle" type="button"
        aria-label={expanded ? 'Свернуть детали' : 'Детали анализа'}
        aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpanded(!expanded)}>
        <span aria-hidden="true">Детали анализа</span>
        <span aria-hidden="true">Свернуть детали</span>
      </button>}
      {children && <div className="event-report-details" id={detailsId} hidden={!expanded}>{children}</div>}
      {activity}
      {disclaimer && <small className="event-report-disclaimer">
        <Info size={12} aria-hidden="true" />
        <span>{disclaimer}</span>
      </small>}
    </div>
  );
}
