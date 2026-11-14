import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useRun } from './useRun.js'
import { useTheme } from './useTheme.js'
import { Skyline } from './components/Illustrations.jsx'
import { AGENTS, AGENT_META, STATUS_TEXT, STRATEGIES, fmt, hhmm, pct, statusOf } from './lib.js'
import Chat from './components/Chat.jsx'
import Charts, { hover } from './components/Charts.jsx'
import { Avatar } from './components/Avatars.jsx'
import { ChaosSheet, RunSheet } from './components/Sheets.jsx'
import MethodDialog from './components/Method.jsx'


const CompareView = lazy(() => import('./components/CompareView.jsx'))
const SPEEDS = [1, 4, 16, 60]

function Tiles({ row, metrics, onExplain }) {
  const kpis = [
    ['Damage', fmt(row?.damage_cum ?? 0), ''],
    ['Fairness', fmt(row?.jain, 2), ''],
    ['Cascades', row?.cascadesCum ?? 0, ''],
    ...(metrics ? [['Breaches', metrics.violations, metrics.violations ? 'bad' : 'good']] : []),
  ]
  return (
    <>
      <div className="tiles">
        {AGENTS.map((a) => {
          const s = row?.served_pct?.[a] ?? 1
          const st = statusOf(row, a)
          const cr = row?.credits?.[a] ?? 0
          const base = a === 'water' ? `Reservoir ${pct(row?.reservoir)}` : a === 'telecom' ? `Battery ${pct(row?.battery)}` : `${Math.round(s * 100)}% met`
          const extra = Math.abs(cr) >= 0.01 ? `${base} · credit ${cr > 0 ? '+' : ''}${fmt(cr, 2)}` : base
          return (
            <article key={a} className="tile">
              <div className="tile-top">
                <Avatar who={a} size={22} />
                <b>{AGENT_META[a].label}</b>
              </div>
              <div className="tile-mw"><span className="num big">{fmt(row?.grants?.[a])}</span><span className="num of">/ {fmt(row?.need?.[a], 0)} MW</span></div>
              <div className="meter"><i style={{ width: `${s * 100}%`, background: AGENT_META[a].color }} /></div>
              <div className="tile-note"><span>{extra}</span><span className={`st ${st}`} title={STATUS_TEXT[st]}>{STATUS_TEXT[st]}</span></div>
            </article>
          )
        })}
      </div>
      <div className="kpis">
        {kpis.map(([label, value, tone]) => (
          <div key={label} className="kpi-cell">
            <span>{label}</span><b className={`num ${tone}`}>{value}</b>
          </div>
        ))}
        <button className="btn icon kpi-help" onClick={onExplain} aria-label="How damage and fairness are computed" title="How damage and fairness are computed">
          <span className="ms" aria-hidden="true">function</span>
        </button>
      </div>
    </>
  )
}

function Timeline({ rows, total, shocks, value, chaosTicks, onChange }) {
  const trackRef = useRef(null)
  const dragging = useRef(false)
  const [ahead, setAhead] = useState(false)
  useEffect(() => { if (!ahead) return undefined; const id = setTimeout(() => setAhead(false), 1800); return () => clearTimeout(id) }, [ahead])
  // map the pointer to a minute on the full 8-hour bar; minutes not played yet clamp to the newest
  const seek = (e) => {
    const b = trackRef.current.getBoundingClientRect()
    const t = Math.round(Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)) * (total - 1))
    setAhead(t > rows.length - 1)
    onChange(t)
  }
  const p = (t) => `${(t / (total - 1)) * 100}%`
  return (
    <footer className="timeline">
      <span className="num tl-l">00:00</span>
      <div className="tl-track" ref={trackRef}
        onPointerDown={(e) => { if (!rows.length) return; e.currentTarget.setPointerCapture(e.pointerId); dragging.current = true; seek(e) }}
        onPointerMove={(e) => { if (dragging.current) seek(e) }}
        onPointerUp={() => { dragging.current = false }} onPointerCancel={() => { dragging.current = false }}>
        <div className="tl-rail">
          {shocks.map((s) => <span key={s.tick} className="tl-band" style={{ left: p(s.tick), width: `${(s.duration / total) * 100}%` }} title={s.label} />)}
          <span className="tl-fill" style={{ width: p(rows.length ? rows.length - 1 : 0) }} />
        </div>
        {chaosTicks.map((t, i) => <span key={i} className="tl-chaos" style={{ left: p(t) }} />)}
        <span className="tl-knob" style={{ left: p(value ?? 0) }} />
        {ahead && <span className="tl-hint" style={{ left: p(value ?? 0) }}>Not played yet</span>}
        <span className="tl-time num" style={{ left: p(value ?? 0) }}>{hhmm(value ?? 0)}</span>
        <input type="range" min="0" max={total - 1} value={value ?? 0} disabled={!rows.length} tabIndex={0}
          aria-label="Scrub through the disaster" aria-valuetext={hhmm(value ?? 0)} onChange={(e) => onChange(+e.target.value)} />
      </div>
      <span className="num tl-r">08:00</span>
    </footer>
  )
}

