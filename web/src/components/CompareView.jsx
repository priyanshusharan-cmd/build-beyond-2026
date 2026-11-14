import { memo, useEffect, useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, fmt, hhmm, STRATEGIES } from '../lib.js'

const ORDER = ['ours', 'priority', 'proportional', 'blind']
const COLORS = { ours: '#33557c', priority: '#c98a3c', proportional: '#8a63d2', blind: '#c8384f' }
const METRICS = [
  { key: 'total_damage', label: 'Total damage', icon: 'local_fire_department', better: 'low', d: 1, note: 'Modeled proxy over 8 hours' },
  { key: 'violations', label: 'Safety breaches', icon: 'gpp_maybe', better: 'low', d: 0, note: 'Grants above available supply' },
  { key: 'jain', label: 'Fairness', icon: 'balance', better: 'high', d: 3, note: "Jain's index; 1.000 is perfectly even" },
  { key: 'cascades', label: 'Cascades', icon: 'account_tree', better: 'low', d: 0, note: 'Knock-on failures triggered' },
]

function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="tip">
      <b className="num">{hhmm(label)}</b>
      {[...payload].sort((a, b) => a.value - b.value).map((p) => (
        <div key={p.dataKey} className="num" style={{ color: p.stroke }}>{STRATEGIES[p.dataKey].label}: {fmt(p.value, 1)}</div>
      ))}
    </div>
  )
}

function CompareView({ seed }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let live = true
    setData(null); setErr(null)
    api(`/compare?seed=${seed}`).then((d) => live && setData(d.strategies)).catch((e) => live && setErr(e.message))
    return () => { live = false }
  }, [seed])

  const series = useMemo(() => {
    if (!data) return []
    return data.ours.series.map((p, i) => ({ tick: p.tick, ...Object.fromEntries(ORDER.map((s) => [s, data[s].series[i]?.damage_cum])) }))
  }, [data])

  if (err) return <div className="glass widget"><p>Couldn&apos;t load the comparison: {err}. Check that the API is running, then switch views to retry.</p></div>

  return (
    <div className="compare">
      <section className="glass chart-card">
        <h3>Damage over time · seed {seed}</h3>
        <p className="hint">Same supply, shocks and damage model for all four. Lower is better.</p>
        <div className="legend-row">{ORDER.map((s) => <span key={s}><i style={{ background: COLORS[s] }} />{STRATEGIES[s].label}</span>)}</div>
        <div className="chart-box" style={{ height: 300 }}>
          {!data ? <div className="skeleton" /> : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 6, right: 8, left: -4, bottom: 0 }}>
                <CartesianGrid stroke="rgba(24,33,45,0.07)" vertical={false} />
                <XAxis dataKey="tick" type="number" domain={[0, 479]} ticks={[0, 60, 120, 180, 240, 300, 360, 420, 479]} tickFormatter={hhmm} stroke="#8a95a5" fontSize={11.5} tickLine={false} axisLine={false} />
                <YAxis scale="sqrt" stroke="#8a95a5" fontSize={11.5} tickLine={false} axisLine={false} width={48} />
                <Tooltip content={<Tip />} cursor={{ stroke: '#18212d', strokeOpacity: 0.2 }} />
                {ORDER.map((s) => (
                  <Line key={s} dataKey={s} type="monotone" stroke={COLORS[s]} strokeWidth={s === 'ours' ? 3.2 : 2} dot={false} animationDuration={900} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      <div className="metric-grid">
        {METRICS.map((m) => {
          const vals = data ? ORDER.map((s) => data[s][m.key]) : []
          const best = vals.length ? (m.better === 'low' ? Math.min(...vals) : Math.max(...vals)) : null
          const max = Math.max(...vals, 1e-9)
          return (
            <section key={m.key} className="glass widget">
              <p className="w-title"><span className="ms" aria-hidden="true">{m.icon}</span>{m.label}</p>
              <p className="w-note">{m.note}</p>
              {!data ? <div className="skeleton" style={{ marginTop: 12 }} /> : (
                <ol className="rank">
                  {ORDER.map((s) => {
                    const v = data[s][m.key]
                    return (
                      <li key={s} className={s === 'ours' ? 'ours' : ''}>
                        <span>{STRATEGIES[s].label}</span>
                        <span className={`num ${v === best ? 'best' : ''}`}>{fmt(v, m.d)}{v === best ? ' · best' : ''}</span>
                        <span className="bar"><i style={{ width: `${(v / max) * 100}%` }} /></span>
                      </li>
                    )
                  })}
                </ol>
              )}
            </section>
          )
        })}
      </div>
      <p className="glass honest"><span className="ms" aria-hidden="true">info</span>
        Measured on this seed. Where a baseline wins a metric, it is marked best.</p>
    </div>
  )
}

export default memo(CompareView)
