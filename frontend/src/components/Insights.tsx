import { useEffect, useState } from 'react'
import type { CircuitInsights, CircuitSpec, Entanglement, ErrorBudget, Mitigation, NoiseSweep, StepState } from '../types'
import { downloadText, pct } from '../util'
import { CircuitPreview } from './CircuitPreview'

/** Phase in units of pi, e.g. "π/2", "-π/4", "0". */
function phaseText(phase: number): string {
  const k = phase / Math.PI
  if (Math.abs(k) < 1e-3) return '0'
  for (const d of [1, 2, 4, 8, 3, 6]) {
    const n = Math.round(k * d)
    if (Math.abs(k * d - n) < 1e-3) return `${n < 0 ? '-' : ''}${Math.abs(n) === 1 ? '' : Math.abs(n)}π${d === 1 ? '' : `/${d}`}`
  }
  return `${k.toFixed(2)}π`
}

/** One qubit's Bloch sphere, drawn in a fixed oblique view; a shorter arrow means it is entangled or noisy. */
export function BlochSphere({ vec, entangled, label, size = 104 }: {
  vec: [number, number, number]; entangled: boolean; label: string; size?: number
}) {
  const c = size / 2, r = size * 0.36
  const [x, y, z] = vec
  const px = c + r * 0.94 * (y - 0.36 * x)
  const py = c + r * (-0.94 * z + 0.24 * x)
  const len = Math.hypot(x, y, z)
  const ink = entangled ? 'var(--gold)' : 'var(--primary)'
  return (
    <figure className="bloch" style={{ margin: 0 }}>
      <svg width={size} height={size} role="img" aria-label={`${label} Bloch vector x ${x.toFixed(2)}, y ${y.toFixed(2)}, z ${z.toFixed(2)}`}>
        <circle cx={c} cy={c} r={r} fill="var(--panel-2)" stroke="var(--line-2)" />
        <ellipse cx={c} cy={c} rx={r} ry={r * 0.3} fill="none" stroke="var(--line-2)" strokeDasharray="3 3" />
        <line x1={c} x2={c} y1={c - r} y2={c + r} stroke="var(--line-2)" />
        <text x={c} y={c - r - 4} textAnchor="middle" fontSize={10} fill="var(--muted)" fontFamily="var(--mono)">|0⟩</text>
        <text x={c} y={c + r + 12} textAnchor="middle" fontSize={10} fill="var(--muted)" fontFamily="var(--mono)">|1⟩</text>
        {len > 0.02 && <line x1={c} y1={c} x2={px} y2={py} stroke={ink} strokeWidth={2.4} strokeLinecap="round" />}
        <circle cx={len > 0.02 ? px : c} cy={len > 0.02 ? py : c} r={4.5} fill={ink} stroke="var(--panel)" strokeWidth={1.5} />
      </svg>
      <figcaption>
        <span className="mono">{label}</span>
        <span className={entangled ? 'gold' : 'muted'}>{entangled ? `entangled · ${len.toFixed(2)}` : len > 0.999 ? 'pure' : len.toFixed(2)}</span>
      </figcaption>
    </figure>
  )
}

function stepNote(s: StepState, prev?: StepState): string {
  const now = s.entangled.flatMap((e, q) => (e ? [q] : []))
  const before = new Set(prev?.entangled.flatMap((e, q) => (e ? [q] : [])) ?? [])
  const fresh = now.filter((q) => !before.has(q))
  if (fresh.length && now.length >= 2) return `${now.map((q) => `q${q}`).join(', ')} are now entangled: their arrows shrink because no qubit has a state of its own any more.`
  if (!now.length && before.size) return 'The entanglement has been undone: every qubit has its own state again.'
  const sup = s.amplitudes.length
  if (s.step === 0) return 'Every qubit starts in |0⟩: one basis state with certainty.'
  if (sup === 1) return `The register is in a single basis state, |${s.amplitudes[0].basis}⟩.`
  return `The register is in a superposition of ${sup}${s.hidden_probability > 1e-6 ? '+' : ''} basis states.`
}

