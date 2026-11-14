import { useEffect, useRef, useState } from 'react'
import { STRATEGIES, hhmm, prefersReducedMotion } from '../lib.js'

function Sheet({ title, sub, onClose, children }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!prefersReducedMotion()) el.animate([{ transform: 'scale(0.97)', opacity: 0.4 }, { transform: 'scale(1)', opacity: 1 }], { duration: 240, easing: 'cubic-bezier(0.05, 0.7, 0.1, 1)' })
    el.querySelector('button, input')?.focus()
    const key = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])
  return (
    <div className="scrim" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="glass sheet" ref={ref} role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        <p>{sub}</p>
        {children}
      </div>
    </div>
  )
}

export function RunSheet({ initial, onStart, onClose }) {
  const [strategy, setStrategy] = useState(initial.strategy)
  const [seed, setSeed] = useState(initial.seed)
  return (
    <Sheet title="New run" sub="Pick how power gets shared. The seed fixes the disaster, so every strategy can face the same one." onClose={onClose}>
      <div className="opt-grid" role="radiogroup" aria-label="Strategy">
        {Object.entries(STRATEGIES).map(([k, s]) => (
          <button key={k} className="opt" role="radio" aria-checked={strategy === k} onClick={() => setStrategy(k)}>
            <span className="ms" aria-hidden="true">{s.icon}</span>
            <span><b>{s.label}</b><small>{s.sub}</small></span>
          </button>
        ))}
      </div>
      <label className="field">Disaster seed
        <input type="number" min="0" inputMode="numeric" value={seed} onChange={(e) => setSeed(Math.max(0, parseInt(e.target.value || '0', 10)))} />
      </label>
      <div className="sheet-actions">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn filled" onClick={() => { onStart({ strategy, seed }); onClose() }}><span className="ms" aria-hidden="true">play_arrow</span>Start run</button>
      </div>
    </Sheet>
  )
}

const KINDS = [
  { kind: 'kill_substation', icon: 'electric_bolt', label: 'Knock out a substation', sub: 'Supply drops for a while', key: 'mw', field: 'Megawatts lost', min: 5, max: 50, step: 5, def: 30, unit: 'MW' },
  { kind: 'icu_surge', icon: 'ecg_heart', label: 'ICU surge', sub: 'Hospital needs more power', key: 'pct', field: 'Extra hospital need', min: 10, max: 80, step: 10, def: 40, unit: '%' },
  { kind: 'burst_main', icon: 'water_damage', label: 'Burst a water main', sub: 'Reservoir drains faster', key: 'drain_mult', field: 'Drain speed', min: 2, max: 6, step: 1, def: 3, unit: '×' },
]

export function ChaosSheet({ onInject, onClose, disabled }) {
  const [vals, setVals] = useState(() => Object.fromEntries(KINDS.map((k) => [k.kind, k.def])))
  const [duration, setDuration] = useState(30)
  const [busy, setBusy] = useState(null)
  const [msg, setMsg] = useState(null)
  const fire = async (k) => {
    setBusy(k.kind); setMsg(null)
    try {
      const r = await onInject(k.kind, { [k.key]: vals[k.kind], duration }, k)
      setMsg({ ok: true, text: `${k.label} hits now (${hhmm(r.queued.tick)} on the clock) for ${duration} min. Watch the chat.` })
    } catch (e) { setMsg({ ok: false, text: e.message }) } finally { setBusy(null) }
  }
  return (
    <Sheet title="Inject chaos" sub="Strike the live run. The agents have to renegotiate from the next minute." onClose={onClose}>
      <label className="field"><span className="field-row"><span>Lasts</span><span className="num">{duration} min</span></span>
        <input type="range" min="5" max="90" step="5" value={duration} onChange={(e) => setDuration(+e.target.value)} />
      </label>
      {KINDS.map((k) => (
        <div className="chaos-opt" key={k.kind}>
          <span className="ico"><span className="ms" aria-hidden="true">{k.icon}</span></span>
          <div>
            <b>{k.label}</b><small>{k.sub}</small>
            <label className="field"><span className="field-row"><span>{k.field}</span><span className="num">{vals[k.kind]}{k.unit}</span></span>
              <input type="range" min={k.min} max={k.max} step={k.step} value={vals[k.kind]} onChange={(e) => setVals((v) => ({ ...v, [k.kind]: +e.target.value }))} />
            </label>
            <button className="btn danger sm" disabled={disabled || busy != null} onClick={() => fire(k)}>
              {busy === k.kind ? 'Counting down…' : 'Strike in 5 s'}
            </button>
          </div>
        </div>
      ))}
      <p className={`sheet-msg ${msg ? (msg.ok ? 'ok' : 'err') : ''}`} role="status">{msg?.text ?? (disabled ? 'This run has finished. Start a new run to inject chaos.' : '')}</p>
    </Sheet>
  )
}
