import { memo, useEffect, useMemo, useRef, useSyncExternalStore } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { CHART_THEME } from '../useTheme.js'
import { AGENTS, AGENT_META, CASCADE_TEXT, chaosText, createStore, fmt, hhmm, pct, statusOf, STATUS_TEXT } from '../lib.js'

/** Transient hover minute shared by every chart and the chat; pinned focus comes from App. */
export const hover = createStore(null)
const useHover = () => useSyncExternalStore(hover.subscribe, hover.get)

const TICKS = [0, 60, 120, 180, 240, 300, 360, 420, 479]
const axisXOf = (ct) => ({ dataKey: 'tick', type: 'number', domain: [0, 479], ticks: TICKS, tickFormatter: hhmm, stroke: ct.axis, fontSize: 12, tickLine: false, axisLine: false, height: 20 })
const axisYOf = (ct) => ({ stroke: ct.axis, fontSize: 12, tickLine: false, axisLine: false, width: 36 })
const M = { top: 8, right: 8, left: 0, bottom: 0 }

function Cursor({ focus, yAxisId, color }) {
  const h = useHover()
  const t = h ?? focus
  return t == null ? null : <ReferenceLine x={t} yAxisId={yAxisId} stroke={color} strokeOpacity={0.55} strokeWidth={1.5} ifOverflow="hidden" />
}

function bands(shocks, chaos, ct) {
  return [
    ...shocks.map((s) => <ReferenceArea key={`s${s.tick}`} x1={s.tick} x2={Math.min(479, s.tick + s.duration)} fill={ct.shock} fillOpacity={0.08} ifOverflow="hidden" />),
    ...chaos.map((c, i) => <ReferenceArea key={`c${i}`} x1={c.tick} x2={Math.min(479, c.tick + c.duration)} fill={ct.chaos} fillOpacity={0.12} ifOverflow="hidden" />),
  ]
}

function Tip({ active, label, rows }) {
  const r = active ? rows[label] : null
  if (!r) return null
  const th = r.thread
  return (
    <div className="tip">
      <div className="tip-head num"><b>{r.t}</b><span>{fmt(r.supply)} MW supply · damage {fmt(r.damage_tick, 2)}</span></div>
      <table><tbody>
        {AGENTS.map((a) => {
          const st = statusOf(r, a)
          return (
            <tr key={a}>
              <td><i style={{ background: AGENT_META[a].hex }} />{AGENT_META[a].label}</td>
              <td className="num">{fmt(r.grants[a])}/{fmt(r.need[a], 0)}</td>
              <td className="num">{pct(r.served_pct[a])}</td>
              <td className="num">{fmt(th.damage?.[a], 2)}</td>
              <td className={`st ${st}`}>{STATUS_TEXT[st]}</td>
            </tr>
          )
        })}
      </tbody></table>
      {[...th.chaos.map((c) => chaosText(c).title), ...th.cascades.map((c) => CASCADE_TEXT[c]?.title ?? c)].map((e, i) => <div key={i} className="tip-ev">⚡ {e}</div>)}
    </div>
  )
}

function Chart({ title, caption, legend, children }) {
  return (
    <section className="chart">
      <div className="chart-head"><h3>{title}</h3><span className="cap">{caption}</span>
        {legend && <span className="legend">{legend.map(([l, c, dash]) => <span key={l}><i style={{ background: c, ...(dash ? { height: 2 } : null) }} />{l}</span>)}</span>}
      </div>
      <div className="chart-plot">{children}</div>
    </section>
  )
}

function Heatmap({ rows, focus, onPick, ct }) {
  const cv = useRef(null)
  const h = useHover()
  const t = h ?? focus
  useEffect(() => {
    const c = cv.current
    if (!c) return
    const draw = () => {
      const dpr = window.devicePixelRatio || 1
      const W = c.clientWidth, H = c.clientHeight
      c.width = W * dpr; c.height = H * dpr
      const ctx = c.getContext('2d'); ctx.scale(dpr, dpr)
      ctx.fillStyle = ct.heatBg; ctx.fillRect(0, 0, W, H)
      const cw = W / 480, rh = H / 4
      const col = (s) => {
        const k = Math.max(0, Math.min(1, s)), l = (a, b, x) => Math.round(a + (b - a) * x)
        const [r, g, b] = k < 0.6 ? [l(198, 232, k / 0.6), l(47, 170, k / 0.6), l(59, 80, k / 0.6)] : [l(232, 196, (k - 0.6) / 0.4), l(170, 230, (k - 0.6) / 0.4), l(80, 212, (k - 0.6) / 0.4)]
        return `rgb(${r},${g},${b})`
      }
      rows.forEach((r) => AGENTS.forEach((a, i) => { ctx.fillStyle = col(r.served_pct[a]); ctx.fillRect(r.tick * cw, i * rh + 1.5, Math.ceil(cw), rh - 3) }))
    }
    draw()
    const ro = new ResizeObserver(draw); ro.observe(c)
    return () => ro.disconnect()
  }, [rows, ct])
  const tickAt = (e) => { const b = cv.current.getBoundingClientRect(); return Math.floor(((e.clientX - b.left) / b.width) * 480) }
  return (
    <div className="heat">
      <div className="heat-labels">{AGENTS.map((a) => <span key={a} style={{ color: AGENT_META[a].hex }}>{AGENT_META[a].label}</span>)}</div>
      <div className="heat-canvas">
        <canvas ref={cv} role="img" aria-label="Share of need met per utility per minute; red is cut, green is fully served"
          onPointerMove={(e) => { const x = tickAt(e); hover.set(x < rows.length ? x : null) }} onPointerLeave={() => hover.set(null)}
          onClick={(e) => { const x = tickAt(e); if (x < rows.length) onPick(x) }} />
        {t != null && <span className="heat-cursor" style={{ left: `${(t / 480) * 100}%` }} />}
      </div>
    </div>
  )
}

