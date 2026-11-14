import { useCallback, useEffect, useRef, useState } from 'react'
import { AGENTS, api, wsUrl } from './lib.js'

/**
 * Owns one live run. Raw events (~100 per simulated minute) are folded into one compact row per
 * minute, each carrying its full negotiation thread (price rounds, every agent's bids, ledger
 * outcome, chaos, cascades). State is flushed at most once per animation frame.
 */
function emptyThread(tick) {
  return { tick, rounds: [], bids: Object.fromEntries(AGENTS.map((a) => [a, []])), ledger: [], chaos: [], cascades: [], deals: [], supplyInfo: null, damage: null }
}

export function useRun() {
  const [info, setInfo] = useState(null)
  const [rows, setRows] = useState([])
  const [snapshot, setSnapshot] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState(null)
  const [connected, setConnected] = useState(false)

  const ws = useRef(null)
  const pending = useRef({ rows: [], snapshot: null, metrics: null })
  const cur = useRef(emptyThread(0))
  const snapByTick = useRef({})
  const raf = useRef(0)

  const flush = useCallback(() => {
    raf.current = 0
    const p = pending.current
    pending.current = { rows: [], snapshot: null, metrics: null }
    if (p.rows.length) setRows((r) => r.concat(p.rows))
    if (p.snapshot) setSnapshot(p.snapshot)
    if (p.metrics) setMetrics(p.metrics)
  }, [])

  const ingest = useCallback((msg) => {
    if (msg.snapshot) snapByTick.current[msg.snapshot.tick] = msg.snapshot
    for (const e of msg.events) {
      const th = cur.current
      switch (e.type) {
        case 'SUPPLY_UPDATE': th.supplyInfo = e.payload; break
        case 'CHAOS_INJECTED': th.chaos.push(e.payload); break
        case 'PRICE_BROADCAST': th.rounds.push(e.payload); break
        case 'BID': th.bids[e.agent]?.push(e.payload.demand_mw); break
        case 'PROPOSE': case 'VALIDATED': case 'REJECTED': case 'COMMIT': case 'FALLBACK':
          th.ledger.push({ type: e.type, ...e.payload }); break
        case 'CONCESSION': if (!e.payload.replay) th.deals.push({ type: 'deal', from: e.agent, ...e.payload }); break
        case 'COUNTER': th.deals.push({ type: 'counter', from: e.agent, ...e.payload }); break
        case 'DAMAGE_TICK': th.damage = e.payload.damage; break
        case 'CASCADE_TRIGGERED': th.cascades.push(e.payload.cascade); break
        case 'TICK_SUMMARY': {
          const s = e.payload
          const snap = snapByTick.current[e.tick]
          const need = snap?.need ?? Object.fromEntries(AGENTS.map((a) => [a, s.served_pct[a] > 0 ? s.grants[a] / s.served_pct[a] : NaN]))
          pending.current.rows.push({
            tick: e.tick, t: e.t, ...s, need,
            needTotal: AGENTS.reduce((x, a) => x + (need[a] || 0), 0),
            granted: AGENTS.reduce((x, a) => x + s.grants[a], 0),
            status: snap?.status, jain: snap?.jain, cascadesCum: snap?.cascades, credits: snap?.credits,
            thread: th,
          })
          delete snapByTick.current[e.tick]
          cur.current = emptyThread(e.tick + 1)
          break
        }
        default: break
      }
    }
    if (msg.snapshot) pending.current.snapshot = msg.snapshot
    if (msg.metrics) pending.current.metrics = msg.metrics
    if (!raf.current) raf.current = requestAnimationFrame(flush)
  }, [flush])

  const start = useCallback(async ({ strategy, seed, speed, scenario = 'default_8h' }) => {
    ws.current?.close()
    cancelAnimationFrame(raf.current); raf.current = 0
    pending.current = { rows: [], snapshot: null, metrics: null }
    cur.current = emptyThread(0)
    snapByTick.current = {}
    setError(null); setRows([]); setSnapshot(null); setMetrics(null)
    try {
      const run = await api('/runs', { method: 'POST', body: { strategy, seed, speed, scenario } })
      setInfo(run)
      const sock = new WebSocket(wsUrl(`/runs/${run.run_id}/stream`))
      ws.current = sock
      sock.onopen = () => setConnected(true)
      sock.onclose = () => setConnected(false)
      sock.onerror = () => setError('Lost the connection to the simulation server. Make sure the API is running on port 8010, then start a new run.')
      sock.onmessage = (m) => ingest(JSON.parse(m.data))
    } catch (err) {
      setError(`Couldn't start a run: ${err.message}. Start the API with "python -m uvicorn api.app:app --port 8010" and try again.`)
    }
  }, [ingest])

  const control = useCallback(async (body) => {
    if (!info) return
    const next = await api(`/runs/${info.run_id}/control`, { method: 'POST', body })
    setInfo((i) => ({ ...i, ...next }))
  }, [info])

  const chaos = useCallback(async (kind, params) => {
    if (!info) throw new Error('Start a run first')
    return api(`/runs/${info.run_id}/chaos`, { method: 'POST', body: { kind, params } })
  }, [info])

  // Sink for the 3D stage. useRun stays the only WebSocket owner; the store is a mirror the
  // frame loop can read imperatively, so the scene never causes a React render (and the flat
  // dashboard below keeps reading the same React state it always did).

  useEffect(() => () => { ws.current?.close(); cancelAnimationFrame(raf.current) }, [])

  return { info, rows, snapshot, metrics, error, connected, start, control, chaos }
}
