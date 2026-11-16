import { Fragment, useEffect, useRef } from 'react';
import './weightWave.css';

const light = 300;
const bold = 820;
const spread = 0.13;

function spring(position: number, stiffness: number, damping: number) {
  return { position, target: position, velocity: 0, stiffness, damping };
}

function step(state: ReturnType<typeof spring>, seconds: number) {
  const acceleration = state.stiffness * (state.target - state.position) - state.damping * state.velocity;
  state.velocity += acceleration * seconds;
  state.position += state.velocity * seconds;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function WeightWave({ text, active }: { text: string; active: boolean }) {
  const wave = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const element = wave.current;
    if (!active || !element) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    // Weight Wave's component-specific settings from the reference wave.js.
    const focus = spring(-0.2, 150, 22);
    const letters = Array.from(element.querySelectorAll<HTMLElement>('.weight-wave-letter'), (letter) => ({
      letter,
      weight: spring(light, 260, 22),
    }));
    let frame = 0;
    let lastTime = 0;
    let sweepTime = 0;
    let pointing = false;

    const animate = (now: number) => {
      const dt = Math.min((now - lastTime) / 1000, 1 / 30) / 4;
      lastTime = now;

      for (let substep = 0; substep < 4; substep++) {
        if (!pointing) {
          sweepTime += dt;
          focus.target = -0.06 + 1.12 * (0.5 - 0.5 * Math.cos(sweepTime * 2 * Math.PI / 4.6));
        }
        step(focus, dt);
        letters.forEach(({ weight }) => step(weight, dt));
      }

      // Measure all letter positions before changing the font weights.
      const width = element.offsetWidth || 1;
      const centers = letters.map(({ letter }) => (letter.offsetLeft + letter.offsetWidth / 2) / width);
      letters.forEach(({ letter, weight }, index) => {
        const distance = (centers[index] - focus.position) / spread;
        weight.target = light + (bold - light) * Math.exp(-distance * distance);
        letter.style.fontWeight = clamp(weight.position, 100, 900).toFixed(1);
        letter.style.opacity = (0.42 + 0.58 * clamp((weight.position - light) / (bold - light), 0, 1)).toFixed(3);
      });

      frame = window.requestAnimationFrame(animate);
    };

    const followPointer = (event: PointerEvent) => {
      if (event.pointerType === 'touch') return;
      const bounds = element.getBoundingClientRect();
      pointing = true;
      focus.target = (event.clientX - bounds.left) / bounds.width;
    };

    function resumeSweep() {
      pointing = false;
      sweepTime = 0;
    }

    function stop() {
      window.cancelAnimationFrame(frame);
      letters.forEach(({ letter }) => {
        letter.style.removeProperty('font-weight');
        letter.style.removeProperty('opacity');
      });
    }

    function syncMotion() {
      stop();
      if (reducedMotion.matches) return;
      lastTime = performance.now();
      frame = window.requestAnimationFrame(animate);
    }

    element.addEventListener('pointermove', followPointer);
    element.addEventListener('pointerleave', resumeSweep);
    reducedMotion.addEventListener('change', syncMotion);
    syncMotion();

    return () => {
      stop();
      reducedMotion.removeEventListener('change', syncMotion);
      element.removeEventListener('pointermove', followPointer);
      element.removeEventListener('pointerleave', resumeSweep);
    };
  }, [active, text]);

  return (
    <span className="weight-wave" ref={wave} aria-hidden="true">
      {text.split(' ').map((word, index) => (
        <Fragment key={index}>
          {index > 0 && ' '}
          <span className="weight-wave-word">
            {Array.from(word, (letter, position) => (
              <span className="weight-wave-letter" key={position}>{letter}</span>
            ))}
          </span>
        </Fragment>
      ))}
    </span>
  );
}
