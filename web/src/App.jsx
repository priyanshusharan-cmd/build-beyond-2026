import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { useRun } from './useRun.js'
import { useTheme } from './useTheme.js'
import { Skyline } from './components/Illustrations.jsx'
import { AGENTS, AGENT_META, STATUS_TEXT, STRATEGIES, fmt, hhmm, pct, statusOf } from './lib.js'
import Chat from './components/Chat.jsx'
import Charts, { hover } from './components/Charts.jsx'
import { Avatar } from './components/Avatars.jsx'
import { ChaosSheet, RunSheet } from './components/Sheets.jsx'

const CompareView = lazy(() => import('./components/CompareView.jsx'))
const SPEEDS = [1, 4, 16, 60]

function Tiles({ row, metrics }) {
  return (
    <div className="tiles">
      {AGENTS.map((a) => {
        const s = row?.served_pct?.[a] ?? 1
        const st = statusOf(row, a)
        const extra = a === 'water' ? `Reservoir ${pct(row?.reservoir)}` : a === 'telecom' ? `Battery ${pct(row?.battery)}` : `${Math.round(s * 100)}% met`
        return (
          <article key={a} className="tile">
            <Avatar who={a} size={24} />
            <div className="tile-body">
              <div className="tile-top"><b>{AGENT_META[a].label}</b><span className={`st ${st}`}>{STATUS_TEXT[st]}</span></div>
              <div className="tile-mw num">{fmt(row?.grants?.[a])} / {fmt(row?.need?.[a], 0)} MW · {extra}</div>
              <div className="meter"><i style={{ width: `${s * 100}%`, background: AGENT_META[a].hex }} /></div>
            </div>
          </article>
        )
      })}
      <article className="tile kpi">
        <div><span>Damage</span><b className="num">{fmt(row?.damage_cum ?? 0)}</b></div>
        <div><span>Fairness</span><b className="num">{fmt(row?.jain, 2)}</b></div>
        <div><span>Cascades</span><b className="num">{row?.cascadesCum ?? 0}</b></div>
        {metrics && <div><span>Breaches</span><b className={`num ${metrics.violations ? 'bad' : 'good'}`}>{metrics.violations}</b></div>}
      </article>
    </div>
  )
}

function Timeline({ rows, total, shocks, value, chaosTicks, onChange }) {
  const p = (t) => `${(t / (total - 1)) * 100}%`
  return (
    <footer className="timeline">
      <span className="num tl-l">00:00</span>
      <div className="tl-track">
        <div className="tl-rail">
          {shocks.map((s) => <span key={s.tick} className="tl-band" style={{ left: p(s.tick), width: `${(s.duration / total) * 100}%` }} title={s.label} />)}
          <span className="tl-fill" style={{ width: p(rows.length ? rows.length - 1 : 0) }} />
        </div>
        {chaosTicks.map((t, i) => <span key={i} className="tl-chaos" style={{ left: p(t) }} />)}
        <span className="tl-knob" style={{ left: p(value ?? 0) }} />
        <input type="range" min="0" max={Math.max(0, rows.length - 1)} value={value ?? 0} disabled={!rows.length}
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

  useEffect(() => { run.start({ ...cfg, speed }) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const rows = run.rows
  const latest = rows.at(-1)
  const shown = focus != null ? rows[focus] : latest
  const done = !!run.metrics
  const paused = !!run.info?.paused
  const total = run.info?.ticks ?? 480
  const strategy = run.info?.strategy ?? cfg.strategy
  const chaosTicks = rows.filter((r) => r.thread.chaos.some((c) => c.source === 'live')).map((r) => r.tick)

  const start = useCallback((c) => { setCfg(c); setFocus(null); run.start({ ...c, speed }) }, [run, speed])
  const closeSheet = useCallback(() => setSheet(null), [])
  // pick a minute from a chart, heatmap or timeline: pin it and scroll the chat there
  const pick = useCallback((t) => { setFocus(t); setScrollTo(t); }, [])
  // pick from the chat: pin it, charts follow (chat is already showing it)
  const pickFromChat = useCallback((t) => setFocus(t), [])
  const scrub = (t) => { if (t >= rows.length - 1 && !done) { setFocus(null) } else pick(t) }
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
        {focus != null && <button className="btn text sm" onClick={() => setFocus(null)}><span className="ms" aria-hidden="true">sensors</span>Live</button>}
        <button className="btn icon" disabled={!run.info || done} aria-label={paused ? 'Resume' : 'Pause'} onClick={() => run.control({ paused: !paused })}>
          <span className="ms" aria-hidden="true">{paused ? 'play_arrow' : 'pause'}</span>
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
              <Tiles row={shown} metrics={run.metrics} />
              <Charts rows={rows} shocks={run.info?.shocks ?? []} focus={focus} onPick={pick} theme={theme} />
            </section>
            <Chat rows={rows} strategy={strategy} speed={speed} focus={focus} scrollTo={scrollTo} onHover={hover.set} onPick={pickFromChat} />
          </main>
          <Timeline rows={rows} total={total} shocks={run.info?.shocks ?? []} chaosTicks={chaosTicks} value={shown?.tick} onChange={scrub} />
        </>
      ) : (
        <main className="compare-wrap scroll">
          <Suspense fallback={<div className="panel"><div className="skeleton" /></div>}>
            <CompareView seed={run.info?.seed ?? cfg.seed} />
          </Suspense>
        </main>
      )}

      {sheet === 'run' && <RunSheet initial={{ strategy, seed: run.info?.seed ?? cfg.seed }} onStart={start} onClose={closeSheet} />}
      {sheet === 'chaos' && <ChaosSheet onInject={run.chaos} onClose={closeSheet} disabled={!run.info || done} />}
    </div>
  )
}
