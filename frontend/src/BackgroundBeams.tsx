// Curve geometry from Aceternity UI's Background Beams.
// https://ui.aceternity.com/components/background-beams
const beamPath = 'M-380 -189C-380 -189 -312 216 152 343C616 470 684 875 684 875';
const beamOffsets = Array.from({ length: 50 }, (_, index) => `translate(${index * 7} ${index * -8})`);

const pulses = [
  { beam: 5, duration: '19s', delay: '-3s' },
  { beam: 12, duration: '22s', delay: '-13s' },
  { beam: 19, duration: '18s', delay: '-7s' },
  { beam: 26, duration: '21s', delay: '-16s' },
  { beam: 33, duration: '20s', delay: '-1s' },
  { beam: 41, duration: '23s', delay: '-10s' },
  { beam: 48, duration: '19s', delay: '-15s' },
];

export function BackgroundBeams() {
  return (
    <svg className="studio-background-beams" viewBox="0 0 696 316" preserveAspectRatio="xMidYMid slice"
      fill="none" aria-hidden="true" focusable="false">
      <g className="studio-beam-traces">
        {beamOffsets.map((offset) => (
          <path key={offset} d={beamPath} transform={offset} vectorEffect="non-scaling-stroke" />
        ))}
      </g>
      <g className="studio-beam-pulses">
        {pulses.map(({ beam, duration, delay }) => (
          <path key={beam} d={beamPath} transform={beamOffsets[beam]} pathLength="100"
            style={{ animationDuration: duration, animationDelay: delay }} />
        ))}
      </g>
    </svg>
  );
}