function Charts({ rows, shocks, focus, onPick, theme = 'light' }) {
  const ct = CHART_THEME[theme]
  const axisX = axisXOf(ct), axisY = axisYOf(ct)
  const data = useMemo(() => rows.map((r) => ({
    tick: r.tick, supply: r.supply, res: r.reservoir * 100, bat: r.battery * 100, price: r.price,
    ...Object.fromEntries(AGENTS.flatMap((a) => [[`g_${a}`, r.grants[a]], [`d_${a}`, r.thread.damage?.[a] ?? 0]])),
  })), [rows])
  const chaos = useMemo(() => rows.flatMap((r) => r.thread.chaos.filter((c) => c.source === 'live').map((c) => ({ tick: r.tick, duration: c.params?.duration ?? 30 }))), [rows])
  const common = {
    data, syncId: 'arena', margin: M,
    onMouseMove: (e) => { if (e?.activeLabel != null) hover.set(e.activeLabel) },
    onMouseLeave: () => hover.set(null),
    onClick: (e) => { if (e?.activeLabel != null) onPick(e.activeLabel) },
  }
  const grid = <CartesianGrid stroke={ct.grid} vertical={false} />
  const noTip = <Tooltip content={() => null} cursor={false} isAnimationActive={false} />
  const agentLegend = AGENTS.map((a) => [AGENT_META[a].label, AGENT_META[a].hex])

  return (
    <div className="charts">
      <Chart title="Power split" caption="Who got what" legend={[...agentLegend, ['Supply', ct.ink, true]]}>
        <ResponsiveContainer><ComposedChart {...common}>
          {grid}{bands(shocks, chaos, ct)}<XAxis {...axisX} /><YAxis {...axisY} />
          <Tooltip content={<Tip rows={rows} />} cursor={false} isAnimationActive={false} wrapperStyle={{ zIndex: 5, pointerEvents: 'none' }} />
          {AGENTS.map((a) => <Area key={a} dataKey={`g_${a}`} stackId="g" type="stepAfter" stroke={AGENT_META[a].hex} strokeWidth={1} fill={AGENT_META[a].hex} fillOpacity={0.55} isAnimationActive={false} />)}
          <Line dataKey="supply" type="stepAfter" stroke={ct.ink} strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          <Cursor color={ct.ink} focus={focus} />
        </ComposedChart></ResponsiveContainer>
      </Chart>
      <Chart title="Need met" caption="Who was cut, and when — red is cut, green is fully served">
        <Heatmap rows={rows} focus={focus} onPick={onPick} ct={ct} />
      </Chart>
      <Chart title="Damage per minute" caption="What each cut cost (modeled proxy)">
        <ResponsiveContainer><ComposedChart {...common}>
          {grid}{bands(shocks, chaos, ct)}<XAxis {...axisX} /><YAxis {...axisY} />{noTip}
          {AGENTS.map((a) => <Area key={a} dataKey={`d_${a}`} stackId="d" type="monotone" stroke={AGENT_META[a].hex} strokeWidth={1} fill={AGENT_META[a].hex} fillOpacity={0.5} isAnimationActive={false} />)}
          <Cursor color={ct.ink} focus={focus} />
        </ComposedChart></ResponsiveContainer>
      </Chart>
      <Chart title="Buffers and price" caption="Why water and telecom gave way" legend={[['Reservoir', AGENT_META.water.hex], ['Battery', AGENT_META.telecom.hex], ['Price', ct.price, true]]}>
        <ResponsiveContainer><ComposedChart {...common}>
          {grid}{bands(shocks, chaos, ct)}<XAxis {...axisX} />
          <YAxis {...axisY} yAxisId="p" domain={[0, 100]} unit="%" />
          <YAxis {...axisY} yAxisId="price" orientation="right" />{noTip}
          <Line yAxisId="p" dataKey="res" stroke={AGENT_META.water.hex} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line yAxisId="p" dataKey="bat" stroke={AGENT_META.telecom.hex} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line yAxisId="price" dataKey="price" type="stepAfter" stroke={ct.price} strokeWidth={1.5} strokeDasharray="3 3" dot={false} isAnimationActive={false} />
          <Cursor color={ct.ink} focus={focus} yAxisId="p" />
        </ComposedChart></ResponsiveContainer>
      </Chart>
    </div>
  )
}

export default memo(Charts)
