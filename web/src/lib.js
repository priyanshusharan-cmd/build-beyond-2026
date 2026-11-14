export const AGENTS = ['hospital', 'water', 'telecom', 'emergency']

export const AGENT_META = {
  hospital: { label: 'Hospital', short: 'H', icon: 'cardiology', color: 'var(--hospital)', hex: '#D64B68' },
  water: { label: 'Water', short: 'W', icon: 'water_drop', color: 'var(--water)', hex: '#2B7FC4' },
  telecom: { label: 'Telecom', short: 'T', icon: 'cell_tower', color: 'var(--telecom)', hex: '#7552C8' },
  emergency: { label: 'Emergency', short: 'E', icon: 'emergency', color: 'var(--emergency)', hex: '#198F6A' },
}

export const STRATEGIES = {
  ours: { label: 'Negotiation', sub: 'Our agents bid against a market price', icon: 'handshake' },
  priority: { label: 'Static priority', sub: 'Hospital, then emergency, telecom, water', icon: 'format_list_numbered' },
  proportional: { label: 'Proportional', sub: 'Everyone cut by the same share', icon: 'pie_chart' },
  blind: { label: 'Blind grab', sub: 'Everyone takes full need; grid trips', icon: 'bolt' },
}

export const CASCADE_TEXT = {
  A: { title: 'Water pressure collapsed', body: 'Hospital cooling load rises 20% while pressure stays low.' },
  B: { title: 'Telecom went dark', body: 'Emergency response loses coordination: its damage counts 1.5×.' },
  OVERLOAD_TRIP: { title: 'Grid overload trip', body: 'Demand exceeded supply, so the grid tripped: −20% supply for 5 minutes.' },
}

export function chaosText(p) {
  const prm = p.params ?? {}
  switch (p.kind) {
    case 'kill_substation': return { title: 'Substation knocked out', body: `−${prm.mw ?? 30} MW for ${prm.duration ?? 30} minutes` }
    case 'icu_surge': return { title: 'ICU surge', body: `Hospital need +${prm.pct ?? 30}% for ${prm.duration ?? 30} minutes` }
    case 'burst_main': return { title: 'Water main burst', body: `Reservoir drains ${prm.drain_mult ?? 3}× faster for ${prm.duration ?? 30} minutes` }
    case 'scenario_shock': return { title: p.label, body: `${p.delta_mw} MW for ${p.duration} minutes (scripted)` }
    default: return { title: p.kind, body: '' }
  }
}

/** Plain-language reason for an agent's final bid. Deterministic template, written after the fact. */
export function bidReason(agent, row) {
  const g = row.grants[agent]
  const need = row.need[agent]
  const short = need - g
  if (!(need > 0)) return 'No load this minute.'
  if (short < 0.05) return agent === 'hospital' ? 'ICU load is critical, so I bid for all of it.' : 'Full need covered at this price.'
  if (agent === 'water' && row.reservoir > 0.35) return `Reservoir at ${pct(row.reservoir)} can carry me, so I bid less.`
  if (agent === 'telecom' && row.battery > 0.2) return `Battery at ${pct(row.battery)} covers the gap, so I step back.`
  if (agent === 'hospital') return 'Below 25% short, ICU damage stays low, so I can give a little.'
  return `Power is worth more to others at this price. I'm ${fmt(short)} MW short.`
}

export const API = '/api'

export async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json()
}

export function wsUrl(path) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${API}${path}`
}

export const hhmm = (tick) => `${String(Math.floor(tick / 60)).padStart(2, '0')}:${String(tick % 60).padStart(2, '0')}`
export const fmt = (n, d = 1) => (n == null || Number.isNaN(n) ? '–' : Number(n).toFixed(d))
export const pct = (x, d = 0) => (x == null || Number.isNaN(x) ? '–' : `${(x * 100).toFixed(d)}%`)

export function statusOf(row, agent) {
  if (row?.status?.[agent]) return row.status[agent]
  const p = row?.served_pct?.[agent] ?? 1
  return p >= 0.95 ? 'ok' : p >= 0.6 ? 'degraded' : 'down'
}
export const STATUS_TEXT = { ok: 'Running', degraded: 'Degraded', down: 'Down' }

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Tiny external store so hover on one chart can drive others without re-rendering them. */
export function createStore(initial) {
  let v = initial
  const subs = new Set()
  return {
    get: () => v,
    set: (n) => { if (n !== v) { v = n; subs.forEach((f) => f()) } },
    subscribe: (f) => { subs.add(f); return () => subs.delete(f) },
  }
}
