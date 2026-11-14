import { AGENTS, CASCADE_TEXT, chaosText, fmt, statusOf } from './lib.js'

/**
 * Turns per-minute rows into a continuous chat. Agents only speak when something changes:
 * a shock, a grant move > 2 MW, a status change, a buffer crossing 50/25/10%, a cascade or chaos.
 * Quiet minutes collapse into one grey line. Fixed templates filled with real numbers (no LLM).
 * Pure and deterministic: same rows => same messages, so it can be recomputed on every render.
 */
const BUF_LEVELS = [0.5, 0.25, 0.1]
const pc = (x) => `${Math.round(x * 100)}%`
const chip = (kind, label) => ({ kind, label })

function agentLine(a, r, why) {
  const g = r.grants[a], need = r.need[a], short = Math.max(0, need - g), s = r.served_pct[a]
  const st = statusOf(r, a)
  const chips = []
  let text
  if (a === 'hospital') {
    if (short < 0.5) text = r.thread.cascades.includes('A') || need > 40
      ? `ICU load is spiking. I need the full ${fmt(need, 0)} MW, and I'm getting it.`
      : `All ${fmt(need, 0)} MW covered. The ICU is humming along.`
    else if (s >= 0.75) text = `I can live with ${fmt(g)} of ${fmt(need, 0)} MW for now. Under a quarter short, the ICU holds.`
    else text = `Only ${fmt(g)} of ${fmt(need, 0)} MW. ICU is past the cliff, I need power now!`
    if (s < 0.75) chips.push(chip('urgent', 'Critical'))
  } else if (a === 'water') {
    const L = r.reservoir
    if (short < 0.5) text = L < 0.95 ? `Fully served, refilling. Reservoir's at ${pc(L)}.` : `Tanks are full and I've got my ${fmt(need, 0)} MW. All good here.`
    else if (L > 0.3) { text = `Reservoir's at ${pc(L)}. I can wait, take ${fmt(short)} MW.`; chips.push(chip('wait', 'Can wait'), chip('yield', `Yielding ${fmt(short, 0)} MW`)) }
    else { text = `Reservoir's down to ${pc(L)}. Pressure's getting scary, I need my share back.`; chips.push(chip('urgent', 'Urgent')) }
  } else if (a === 'telecom') {
    const B = r.battery
    if (short < 0.5) text = B < 0.95 ? `Back on grid power, charging up. Battery at ${pc(B)}.` : `Towers powered, battery full. Everyone can call home.`
    else if (B > 0.25) { text = `Battery's at ${pc(B)}. I'll ride it out, take ${fmt(short)} MW.`; chips.push(chip('wait', 'Can wait'), chip('yield', `Yielding ${fmt(short, 0)} MW`)) }
    else if (B > 0) { text = `Battery's down to ${pc(B)}. I can't hold much longer.`; chips.push(chip('urgent', 'Urgent')) }
    else { text = `Battery's empty. Towers are going dark.`; chips.push(chip('urgent', 'Critical')) }
  } else {
    const towersDown = r.battery <= 0.001 && r.served_pct.telecom < 0.95
    if (towersDown) { text = `Towers are down, so our crews can't coordinate.`; chips.push(chip('urgent', 'Urgent')) }
    else if (short < 0.5) text = `All ${fmt(need, 0)} MW in. Crews are rolling.`
    else { text = `Running on ${fmt(g)} of ${fmt(need, 0)} MW. Response times are slipping.`; if (s < 0.6) chips.push(chip('urgent', 'Urgent')) }
  }
  if (st === 'degraded' && !chips.some((c) => c.kind === 'urgent')) chips.push(chip('degraded', 'Degraded'))
  if (st === 'down') chips.push(chip('shock', 'Down'))
  return { who: a, text, chips, why }
}