export default function App() {
  const run = useRun()
  const [theme, toggleTheme] = useTheme()
  const [view, setView] = useState('live')
  const [mobileTab, setMobileTab] = useState('data')
  const [cfg, setCfg] = useState({ strategy: 'ours', seed: 0 })
  const [speed, setSpeed] = useState(1)
  const [focus, setFocus] = useState(null) // pinned minute; null = follow live
  const [scrollTo, setScrollTo] = useState(null)
  const [sheet, setSheet] = useState(null)
  const [replaying, setReplaying] = useState(false) // playing back history from `focus`

  useEffect(() => { run.start({ ...cfg, speed }) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const rows = run.rows
  const latest = rows.at(-1)
  const shown = focus != null ? rows[focus] : latest
  const done = !!run.metrics
  const paused = !!run.info?.paused
  const total = run.info?.ticks ?? 480
  const strategy = run.info?.strategy ?? cfg.strategy
  const chaosTicks = rows.filter((r) => r.thread.chaos.some((c) => c.source === 'live')).map((r) => r.tick)

    const closeSheet = useCallback(() => setSheet(null), [])
  // pick a minute from a chart, heatmap or timeline: pin it and scroll the chat there
  // Entering history freezes the live simulation so a replay can catch up; leaving resumes it.
  const autoPaused = useRef(false)
  const freeze = () => { if (!done && !paused && !autoPaused.current) { autoPaused.current = true; run.control({ paused: true }).catch(() => {}) } }
  const unfreeze = () => { if (autoPaused.current) { autoPaused.current = false; run.control({ paused: false }).catch(() => {}) } }
  const start = useCallback((c) => { autoPaused.current = false; setCfg(c); setFocus(null); run.start({ ...c, speed }) }, [run, speed])
  const pick = (t) => { freeze(); setFocus(t); setScrollTo(t); setReplaying(false) }
  // pick from the chat: pin it, charts follow (chat is already showing it)
  const pickFromChat = (t) => { freeze(); setFocus(t); setReplaying(false) }
  // seeking never resumes the run by itself; only Play (replay catches up) or Back to live does
  const scrub = (t) => pick(Math.max(0, Math.min(t, rows.length - 1)))
  // Replay: step the pinned minute forward at the chosen speed; on catching up, rejoin live.
  const live = useRef({ n: 0, done: false })
  live.current = { n: rows.length, done }
  useEffect(() => {
    if (focus == null || !replaying) return undefined
    const step = Math.max(1, Math.round(speed / 20))
    const id = setInterval(() => {
      setFocus((f) => {
        if (f == null) return f
        const next = f + step
        const { n, done: fin } = live.current
        if (next >= n - 1) {
          setReplaying(false)
          return fin ? n - 1 : null
        }
        if (Math.floor(next / 10) !== Math.floor(f / 10)) setScrollTo(next)
        return next
      })
    }, Math.max(50, (1000 * step) / speed))
    return () => clearInterval(id)
  }, [focus != null, replaying, speed]) // eslint-disable-line react-hooks/exhaustive-deps

  // One play/pause button: in history it plays/pauses the replay, at live it pauses the simulation.
  const inHistory = focus != null
  const playing = inHistory ? replaying : !paused && !done
  const onPlay = () => {
    if (inHistory) setReplaying((r) => !r)
    else if (done) { setFocus(0); setScrollTo(0); setReplaying(true) }
    else run.control({ paused: !paused })
  }
  const goLive = () => { setFocus(null); setReplaying(false); unfreeze() }
  // replay reached the newest minute and rejoined live
  useEffect(() => { if (focus == null) unfreeze() }, [focus]) // eslint-disable-line react-hooks/exhaustive-deps
  // Strike from the chaos panel: always back to live and running, so it lands within a second.
  // Strike: close the panel, run a big 5-second on-screen countdown, then hit the live run.
  const [countdown, setCountdown] = useState(null) // {n, label, icon} | {impact, label, at}
  const strike = async (kind, params, meta) => {
    setSheet(null)
    setFocus(null); setReplaying(false); autoPaused.current = false
    if (paused) await run.control({ paused: false })
    for (let n = 5; n > 0; n--) {
      setCountdown({ n, label: meta?.label ?? kind, icon: meta?.icon })
      await new Promise((res) => setTimeout(res, 1000))
    }
    try {
      const r = await run.chaos(kind, params)
      setCountdown({ impact: true, label: meta?.label ?? kind, icon: meta?.icon, at: hhmm(r.queued.tick), dur: params.duration })
      setTimeout(() => setCountdown(null), 1800)
      return r
    } catch (e) { setCountdown(null); throw e }
  }
  const changeSpeed = (s) => { setSpeed(s); run.control({ speed: s }).catch(() => {}) }

  return (
    <div className={`app tab-${mobileTab}`}>
      <header className="appbar">
        <div className="brand"><span className="brand-mark"><span className="ms" aria-hidden="true">bolt</span></span><h1>Blackout Arena</h1></div>
        <nav className="views" aria-label="Views">
          {[['live', 'Live'], ['compare', 'Compare']].map(([id, l]) => (
            <button key={id} aria-current={view === id ? 'page' : undefined} onClick={() => setView(id)}>{l}</button>
          ))}
        </nav>
        <button className="run-chip" onClick={() => setSheet('run')} title="Start a new run">
          {STRATEGIES[strategy].label} · seed <span className="num">{run.info?.seed ?? cfg.seed}</span><span className="ms" aria-hidden="true">expand_more</span>
        </button>
        <span className="spacer" />
        <span className="clock num" aria-label="Simulation time">{hhmm(shown?.tick ?? 0)}</span>
        {inHistory && <span className="replay-tag">{replaying ? 'Replaying' : 'Paused in history'}</span>}
        {inHistory && !done && <button className="btn text sm" onClick={goLive}><span className="ms" aria-hidden="true">sensors</span>Back to live</button>}
        <button className="btn icon" disabled={!run.info} aria-label={playing ? 'Pause' : 'Play'} title={inHistory ? 'Play/pause the replay' : done ? 'Replay from the start' : 'Pause/resume the simulation'} onClick={onPlay}>
          <span className="ms" aria-hidden="true">{playing ? 'pause' : done && !inHistory ? 'replay' : 'play_arrow'}</span>
        </button>
        <div className="seg" role="radiogroup" aria-label="Playback speed">
          {SPEEDS.map((s) => <button key={s} role="radio" aria-checked={speed === s} onClick={() => changeSpeed(s)}>{s}×</button>)}
        </div>
        <button className="btn icon theme-btn" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} title="Toggle theme">
          <span className="ms" aria-hidden="true">{theme === 'dark' ? 'light_mode' : 'dark_mode'}</span>
        </button>
        <button className="btn danger" onClick={() => setSheet('chaos')}><span className="ms" aria-hidden="true">bolt</span><span className="lbl">Chaos</span></button>
      </header>

      {run.error && <div className="banner" role="alert"><span className="ms" aria-hidden="true">error</span>{run.error}</div>}

      {view === 'live' ? (
        <>
          <div className="mtabs" role="tablist">
            {[['data', 'Data'], ['chat', 'Chat']].map(([id, l]) => <button key={id} role="tab" aria-selected={mobileTab === id} onClick={() => setMobileTab(id)}>{l}</button>)}
          </div>
          <main className="workspace">
            <section className="panel data scroll" aria-label="Data">
              <div className="hero-illo">
                <Skyline lit={shown ? Math.min(1, shown.granted / Math.max(1, shown.needTotal)) : 1} />
                <div className="hero-text"><b>{shown ? `${fmt(shown.supply, 0)} MW on the grid` : 'Waiting for power'}</b>
                  <span>{shown ? `${fmt(shown.needTotal, 0)} MW needed · ${STRATEGIES[strategy].label.toLowerCase()} at minute ${shown.t}` : 'Start a run to light up the city'}</span></div>
              </div>
              <Tiles row={shown} metrics={run.metrics} onExplain={() => setSheet('method')} />
              <Charts rows={rows} shocks={run.info?.shocks ?? []} focus={focus} onPick={pick} theme={theme} />
            </section>
            <Chat rows={rows} strategy={strategy} speed={speed} focus={focus} scrollTo={scrollTo} onHover={hover.set} onPick={pickFromChat} />
          </main>
          <Timeline rows={rows} total={total} shocks={run.info?.shocks ?? []} chaosTicks={chaosTicks} value={shown?.tick} onChange={scrub} />
        </>
      ) : (
        <main className="compare-wrap scroll">
          <Suspense fallback={<div className="panel"><div className="skeleton" /></div>}>
            <CompareView seed={run.info?.seed ?? cfg.seed} theme={theme} onExplain={() => setSheet('method')} />
          </Suspense>
        </main>
      )}

      {countdown && (
        <div className={`countdown ${countdown.impact ? 'impact' : ''}`} role="status" aria-live="assertive">
          <div className="cd-card">
            <span className="cd-label"><span className="ms" aria-hidden="true">{countdown.icon ?? 'bolt'}</span>{countdown.label}</span>
            {countdown.impact
              ? <><b className="cd-impact">Injected</b><span className="cd-sub num">{countdown.at} · lasts {countdown.dur} min · the agents renegotiate from here</span></>
              : <><div className="cd-ring"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="54" className="cd-track" /><circle key={countdown.n} cx="60" cy="60" r="54" className="cd-prog" /></svg>
                  <b key={`n${countdown.n}`} className="cd-num num">{countdown.n}</b></div>
                <span className="cd-sub">Hitting the grid in…</span></>}
          </div>
        </div>
      )}
      {sheet === 'method' && <MethodDialog onClose={closeSheet} />}
      {sheet === 'run' && <RunSheet initial={{ strategy, seed: run.info?.seed ?? cfg.seed }} onStart={start} onClose={closeSheet} />}
      {sheet === 'chaos' && <ChaosSheet onInject={strike} onClose={closeSheet} disabled={!run.info || done} />}
    </div>
  )
}
