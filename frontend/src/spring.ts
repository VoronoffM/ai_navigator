export function spring(value: number, stiffness: number, damping: number) {
  return { value, target: value, velocity: 0, stiffness, damping };
}

type Spring = ReturnType<typeof spring>;

export function advance(spring: Spring, dt: number) {
  const acceleration = spring.stiffness * (spring.target - spring.value) - spring.damping * spring.velocity;
  spring.velocity += acceleration * dt;
  spring.value += spring.velocity * dt;
}

export function settled({ value, target, velocity }: Spring) {
  return Math.abs(value - target) < 0.001 && Math.abs(velocity) < 0.01;
}

export function clamp(value: number) {
  return Math.min(1, Math.max(0, value));
}
