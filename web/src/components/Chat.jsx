import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { buildStory } from '../story.js'
import { Avatar, SPEAKERS } from './Avatars.jsx'
import { ChatIllo } from './Illustrations.jsx'

const CHIP_ICON = { urgent: 'priority_high', wait: 'schedule', yield: 'volunteer_activism', shock: 'bolt', degraded: 'warning' }

function Msg({ m, active, onHover, onPick }) {
  if (m.kind === 'quiet') {
    return (
      <button className={`quiet ${active ? 'active' : ''}`} data-tick={m.tick} data-to={m.to}
        onMouseEnter={() => onHover(m.tick)} onClick={() => onPick(m.tick)}>
        <span className="num">{m.t === m.tTo ? m.t : `${m.t}–${m.tTo}`}</span> · {m.allServed ? 'stable, everyone served' : 'holding steady, same split'}
      </button>
    )
  }
  const s = SPEAKERS[m.who]
  return (
    <div className={`msg ${active ? 'active' : ''}`} data-tick={m.tick} onMouseEnter={() => onHover(m.tick)} onClick={() => onPick(m.tick)}>
      <Avatar who={m.who} />
      <div className="msg-body">
        <div className="msg-head"><b style={{ color: s.color }}>{s.name}</b><time className="num">{m.t}</time></div>
        <p>{m.text}</p>
        {m.chips?.length > 0 && (
          <div className="chips">
            {m.chips.map((c, i) => <span key={i} className={`chip ${c.kind}`}><span className="ms" aria-hidden="true">{CHIP_ICON[c.kind]}</span>{c.label}</span>)}
          </div>
        )}
      </div>
    </div>
  )
}

function Chat({ rows, strategy, speed, focus, onHover, onPick, scrollTo }) {
  const summaryOnly = speed >= 16
  const story = useMemo(() => buildStory(rows, { strategy, summaryOnly }), [rows, strategy, summaryOnly])
  const body = useRef(null)
  const atBottom = useRef(true)
  const seen = useRef(0)
  const [unseen, setUnseen] = useState(0)

  useLayoutEffect(() => {
    const el = body.current
    if (!el) return
    if (atBottom.current) { el.scrollTop = el.scrollHeight; seen.current = story.length; setUnseen(0) }
    else setUnseen(Math.max(0, story.length - seen.current))
  }, [story.length])

  // a minute picked on a chart or the timeline: bring its messages into view
  useEffect(() => {
    if (scrollTo == null || !body.current) return
    const nodes = [...body.current.querySelectorAll('[data-tick]')]
    const hit = nodes.find((n) => +n.dataset.tick >= scrollTo || (n.dataset.to && +n.dataset.to >= scrollTo))
    if (hit) { atBottom.current = false; hit.scrollIntoView({ block: 'center', behavior: 'smooth' }) }
  }, [scrollTo])

  const onScroll = () => {
    const el = body.current
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    if (atBottom.current) { seen.current = story.length; setUnseen(0) }
  }
  const jump = () => { const el = body.current; el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }); atBottom.current = true; seen.current = story.length; setUnseen(0) }

  // which message is "active": the latest one at or before the focused minute
  let activeId = null
  if (focus != null) for (const m of story) { if (m.tick <= focus) activeId = m.id; else break }

  return (
    <section className="panel chat" aria-label="Negotiation chat">
      <header className="panel-head">
        <h2>Negotiation chat</h2>
        <span className="sub">{summaryOnly ? 'Summary mode at high speed' : 'Agents speak when something changes'}</span>
      </header>
      <div className="chat-body scroll" ref={body} onScroll={onScroll} onMouseLeave={() => onHover(null)}>
        {!story.length && <div className="chat-illo"><ChatIllo /><p>Each minute the four utilities bid for power, the market sets a price and the ledger commits the split. Start a run to watch.</p></div>}
        {story.map((m) => <Msg key={m.id} m={m} active={m.id === activeId} onHover={onHover} onPick={onPick} />)}
      </div>
      {unseen > 0 && <button className="new-pill" onClick={jump}>{unseen} new message{unseen > 1 ? 's' : ''} <span className="ms" aria-hidden="true">arrow_downward</span></button>}
    </section>
  )
}

export default memo(Chat)
