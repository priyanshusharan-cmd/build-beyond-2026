// Small illustrated avatars, one per speaker. Pure SVG, colour from the agent palette.
const S = { width: 32, height: 32, viewBox: '0 0 32 32', 'aria-hidden': true }

const shapes = {
  hospital: (c) => (
    <>
      <rect x="7" y="9" width="18" height="17" rx="2" fill={c} />
      <rect x="13" y="20" width="6" height="6" fill="#fff" opacity=".85" />
      <rect x="14.5" y="11" width="3" height="8" rx="1" fill="#fff" />
      <rect x="12" y="13.5" width="8" height="3" rx="1" fill="#fff" />
    </>
  ),
  water: (c) => (
    <>
      <rect x="8" y="6" width="16" height="10" rx="3" fill={c} />
      <path d="M16 8.5c1.6 2 2.4 3.2 2.4 4.2a2.4 2.4 0 0 1-4.8 0c0-1 .8-2.2 2.4-4.2z" fill="#fff" />
      <path d="M11 16l-2 10M21 16l2 10M10 21h12" stroke={c} strokeWidth="2" strokeLinecap="round" />
    </>
  ),
  telecom: (c) => (
    <>
      <path d="M16 12l-5 14M16 12l5 14M12.5 21h7" stroke={c} strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="16" cy="10" r="2.6" fill={c} />
      <path d="M10.5 5.5a8 8 0 0 0 0 9M21.5 5.5a8 8 0 0 1 0 9" stroke={c} strokeWidth="1.8" fill="none" strokeLinecap="round" />
    </>
  ),
  emergency: (c) => (
    <>
      <path d="M5 13h13l4 4h5v6H5z" fill={c} />
      <rect x="9" y="9" width="5" height="4" rx="1" fill="#E5484D" />
      <rect x="10.2" y="15" width="1.6" height="5" fill="#fff" />
      <rect x="8.5" y="16.7" width="5" height="1.6" fill="#fff" />
      <circle cx="10" cy="24" r="2.4" fill="#2B3440" /><circle cx="22" cy="24" r="2.4" fill="#2B3440" />
    </>
  ),
  market: (c) => (
    <>
      <circle cx="16" cy="16" r="9" fill="none" stroke={c} strokeWidth="2" />
      <path d="M16 10v6l4 3" stroke={c} strokeWidth="2" strokeLinecap="round" fill="none" />
    </>
  ),
  ledger: (c) => (
    <>
      <rect x="8" y="6" width="16" height="20" rx="2" fill="none" stroke={c} strokeWidth="2" />
      <path d="M12 16l3 3 5-6" stroke={c} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </>
  ),
  chaos: (c) => <path d="M18 4L8 18h7l-2 10 11-15h-7z" fill={c} />,
}

export const SPEAKERS = {
  hospital: { name: 'Hospital', color: '#D64B68', soft: '#FBE7EB' },
  water: { name: 'Water', color: '#2B7FC4', soft: '#E1EEFA' },
  telecom: { name: 'Telecom', color: '#7552C8', soft: '#EDE6FA' },
  emergency: { name: 'Emergency', color: '#198F6A', soft: '#DDF3EA' },
  market: { name: 'Market clock', color: '#5B6472', soft: '#EEF0F3' },
  ledger: { name: 'Ledger', color: '#5B6472', soft: '#EEF0F3' },
  chaos: { name: 'Disaster', color: '#C62F3B', soft: '#FCE4E5' },
}

export function Avatar({ who, size = 32 }) {
  const s = SPEAKERS[who] ?? SPEAKERS.market
  return (
    <span className="avatar" style={{ width: size + 8, height: size + 8, background: `linear-gradient(145deg, color-mix(in srgb, ${s.color} 22%, transparent), color-mix(in srgb, ${s.color} 8%, transparent))` }}>
      <svg {...S} width={size} height={size}>{(shapes[who] ?? shapes.market)(s.color)}</svg>
    </span>
  )
}
