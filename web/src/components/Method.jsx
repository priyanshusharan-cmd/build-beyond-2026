import { useEffect } from 'react'

/**
 * One dialog explaining exactly how the two scoreboard numbers are produced.
 * Every formula here mirrors engine/blackout_arena (agents/*.py, fairness.py)
 * and config/damage.yaml, so a judge can check it against the code.
 */

const DAMAGE_ROWS = [
  ['Hospital', 10, 'd = σ(20·(u − 0.25)), rescaled to 0…1', 'Flat near zero until roughly 25% short, then a steep cliff — ICU load.'],
  ['Emergency', 5, 'd = u', 'Straight line: response capacity falls with the cut.'],
  ['Telecom', 3, 'd = 0.05·u while battery > 0, else 0.05·u + u', 'Battery absorbs the cut; damage jumps once it is empty.'],
  ['Water', 2, 'd = ((0.5 − L)/0.5)·max(u, 0.3) when u > 0 and L < 0.5', 'Reservoir level L absorbs the cut; no damage at all while L ≥ 0.5.'],
]

export default function MethodDialog({ onClose }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])

  return (
    <div className="scrim" role="presentation" onClick={onClose}>
      <div className="sheet method" role="dialog" aria-modal="true" aria-label="How damage and fairness are computed" onClick={(e) => e.stopPropagation()}>
        <h2>How these numbers are computed</h2>
        <p>Both come straight from the engine on the seed shown. Damage is a modeled proxy, not a real-world cost.</p>

        <section className="mth">
          <h3>Damage</h3>
          <p className="mth-lead">Each minute, each utility has a deficit <code>u = 1 − served / need</code>, between 0 and 1. Its damage <code>d</code> is a function of that deficit and of its own buffer:</p>
          <table className="mth-table">
            <thead><tr><th>Utility</th><th>Weight</th><th>Damage function</th></tr></thead>
            <tbody>
              {DAMAGE_ROWS.map(([name, w, f, why]) => (
                <tr key={name}>
                  <td><b>{name}</b></td>
                  <td className="num">{w}</td>
                  <td><code>{f}</code><small>{why}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mth-formula num">damage(minute) = Σ weightᵢ × dᵢ &nbsp;·&nbsp; total damage = Σ over all 480 minutes</p>
          <p className="mth-lead">Two cascades change the inputs rather than the formula: <b>A</b> — reservoir below 0.2 raises hospital need ×1.2; <b>B</b> — flat telecom battery multiplies emergency damage ×1.5. Lower total damage is better.</p>
        </section>

        <section className="mth">
          <h3>Fairness — Jain&apos;s index</h3>
          <p className="mth-lead">Per utility, satisfaction is the share of its need met, averaged over every minute so far:</p>
          <p className="mth-formula num">sᵢ = mean over ticks of clip(servedᵢ / needᵢ, 0, 1)</p>
          <p className="mth-formula num">J = (Σ sᵢ)² / (n · Σ sᵢ²) &nbsp;with n = 4</p>
          <p className="mth-lead">
            <b>J = 1.000</b> means all four met the same share of their need; the floor is <b>1/n = 0.250</b>, which is all power to one utility.
            It moves during the run because each sᵢ is a <em>running</em> time-average: a deep early cut keeps pulling J down after supply recovers, and J climbing back means the utilities that were cut are catching up.
          </p>
          <p className="mth-note">
            <span className="ms" aria-hidden="true">info</span>
            Jain&apos;s index is priority-blind on purpose. Cutting everyone equally scores 1.000 while doing far more damage, which is why the scoreboard reports damage and fairness side by side instead of one score.
          </p>
        </section>

        <div className="sheet-actions"><button className="btn filled" onClick={onClose}>Got it</button></div>
      </div>
    </div>
  )
}
