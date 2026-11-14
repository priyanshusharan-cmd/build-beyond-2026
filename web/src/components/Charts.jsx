import { memo, useEffect, useMemo, useRef, useSyncExternalStore } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { CHART_THEME } from '../useTheme.js'
import { AGENTS, AGENT_META, agentHex, CASCADE_TEXT, chaosText, createStore, fmt, hhmm, pct, statusOf, STATUS_TEXT } from '../lib.js'

/** Transient hover minute shared by every chart and the chat; pinned focus comes from App. */
export const hover = createStore(null)
const useHover = () => useSyncExternalStore(hover.subscribe, hover.get)

const TICKS = [0, 60, 120, 180, 240, 300, 360, 420, 479]
const TYPE = { fontFamily: "'Roboto Mono', ui-monospace, monospace", fontSize: 11, letterSpacing: '-0.01em' }
const axisXOf = (ct) => ({ dataKey: 'tick', type: 'number', domain: [0, 479], ticks: TICKS, tickFormatter: hhmm, stroke: ct.axis, tick: { ...TYPE, fill: ct.axis }, tickLine: false, axisLine: false, height: 22 })
const axisYOf = (ct) => ({ stroke: ct.axis, tick: { ...TYPE, fill: ct.axis }, tickLine: false, axisLine: false, width: 40 })
const M = { top: 8, right: 8, left: 0, bottom: 0 }

function Cursor({ focus, yAxisId, color }) {
  const h = useHover()
  const t = h ?? focus
  return t == null ? null : <ReferenceLine x={t} yAxisId={yAxisId} stroke={color} strokeOpacity={0.5} strokeWidth={1.5} ifOverflow="hidden" />
}

function bands(shocks, chaos, ct) {
  return [
    ...shocks.map((s) => <ReferenceArea key={`s${s.tick}`} x1={s.tick} x2={Math.min(479, s.tick + s.duration)} fill={ct.shock} fillOpacity={0.07} ifOverflow="hidden" />),
    ...chaos.map((c, i) => <ReferenceArea key={`c${i}`} x1={c.tick} x2={Math.min(479, c.tick + c.duration)} fill={ct.chaos} fillOpacity={0.12} ifOverflow="hidden" />),
  ]
}