export function buildStory(rows, { strategy = 'ours', summaryOnly = false } = {}) {
  const out = []
  let quiet = null
  const last = { grant: {}, status: {}, spokeAt: {}, price: null, res: 1, bat: 1 }
  const flushQuiet = () => {
    if (!quiet) return
    out.push({ id: `q${quiet.from}`, kind: 'quiet', tick: quiet.from, to: quiet.to, t: quiet.t, tTo: quiet.tTo, allServed: quiet.allServed })
    quiet = null
  }
  const crossed = (prev, now) => BUF_LEVELS.find((lv) => prev > lv && now <= lv)

  rows.forEach((r, i) => {
    const th = r.thread
    const msgs = []
    const add = (m) => msgs.push({ ...m, tick: r.tick, t: r.t, id: `${r.tick}-${msgs.length}` })
    const neg = th.rounds.length > 0

    for (const c of th.chaos) {
      const t = chaosText(c)
      add({ who: 'chaos', text: `${t.title}. ${t.body}.`, chips: [chip('shock', c.source === 'live' ? 'Chaos' : 'Shock')] })
    }
    const spoke = []
    if (i === 0) {
      add({ who: 'market', text: neg ? `Morning, everyone. ${fmt(r.supply, 0)} MW on the grid, you need ${fmt(r.needTotal, 0)}. Bids open.` : `${fmt(r.supply, 0)} MW on the grid. No bidding in this mode: ${strategyRule(strategy)}.`, chips: [] })
      AGENTS.forEach((a) => { add(agentLine(a, r)); spoke.push(a) })
    } else if (!summaryOnly) {
      if (neg && last.price != null && Math.abs(r.price - last.price) > Math.max(0.03, last.price * 0.2)) {
        const up = r.price > last.price
        add({ who: 'market', text: up ? `Too much demand. Price up to ${fmt(r.price, 2)}.` : `Demand eased. Price down to ${fmt(r.price, 2)}.`, chips: [] })
        last.price = r.price
      }
      AGENTS.forEach((a) => {
        // a grant shift only counts if it is > 2 MW and the agent hasn't spoken in the last 10 minutes
        const moved = Math.abs(r.grants[a] - (last.grant[a] ?? r.grants[a])) > 2 && r.tick - (last.spokeAt[a] ?? -99) >= 10
        const stChanged = statusOf(r, a) !== last.status[a]
        const buf = a === 'water' ? crossed(last.res, r.reservoir) : a === 'telecom' ? crossed(last.bat, r.battery) : null
        if (moved || stChanged || buf) { add(agentLine(a, r)); spoke.push(a) }
      })
    } else {
      AGENTS.forEach((a) => { if (statusOf(r, a) !== last.status[a]) { add(agentLine(a, r)); spoke.push(a) } })
    }
    for (const c of th.cascades) {
      const t = CASCADE_TEXT[c] ?? { title: `Cascade ${c}`, body: '' }
      add({ who: 'chaos', text: `${t.title}. ${t.body}`, chips: [chip('shock', 'Cascade')] })
    }
    const rejected = th.ledger.find((l) => l.type === 'REJECTED')
    if (r.used_fallback || rejected) {
      add({ who: 'ledger', text: `${rejected ? `That proposal broke the rules (${rejected.reasons?.join(', ') ?? 'invalid'}). ` : 'Negotiation ran out of rounds. '}Applying the safe fallback split.`, chips: [chip('degraded', 'Fallback')] })
    } else if (spoke.length >= 2 || (i === 0)) {
      add({ who: 'ledger', text: `${fmt(r.granted)} of ${fmt(r.supply)} MW. Checks out, committed.`, chips: [] })
    }

    if (msgs.length) {
      flushQuiet()
      out.push(...msgs)
    } else {
      const allServed = AGENTS.every((a) => r.served_pct[a] >= 0.95)
      if (quiet && quiet.allServed === allServed) { quiet.to = r.tick; quiet.tTo = r.t }
      else { flushQuiet(); quiet = { from: r.tick, to: r.tick, t: r.t, tTo: r.t, allServed } }
    }
    AGENTS.forEach((a) => {
      if (spoke.includes(a) || last.grant[a] == null) { last.grant[a] = r.grants[a]; last.spokeAt[a] = r.tick }
      last.status[a] = statusOf(r, a)
    })
    if (last.price == null && neg) last.price = r.price
    last.res = r.reservoir; last.bat = r.battery
  })
  flushQuiet()
  return out
}

function strategyRule(s) {
  return { priority: 'hospital first, then emergency, telecom, water', proportional: 'everyone gets cut by the same share', blind: 'everyone grabs their full need' }[s] ?? 'fixed rule'
}
