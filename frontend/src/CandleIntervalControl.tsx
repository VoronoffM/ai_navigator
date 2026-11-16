import { useLayoutEffect, useRef } from 'react';
import type { Interval } from './market';

const options = [{ value: '1h', label: 'Час' }, { value: '1d', label: 'День' }] as const;

type Props = { value: Interval; disabled: boolean; onChange: (value: Interval) => void };

export function CandleIntervalControl({ value, disabled, onChange }: Props) {
  const target = value === '1d' ? 1 : 0;
  const highlight = useRef<HTMLSpanElement>(null);
  const spring = useRef({ position: target, velocity: 0 });

  useLayoutEffect(() => {
    const element = highlight.current!;
    const motion = spring.current;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const segmentWidth = element.offsetWidth;
    // The DesignBookmark segmented control defines its position spring in seg.js.
    const stiffness = 300;
    const damping = 20;
    let frame: number;
    let last = performance.now();

    function render() {
      const stretch = Math.min(Math.abs(motion.velocity * segmentWidth) / 1400, 0.22);
      element.style.transform = `translateX(${motion.position * 100}%) scale(${1 + stretch}, ${1 - stretch * 0.5})`;
    }

    function settle() {
      motion.position = target;
      motion.velocity = 0;
      render();
    }

    function tick(now: number) {
      if (reducedMotion.matches) {
        settle();
        return;
      }

      const step = Math.min((now - last) / 1000, 1 / 30) / 4;
      last = now;
      for (let substep = 0; substep < 4; substep += 1) {
        const acceleration = stiffness * (target - motion.position) - damping * motion.velocity;
        motion.velocity += acceleration * step;
        motion.position += motion.velocity * step;
      }

      if (Math.abs(target - motion.position) < 0.001 && Math.abs(motion.velocity) < 0.01) {
        settle();
        return;
      }

      render();
      frame = requestAnimationFrame(tick);
    }

    if (reducedMotion.matches || !segmentWidth || (motion.position === target && motion.velocity === 0)) {
      settle();
      return;
    }

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);

  return (
    <div className="intervals" role="group" aria-label="Интервал свечей">
      <span ref={highlight} className="interval-highlight" aria-hidden="true" />
      {options.map((option) => (
        <button type="button" key={option.value} aria-pressed={option.value === value}
          disabled={disabled} onClick={() => onChange(option.value)}>{option.label}</button>
      ))}
    </div>
  );
}
