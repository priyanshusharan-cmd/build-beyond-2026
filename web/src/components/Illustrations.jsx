// Subtle gradient illustrations. Colours come from CSS tokens (via style) so they follow the theme.
const v = (name) => ({ fill: `var(${name})` })
const stop = (name, o = 1) => ({ stopColor: `var(${name})`, stopOpacity: o })

const BUILDINGS = [
  [4, 46], [10, 30], [15, 58], [22, 40], [27, 66], [34, 36], [40, 52], [46, 28], [51, 60], [58, 44],
  [63, 70], [70, 34], [75, 50], [82, 62], [88, 38], [93, 54],
]

/** City skyline; lit windows track how much of the need is being met. */
export function Skyline({ lit = 1 }) {
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="xMaxYMax meet" aria-hidden="true">
      <defs>
        <radialGradient id="glow" cx="78%" cy="30%" r="40%">
          <stop offset="0%" style={stop('--illo-glow', 0.55)} />
          <stop offset="100%" style={stop('--illo-glow', 0)} />
        </radialGradient>
        <linearGradient id="bld" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" style={stop('--illo-a', 1)} />
          <stop offset="100%" style={stop('--illo-a', 0.35)} />
        </linearGradient>
      </defs>
      <rect width="100" height="40" fill="url(#glow)" />
      <path d="M30 14 Q 55 22 80 14" fill="none" style={{ stroke: 'var(--ink-3)' }} strokeOpacity=".35" strokeWidth=".25" />
      <path d="M30 16 Q 55 24 80 16" fill="none" style={{ stroke: 'var(--ink-3)' }} strokeOpacity=".25" strokeWidth=".25" />
      {[30, 80].map((x) => <path key={x} d={`M${x} 40 L${x} 12 M${x - 2} 14 L${x + 2} 14`} style={{ stroke: 'var(--ink-3)' }} strokeOpacity=".35" strokeWidth=".4" />)}
      {BUILDINGS.map(([x, h], i) => {
        const w = 4.2, y = 40 - h * 0.4
        const wins = Math.floor(h / 14)
        return (
          <g key={i} opacity={i % 2 ? 0.75 : 1}>
            <rect x={x - w / 2 + 30 * 0} y={y} width={w} height={40 - y} rx=".6" fill="url(#bld)" />
            {Array.from({ length: wins }, (_, k) => {
              const on = ((i * 7 + k * 3) % 10) / 10 < lit
              return <rect key={k} x={x - 0.6} y={y + 2 + k * 4} width="1.2" height="1.4" rx=".2" style={v('--illo-glow')} opacity={on ? 0.8 : 0.08} />
            })}
          </g>
        )
      })}
    </svg>
  )
}

export function ChatIllo() {
  return (
    <svg viewBox="0 0 160 100" aria-hidden="true">
      <defs>
        <linearGradient id="b1" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" style={stop('--illo-a')} /><stop offset="100%" style={stop('--illo-b')} /></linearGradient>
        <linearGradient id="b2" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" style={stop('--illo-glow', 0.7)} /><stop offset="100%" style={stop('--illo-glow', 0.25)} /></linearGradient>
      </defs>
      <rect x="10" y="14" width="88" height="40" rx="16" fill="url(#b1)" />
      <path d="M26 54 l-6 12 l16 -12z" fill="url(#b1)" />
      <rect x="62" y="48" width="88" height="38" rx="16" fill="url(#b2)" />
      <path d="M134 86 l6 10 l-16 -10z" fill="url(#b2)" />
      {[28, 44, 60].map((x) => <circle key={x} cx={x} cy="34" r="4" style={v('--ink-3')} opacity=".35" />)}
      <path d="M84 67 h44" style={{ stroke: 'var(--ink-3)' }} strokeOpacity=".35" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}