/** Step through the circuit gate by gate: amplitudes, phases and one Bloch sphere per qubit. */
export function StepInspector({ spec, steps }: { spec: CircuitSpec; steps: StepState[] }) {
  const [i, setI] = useState(steps.length - 1)
  const [playing, setPlaying] = useState(false)
  useEffect(() => { setI(steps.length - 1) }, [steps])
  useEffect(() => {
    if (!playing) return
    const t = setTimeout(() => (i < steps.length - 1 ? setI(i + 1) : setPlaying(false)), 1100)
    return () => clearTimeout(t)
  }, [playing, i, steps.length])
  const s = steps[Math.min(i, steps.length - 1)]
  if (!s) return null
  const n = s.bloch.length
  return (
    <div className="inspector">
      <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
        <button className="btn small" disabled={i === 0} onClick={() => { setPlaying(false); setI(i - 1) }} aria-label="Previous step">◀</button>
        <button className="btn small" onClick={() => { if (i === steps.length - 1) setI(0); setPlaying(!playing) }}>{playing ? 'Pause' : 'Play'}</button>
        <button className="btn small" disabled={i === steps.length - 1} onClick={() => { setPlaying(false); setI(i + 1) }} aria-label="Next step">▶</button>
        <input type="range" min={0} max={steps.length - 1} value={i} onChange={(e) => { setPlaying(false); setI(Number(e.target.value)) }}
          aria-label="Step" style={{ flex: 1, minWidth: 140 }} />
        <span className="sub mono">step {s.step} of {steps.length - 1}</span>
      </div>
      <div className="step-title"><strong>{s.label}</strong><span className="sub">{stepNote(s, steps[i - 1])}</span></div>
      <CircuitPreview spec={spec} highlight={s.op_index === null ? null : `operations[${s.op_index}]`} onPick={() => {}} />
      <div className="inspector-grid">
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Amplitudes <span className="muted">(phase relative to the largest)</span></div>
          <table className="amps">
            <tbody>
              {s.amplitudes.map((a) => (
                <tr key={a.basis}>
                  <td className="mono">|{a.basis}⟩</td>
                  <td style={{ width: '100%' }}>
                    <div className="amp-track"><div className="amp-bar" style={{ width: `${Math.max(1.5, a.probability * 100)}%` }} /></div>
                  </td>
                  <td className="num">{pct(a.probability)}</td>
                  <td className="num">
                    <svg width={18} height={18} aria-hidden="true" style={{ verticalAlign: -4 }}>
                      <circle cx={9} cy={9} r={7.5} fill="none" stroke="var(--line-2)" />
                      <line x1={9} y1={9} x2={9 + 7 * Math.cos(a.phase)} y2={9 - 7 * Math.sin(a.phase)} stroke="var(--text)" strokeWidth={1.6} strokeLinecap="round" />
                    </svg>
                  </td>
                  <td className="mono muted" style={{ whiteSpace: 'nowrap' }}>{phaseText(a.phase)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {s.hidden_probability > 1e-6 && <div className="sub">+ {pct(s.hidden_probability)} spread over smaller amplitudes</div>}
        </div>
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Each qubit on its own</div>
          <div className="spheres">
            {Array.from({ length: n }, (_, q) => <BlochSphere key={q} vec={s.bloch[q]} entangled={s.entangled[q]} label={`q${q}`} />)}
          </div>
        </div>
      </div>
    </div>
  )
}

export function EntanglementPanel({ ent }: { ent: Entanglement }) {
  return (
    <div className="panel">
      <div className="panel-head"><h2>Entanglement</h2><span className="sub">concurrence: 0 none, 1 maximal</span></div>
      <p className="lead">{ent.summary}</p>
      {ent.pairs.length > 0 ? (
        <table className="data">
          <thead><tr><th>Pair</th><th>Ideal</th><th>With noise</th><th className="num">Kept</th></tr></thead>
          <tbody>
            {ent.pairs.slice(0, 6).map((p) => (
              <tr key={`${p.a}-${p.b}`}>
                <td className="mono">q{p.a} – q{p.b}</td>
                <td><Meter v={p.ideal} label={p.ideal.toFixed(2)} outline /></td>
                <td>{p.noisy === null ? <span className="muted">—</span> : <Meter v={p.noisy} label={p.noisy.toFixed(2)} />}</td>
                <td className="num">{p.noisy === null || !p.ideal ? '—' : pct(p.noisy / p.ideal, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : ent.qubit_entropy.some((e) => e > 0.01) && (
        <table className="data">
          <thead><tr><th>Qubit</th><th>Entanglement entropy with the rest</th></tr></thead>
          <tbody>
            {ent.qubit_entropy.map((e, q) => (
              <tr key={q}><td className="mono">q{q}</td><td><Meter v={e} label={`${e.toFixed(2)} bit`} /></td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function Meter({ v, label, outline }: { v: number; label: string; outline?: boolean }) {
  return (
    <div className="meter">
      <div className="meter-track">
        <div className="meter-bar" style={{ width: `${Math.max(2, Math.min(1, v) * 100)}%`, ...(outline ? { background: 'rgba(217,164,65,0.18)', boxShadow: 'inset 0 0 0 1.5px var(--gold)' } : {}) }} />
      </div>
      <span className="mono">{label}</span>
    </div>
  )
}

export function ErrorBudgetPanel({ budget }: { budget: ErrorBudget }) {
  const max = Math.max(1e-4, ...budget.items.map((i) => i.fidelity_loss))
  return (
    <div className="panel">
      <div className="panel-head"><h2>Error budget</h2><span className="sub">match lost to each noise source on its own</span></div>
      <p className="lead">{budget.summary}</p>
      <div className="budget">
        {budget.items.map((it) => (
          <div key={it.source} className="budget-row" title={`${it.label}: ${pct(it.fidelity_loss, 2)}`}>
            <span>{it.label}</span>
            <div className="budget-track"><div className="budget-bar" style={{ width: `${(it.fidelity_loss / max) * 100}%` }} /></div>
            <span className="num mono">{pct(it.fidelity_loss)}</span>
          </div>
        ))}
        <div className="budget-row total"><span>All together</span><span /><span className="num mono">{pct(budget.total_loss)}</span></div>
      </div>
    </div>
  )
}

const SW = 640, SH = 230, SP = { l: 46, r: 16, t: 14, b: 38 }

/** Match to the ideal as hardware noise is scaled down or up from today's preset. */
export function SweepChart({ sweep }: { sweep: NoiseSweep }) {
  const [tip, setTip] = useState<number | null>(null)
  const pts = sweep.points
  const lo = Math.max(0, Math.floor((Math.min(sweep.target, ...pts.map((p) => p.fidelity)) - 0.02) * 20) / 20)
  const xs = (k: number) => SP.l + (k / (pts.length - 1)) * (SW - SP.l - SP.r)
  const ys = (f: number) => SP.t + (1 - (f - lo) / (1 - lo)) * (SH - SP.t - SP.b)
  // position of a scale between the sampled categories (log interpolation)
  const xScale = (s: number) => {
    for (let k = 0; k < pts.length - 1; k++) {
      const a = pts[k].scale, b = pts[k + 1].scale
      if (s >= a && s <= b) {
        const t = a > 0 ? Math.log(s / a) / Math.log(b / a) : s / b
        return xs(k + Math.max(0, Math.min(1, t)))
      }
    }
    return xs(pts.length - 1)
  }
  const today = pts.findIndex((p) => p.scale === 1)
  const path = pts.map((p, k) => `${k ? 'L' : 'M'}${xs(k)} ${ys(p.fidelity)}`).join('')
  const ticks = [lo, (lo + 1) / 2, 1]
  const hit = sweep.scale_for_target
  return (
    <div className="panel">
      <div className="panel-head"><h2>How good must the hardware be?</h2><span className="sub">same circuit, noise scaled from today's {sweep.baseline.replace('_', ' ')} level</span></div>
      <p className="lead">{sweep.summary}</p>
      <div style={{ position: 'relative', maxWidth: 900 }}>
        <svg viewBox={`0 0 ${SW} ${SH}`} width="100%" style={{ maxWidth: 900, display: 'block' }} role="img" aria-label="Match to the ideal against noise scale">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={SP.l} x2={SW - SP.r} y1={ys(t)} y2={ys(t)} stroke="var(--line)" />
              <text x={SP.l - 8} y={ys(t) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">{pct(t, 0)}</text>
            </g>
          ))}
          <line x1={SP.l} x2={SW - SP.r} y1={ys(sweep.target)} y2={ys(sweep.target)} stroke="var(--pass)" strokeDasharray="5 4" />
          <text x={SW - SP.r} y={ys(sweep.target) - 6} textAnchor="end" fontSize={11} fill="var(--pass)">{pct(sweep.target, 0)} target</text>
          {today >= 0 && (
            <g>
              <line x1={xs(today)} x2={xs(today)} y1={SP.t} y2={SH - SP.b} stroke="var(--line-2)" strokeDasharray="3 3" />
              <text x={xs(today) + 5} y={SP.t + 10} fontSize={11} fill="var(--text-2)">today</text>
            </g>
          )}
          {hit !== null && (
            <g>
              <line x1={xScale(hit)} x2={xScale(hit)} y1={ys(sweep.target)} y2={SH - SP.b} stroke="var(--pass)" strokeWidth={1.2} />
              <text x={xScale(hit)} y={SH - SP.b - 6} textAnchor="middle" fontSize={11} fill="var(--pass)">{Number(hit.toPrecision(2))}×</text>
            </g>
          )}
          <path d={path} fill="none" stroke="var(--primary)" strokeWidth={2} />
          {pts.map((p, k) => (
            <g key={p.scale} onMouseEnter={() => setTip(k)} onMouseLeave={() => setTip(null)}>
              <rect x={xs(k) - 18} y={SP.t} width={36} height={SH - SP.t - SP.b} fill="transparent" />
              <circle cx={xs(k)} cy={ys(p.fidelity)} r={tip === k ? 5.5 : 4} fill="var(--primary)" stroke="var(--panel)" strokeWidth={2} />
              <text x={xs(k)} y={SH - SP.b + 18} textAnchor="middle" fontSize={11} fill="var(--text-2)">{p.scale}×</text>
            </g>
          ))}
          <text x={(SW + SP.l) / 2} y={SH - 4} textAnchor="middle" fontSize={11} fill="var(--muted)">noise relative to today (lower is better hardware)</text>
        </svg>
        {tip !== null && (
          <div className="chart-tip" style={{ position: 'absolute', left: `${(Math.min(xs(tip) + 12, SW - 170) / SW) * 100}%`, top: `${((ys(pts[tip].fidelity) - 10) / SH) * 100}%` }}>
            <div className="mono" style={{ marginBottom: 4 }}>{pts[tip].scale}× today's noise</div>
            <div className="r"><span>Match to ideal</span><span>{pct(pts[tip].fidelity)}</span></div>
            {pts[tip].success !== null && <div className="r"><span>Right answer</span><span>{pct(pts[tip].success ?? 0)}</span></div>}
          </div>
        )}
      </div>
    </div>
  )
}

export function ReadoutPanel({ m }: { m: Mitigation }) {
  return (
    <div className="panel">
      <div className="panel-head"><h2>Readout correction</h2><span className="sub">inverting the known readout error</span></div>
      <div className="tiles" style={{ gridTemplateColumns: 'repeat(2, 1fr)', marginTop: 0, marginBottom: 10 }}>
        <div className="tile"><div className="k">Match to ideal, as measured</div><div className="v">{m.fidelity_raw.toFixed(3)}</div></div>
        <div className="tile"><div className="k">After readout correction</div><div className="v good">{m.fidelity_corrected.toFixed(3)}</div></div>
      </div>
      <p className="lead" style={{ marginBottom: 0 }}>{m.summary}</p>
    </div>
  )
}

export function ExportButtons({ ins, spec }: { ins?: CircuitInsights; spec: CircuitSpec }) {
  const base = (spec.metadata?.title || 'circuit').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'circuit'
  return (
    <>
      {ins && <button className="btn small" onClick={() => downloadText(`${base}.qasm`, ins.exports.qasm2)}>OpenQASM 2</button>}
      {ins && <button className="btn small" onClick={() => downloadText(`${base}_v3.qasm`, ins.exports.qasm3)}>OpenQASM 3</button>}
      <button className="btn small" onClick={() => downloadText(`${base}.spec.json`, JSON.stringify(spec, null, 2))}>Spec JSON</button>
    </>
  )
}

/** Everything the exact analyses found, below the verified result (or in the editor before a run). */
export function InsightsSection({ spec, ins, wide = false }: { spec: CircuitSpec; ins: CircuitInsights; wide?: boolean }) {
  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head"><h2>Inside the circuit, gate by gate</h2><span className="sub">exact ideal state after every step</span></div>
        <StepInspector spec={spec} steps={ins.steps} />
      </div>
      <div className={wide ? 'two-col' : 'stack'}>
        {ins.entanglement && <EntanglementPanel ent={ins.entanglement} />}
        {ins.budget && <ErrorBudgetPanel budget={ins.budget} />}
      </div>
      {ins.sweep && <SweepChart sweep={ins.sweep} />}
      {ins.mitigation && <ReadoutPanel m={ins.mitigation} />}
      {ins.notes.map((t, k) => <div key={k} className="notice">{t}</div>)}
    </div>
  )
}