/** Soft vertical fade for every stacked area — the only gradient the charts use. */
function Fades({ theme, prefix }) {
  return (
    <defs>
      {AGENTS.map((a) => {
        const c = agentHex(a, theme)
        return (
          <linearGradient key={a} id={`${prefix}-${a}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={c} stopOpacity={0.62} />
            <stop offset="100%" stopColor={c} stopOpacity={0.34} />
          </linearGradient>
        )
      })}
    </defs>
  )
}

function Tip({ active, label, rows, theme }) {
  const r = active ? rows[label] : null
  if (!r) return null
  const th = r.thread
  return (
    <div className="tip">
      <div className="tip-head"><b className="num">{r.t}</b><span className="num">{fmt(r.supply)} MW supply · damage {fmt(r.damage_tick, 2)}</span></div>
      <table><tbody>
        {AGENTS.map((a) => {
          const st = statusOf(r, a)
          return (
            <tr key={a}>
              <td><i style={{ background: agentHex(a, theme) }} />{AGENT_META[a].label}</td>
              <td className="num">{fmt(r.grants[a])}/{fmt(r.need[a], 0)}</td>
              <td className="num">{pct(r.served_pct[a])}</td>
              <td className="num">{fmt(th.damage?.[a], 2)}</td>
              <td className={`st ${st}`}>{STATUS_TEXT[st]}</td>
            </tr>
          )
        })}
      </tbody></table>
      {[...th.chaos.map((c) => chaosText(c).title), ...th.cascades.map((c) => CASCADE_TEXT[c]?.title ?? c)].map((e, i) => <div key={i} className="tip-ev">{e}</div>)}
    </div>
  )
}


/** Legend that doubles as a readout: the value at the hovered or pinned minute. */
function LiveLegend({ rows, focus, items }) {
  const h = useHover()
  const t = h ?? focus
  const i = t == null ? rows.length - 1 : Math.max(0, Math.min(t, rows.length - 1))
  const r = rows[i]
  return (
    <span className="legend">
      {items.map(({ label, color, dash, read }) => (
        <span key={label}>
          <i style={{ background: color, ...(dash ? { height: 2, borderRadius: 2 } : null) }} />
          {label}
          {r && <b className="num" style={{ color }}>{read(r)}</b>}
        </span>
      ))}
    </span>
  )
}

/** Shocks, live chaos and cascades pinned along the top of a plot. */
function EventPins({ rows, shocks }) {
  const pins = useMemo(() => {
    const out = shocks.map((s) => ({ tick: s.tick, kind: 'shock', text: `${s.label ?? 'Scripted shock'} · ${s.delta_mw ?? ''} MW for ${s.duration} min` }))
    rows.forEach((r) => {
      r.thread.chaos.filter((c) => c.source === 'live').forEach((c) => out.push({ tick: r.tick, kind: 'chaos', text: chaosText(c).title }))
      r.thread.cascades.forEach((c) => out.push({ tick: r.tick, kind: 'cascade', text: CASCADE_TEXT[c]?.title ?? c }))
    })
    return out
  }, [rows, shocks])
  if (!pins.length) return null
  return (
    <div className="pins" aria-hidden="true">
      {pins.map((p, i) => <span key={i} className={`pin ${p.kind}`} style={{ left: `${(p.tick / 479) * 100}%` }} title={`${hhmm(p.tick)} — ${p.text}`} />)}
    </div>
  )
}

function Chart({ title, caption, legend, overlay, children }) {
  return (
    <section className="chart">
      <div className="chart-head"><h3>{title}</h3><span className="cap">{caption}</span>{legend}</div>
      <div className="chart-plot">{overlay}{children}</div>
    </section>
  )
}

function Heatmap({ rows, focus, onPick, ct, theme }) {
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
      // error -> warning -> success, straight off the scheme's container tones
      const col = (s) => {
        const k = Math.max(0, Math.min(1, s))
        const [a, b, x] = k < 0.6 ? [ct.heatLow, ct.heatMid, k / 0.6] : [ct.heatMid, ct.heatHigh, (k - 0.6) / 0.4]
        const m = (i) => Math.round(a[i] + (b[i] - a[i]) * x)
        return `rgb(${m(0)},${m(1)},${m(2)})`
      }
      rows.forEach((r) => AGENTS.forEach((a, i) => { ctx.fillStyle = col(r.served_pct[a]); ctx.fillRect(r.tick * cw, i * rh + 2, Math.ceil(cw), rh - 4) }))
    }
    draw()
    const ro = new ResizeObserver(draw); ro.observe(c)
    return () => ro.disconnect()
  }, [rows, ct])
  const tickAt = (e) => { const b = cv.current.getBoundingClientRect(); return Math.floor(((e.clientX - b.left) / b.width) * 480) }
  return (
    <div className="heat">
      <div className="heat-labels">{AGENTS.map((a) => <span key={a} style={{ color: agentHex(a, theme) }}>{AGENT_META[a].label}</span>)}</div>
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
  const agentItems = AGENTS.map((a) => ({ label: AGENT_META[a].label, color: agentHex(a, theme), read: (r) => fmt(r.grants[a], 0) }))
  const pins = <EventPins rows={rows} shocks={shocks} />

  return (
    <div className="charts">
      <Chart title="Power split" caption="Who got what · MW at the cursor" overlay={pins}
        legend={<LiveLegend rows={rows} focus={focus} items={[...agentItems, { label: 'Supply', color: ct.ink, dash: true, read: (r) => fmt(r.supply, 0) }]} />}>
        <ResponsiveContainer><ComposedChart {...common}>
          <Fades theme={theme} prefix="g" />
          {grid}{bands(shocks, chaos, ct)}<XAxis {...axisX} /><YAxis {...axisY} />
          <Tooltip content={<Tip rows={rows} theme={theme} />} cursor={false} isAnimationActive={false} wrapperStyle={{ zIndex: 5, pointerEvents: 'none' }} />
          {AGENTS.map((a) => <Area key={a} dataKey={`g_${a}`} stackId="g" type="stepAfter" stroke={agentHex(a, theme)} strokeWidth={1.25} fill={`url(#g-${a})`} isAnimationActive={false} />)}
          <Line dataKey="supply" type="stepAfter" stroke={ct.ink} strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          <Cursor color={ct.ink} focus={focus} />
        </ComposedChart></ResponsiveContainer>
      </Chart>
      <Chart title="Need met" caption="Share of need met, per utility, per minute"
        legend={<span className="legend scale"><span>0%</span><i className={`ramp ${theme}`} /><span>100%</span></span>}>
        <Heatmap rows={rows} focus={focus} onPick={onPick} ct={ct} theme={theme} />
      </Chart>
      <Chart title="Damage per minute" caption="What each cut cost (modeled proxy)" overlay={pins}
        legend={<LiveLegend rows={rows} focus={focus} items={AGENTS.map((a) => ({ label: AGENT_META[a].label, color: agentHex(a, theme), read: (r) => fmt(r.thread.damage?.[a] ?? 0, 1) }))} />}>
        <ResponsiveContainer><ComposedChart {...common}>
          <Fades theme={theme} prefix="d" />
          {grid}{bands(shocks, chaos, ct)}<XAxis {...axisX} /><YAxis {...axisY} />{noTip}
          {AGENTS.map((a) => <Area key={a} dataKey={`d_${a}`} stackId="d" type="monotone" stroke={agentHex(a, theme)} strokeWidth={1.25} fill={`url(#d-${a})`} isAnimationActive={false} />)}
          <Cursor color={ct.ink} focus={focus} />
        </ComposedChart></ResponsiveContainer>
      </Chart>
      <Chart title="Buffers and price" caption="Why water and telecom gave way" overlay={pins}
        legend={<LiveLegend rows={rows} focus={focus} items={[
          { label: 'Reservoir', color: agentHex('water', theme), read: (r) => pct(r.reservoir) },
          { label: 'Battery', color: agentHex('telecom', theme), read: (r) => pct(r.battery) },
          { label: 'Price', color: ct.price, dash: true, read: (r) => fmt(r.price, 2) },
        ]} />}>
        <ResponsiveContainer><ComposedChart {...common}>
          {grid}{bands(shocks, chaos, ct)}<XAxis {...axisX} />
          <YAxis {...axisY} yAxisId="p" domain={[0, 100]} unit="%" />
          <YAxis {...axisY} yAxisId="price" orientation="right" />{noTip}
          <Line yAxisId="p" dataKey="res" stroke={agentHex('water', theme)} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line yAxisId="p" dataKey="bat" stroke={agentHex('telecom', theme)} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line yAxisId="price" dataKey="price" type="stepAfter" stroke={ct.price} strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          <Cursor color={ct.ink} focus={focus} yAxisId="p" />
        </ComposedChart></ResponsiveContainer>
      </Chart>
    </div>
  )
}

export default memo(Charts)
