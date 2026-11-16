import { useLayoutEffect, useRef, type CSSProperties } from 'react';

function spring(value: number, stiffness: number, damping: number) {
  return { value, target: value, velocity: 0, stiffness, damping };
}

type Spring = ReturnType<typeof spring>;

function advance(spring: Spring, dt: number) {
  const acceleration = spring.stiffness * (spring.target - spring.value) - spring.damping * spring.velocity;
  spring.velocity += acceleration * dt;
  spring.value += spring.velocity * dt;
}

function settled({ value, target, velocity }: Spring) {
  return Math.abs(value - target) < 0.001 && Math.abs(velocity) < 0.01;
}

function clamp(value: number) {
  return Math.min(1, Math.max(0, value));
}

export function ScenarioProgress({ labels, current }: { labels: readonly string[]; current: number }) {
  const root = useRef<HTMLOListElement>(null);
  // DesignBookmark Step Progress. Fill uses the shared soft spring.
  const motion = useRef({
    line: spring(0, 160, 22),
    dots: labels.map(() => ({
      fill: spring(0, 260, 24),
      check: spring(0, 140, 20),
      pop: spring(1, 500, 14),
      active: spring(0, 300, 26),
      delay: 0,
    })),
    current: -1,
  });

  useLayoutEffect(() => {
    const list = root.current!;
    const markers = list.querySelectorAll<HTMLElement>('.studio-progress-marker');
    const { line, dots } = motion.current;
    const springs = [line, ...dots.flatMap(({ fill, check, pop, active }) => [fill, check, pop, active])];
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let previousTime = 0;

    line.target = current / (dots.length - 1);
    dots.forEach(({ fill, active, check }, index) => {
      const done = index < current;
      if (done && fill.target === 0) dots[index].delay = 0.12;
      if (!done) {
        dots[index].delay = 0;
        check.target = 0;
      }
      fill.target = Number(done);
      active.target = Number(index === current);
    });
    if (motion.current.current !== current) {
      dots[current].pop.value = 0.7;
      dots[current].pop.velocity = 6;
      motion.current.current = current;
    }

    function render() {
      list.style.setProperty('--progress-filled', String(clamp(line.value)));
      dots.forEach(({ fill, check, pop, active }, index) => {
        const style = markers[index].style;
        style.setProperty('--step-filled', `${clamp(fill.value) * 100}%`);
        style.setProperty('--step-active', `${clamp(active.value) * 100}%`);
        style.setProperty('--step-number', String(1 - clamp(fill.value)));
        style.setProperty('--step-check-offset', String(1 - clamp(check.value)));
        style.setProperty('--step-scale', String(pop.value));
      });
    }

    function snap() {
      dots.forEach((dot) => {
        dot.check.target = dot.fill.target;
        dot.delay = 0;
      });
      springs.forEach((spring) => {
        spring.value = spring.target;
        spring.velocity = 0;
      });
      render();
    }

    function tick(time: number) {
      const dt = Math.min((time - previousTime) / 1000, 1 / 30);
      previousTime = time;
      dots.forEach((dot) => {
        if (dot.delay <= 0) return;
        dot.delay -= dt;
        if (dot.delay <= 0) dot.check.target = 1;
      });
      for (let substep = 0; substep < 4; substep++) {
        springs.forEach((spring) => advance(spring, dt / 4));
      }
      if (dots.every(({ delay }) => delay <= 0) && springs.every(settled)) {
        snap();
        return;
      }
      render();
      frame = requestAnimationFrame(tick);
    }

    function syncMotion() {
      cancelAnimationFrame(frame);
      if (reducedMotion.matches) {
        snap();
        return;
      }
      render();
      previousTime = performance.now();
      frame = requestAnimationFrame(tick);
    }

    syncMotion();
    reducedMotion.addEventListener('change', syncMotion);
    return () => {
      cancelAnimationFrame(frame);
      reducedMotion.removeEventListener('change', syncMotion);
    };
  }, [current]);

  return (
    <ol className="studio-progress" ref={root} aria-label="Этапы настройки сценария" role="list"
      style={{ '--progress-steps': labels.length } as CSSProperties}>
      {labels.map((label, index) => (
        <li key={label} aria-current={index === current ? 'step' : undefined} data-reached={index <= current}>
          <span className="studio-progress-marker" aria-hidden="true">
            <span>{index + 1}</span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
              <path d="M5 12.5l4.5 4.5L19 7.5" pathLength="1" />
            </svg>
          </span>
          <span>{label}</span>
        </li>
      ))}
    </ol>
  );
}
