import { useLayoutEffect, useRef } from 'react';
import { Bot, Github, House, UserRound } from 'lucide-react';

const items = [
  { section: 'market', label: 'Home', Icon: House },
  { section: 'studio', label: 'Agent Studio', Icon: Bot },
  { section: null, label: 'GitHub', Icon: Github },
  { section: null, label: 'Profile', Icon: UserRound },
] as const;

type Section = NonNullable<(typeof items)[number]['section']>;

function spring(position: number, stiffness: number, damping: number) {
  return { position, target: position, velocity: 0, stiffness, damping };
}

type Spring = ReturnType<typeof spring>;

function step(state: Spring, dt: number) {
  const acceleration = state.stiffness * (state.target - state.position) - state.damping * state.velocity;
  state.velocity += acceleration * dt;
  state.position += state.velocity * dt;
}

function atRest(state: Spring) {
  return Math.abs(state.position - state.target) < 0.01 && Math.abs(state.velocity) < 0.05;
}

function settle(state: Spring) {
  state.position = state.target;
  state.velocity = 0;
}

function createMotion() {
  // Bottom Bar's component-specific values from DesignBookmark's bar.js.
  return {
    labels: items.map(() => spring(0, 300, 26)),
    icons: items.map(() => spring(1, 520, 14)),
    left: spring(0, 340, 28),
    width: spring(0, 340, 28),
  };
}

export function WorkspaceNav({ section, onChange }: { section: Section; onChange: (section: Section) => void }) {
  const nav = useRef<HTMLElement>(null);
  const highlight = useRef<HTMLSpanElement>(null);
  const motion = useRef<ReturnType<typeof createMotion> | null>(null);
  const previousSection = useRef<Section>(section);

  useLayoutEffect(() => {
    const initial = motion.current === null;
    const { labels, icons, left, width } = (motion.current ??= createMotion());
    const buttons = Array.from(nav.current!.querySelectorAll('button'));
    const activeIndex = items.findIndex((item) => item.section === section);
    const activeButton = buttons[activeIndex];
    const pill = highlight.current!;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const tabs = buttons.map((button, index) => ({
      label: button.querySelector<HTMLElement>('.workspace-nav-label')!,
      text: button.querySelector<HTMLElement>('.workspace-nav-label > span')!,
      icon: button.querySelector('svg')!,
      labelSpring: labels[index],
      iconSpring: icons[index],
      fullWidth: 0,
    }));
    const itemSprings = [...labels, ...icons];
    const allSprings = [...itemSprings, left, width];
    let frame = 0;
    let lastTime = 0;

    function measure() {
      tabs.forEach((tab, index) => {
        tab.fullWidth = tab.text.offsetWidth;
        tab.labelSpring.target = index === activeIndex ? tab.fullWidth : 0;
      });
    }

    function renderItems() {
      tabs.forEach(({ label, fullWidth, icon, labelSpring, iconSpring }) => {
        const size = Math.max(0, labelSpring.position);
        const progress = size / fullWidth;
        label.style.width = `${size.toFixed(2)}px`;
        label.style.opacity = Math.max(0, Math.min(1, progress * 1.4 - 0.4)).toFixed(3);
        icon.style.transform = `scale(${iconSpring.position.toFixed(4)})`;
      });
    }

    function measureHighlight() {
      left.target = activeButton.offsetLeft;
      width.target = activeButton.offsetWidth;
    }

    function renderHighlight() {
      pill.style.transform = `translateX(${left.position.toFixed(2)}px)`;
      pill.style.width = `${width.position.toFixed(2)}px`;
    }

    function snap() {
      cancelAnimationFrame(frame);
      frame = 0;
      itemSprings.forEach(settle);
      renderItems();
      measureHighlight();
      settle(left);
      settle(width);
      renderHighlight();
    }

    function tick(now: number) {
      const dt = Math.min((now - lastTime) / 1000, 1 / 30) / 4;
      lastTime = now;
      measureHighlight();
      for (let substep = 0; substep < 4; substep++) {
        allSprings.forEach((state) => step(state, dt));
      }

      if (allSprings.every(atRest)) {
        snap();
        return;
      }
      renderItems();
      renderHighlight();
      frame = requestAnimationFrame(tick);
    }

    function syncMotion() {
      measure();
      if (reducedMotion.matches) snap();
      else if (!frame) {
        lastTime = performance.now();
        frame = requestAnimationFrame(tick);
      }
    }

    measure();
    if (initial || reducedMotion.matches) snap();
    else if (previousSection.current !== section) {
      icons[activeIndex].position = 0.72;
      icons[activeIndex].velocity = 6;
      syncMotion();
    }
    previousSection.current = section;

    const resize = new ResizeObserver(syncMotion);
    tabs.forEach(({ text }) => resize.observe(text));
    reducedMotion.addEventListener('change', syncMotion);
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      reducedMotion.removeEventListener('change', syncMotion);
    };
  }, [section]);

  return (
    <nav className="workspace-nav" aria-label="Разделы AI Штурман" ref={nav}>
      <span className="workspace-nav-highlight" ref={highlight} aria-hidden="true" />
      {items.map(({ section: destination, label, Icon }) => (
        <button key={label} type="button" aria-label={label}
          aria-current={section === destination ? 'page' : undefined} disabled={destination === null}
          onClick={destination === null ? undefined : () => onChange(destination)}>
          <Icon size={20} strokeWidth={1.9} aria-hidden="true" />
          <span className="workspace-nav-label" aria-hidden="true"><span>{label}</span></span>
        </button>
      ))}
    </nav>
  );
}
