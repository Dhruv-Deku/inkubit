import { useEffect, useState } from 'react'
import { api } from '../api'
import type { CircuitInsights, CircuitSpec, Entanglement, ErrorBudget, LiveState, Mitigation, NoiseSweep, StepState, ZeroNoise } from '../types'
import { downloadText, pct } from '../util'
import { BlochSphere } from './Bloch'
import { CircuitPreview } from './CircuitPreview'
import { EntanglementWeb } from './EntanglementWeb'
import { BellPanel, ShorPanel, TomographyPanel } from './Labs'
import { Histogram } from './Histogram'
import { AmplitudeTable } from './LiveState'

export { BlochSphere }

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
      <div className="step-title"><strong>{s.label}</strong><span className="sub">{stepNote(s, steps[i - 1])}</span>
        {s.dirac && <span className="ket" title="The state in Dirac notation (qubit 0 is the rightmost digit)">{s.dirac}</span>}</div>
      <CircuitPreview spec={spec} highlight={s.op_index === null ? null : `operations[${s.op_index}]`} onPick={() => {}} />
      <div className="inspector-grid">
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Amplitudes <span className="muted">(phase relative to the largest)</span></div>
          <AmplitudeTable amps={s.amplitudes} hidden={s.hidden_probability} />
        </div>
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Each qubit on its own <span className="muted">(drag to turn; the trail is its path so far)</span></div>
          <div className="spheres">
            {Array.from({ length: n }, (_, q) => (
              <BlochSphere key={q} vec={s.bloch[q]} entangled={s.entangled[q]} label={`q${q}`} size={112}
                trail={steps.slice(0, i + 1).map((t) => t.bloch[q])} />
            ))}
          </div>
          {n >= 2 && n <= 8 && (
            <>
              <div className="label" style={{ margin: '12px 0 4px' }}>Who is entangled with whom <span className="muted">(gold threads: pairs; arcs: entanglement with the rest)</span></div>
              <EntanglementWeb step={s} size={150} />
            </>
          )}
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
      <div className="panel-head"><h2>Error budget</h2><span className="sub">match lost to each noise source</span></div>
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

/** Slider position 0..120 -> noise scale: 0 is perfect hardware, 80 is today, 120 is ten times worse. */
const sliderScale = (k: number) => (k <= 0 ? 0 : Math.pow(10, (k - 80) / 40))
function scaleText(s: number): string {
  if (s === 0) return 'perfect hardware'
  if (Math.abs(s - 1) < 0.02) return "today's noise"
  return s < 1 ? `${Number((1 / s).toPrecision(2))}× better hardware` : `${Number(s.toPrecision(2))}× today's noise`
}

/** Drag the hardware quality and watch the outcome odds change (exact, from the spec). */
function WhatIf({ spec, baseline, onScale }: { spec: CircuitSpec; baseline: string; onScale: (s: number | null) => void }) {
  const [k, setK] = useState(80)
  const [live, setLive] = useState<LiveState | null>(null)
  const scale = sliderScale(k)
  useEffect(() => {
    const ctl = new AbortController()
    const t = setTimeout(() => {
      api.state(spec, baseline, scale, ctl.signal).then(setLive).catch(() => { /* superseded, or the backend is away */ })
    }, 40)
    return () => { clearTimeout(t); ctl.abort() }
  }, [spec, baseline, scale])
  useEffect(() => () => onScale(null), [])
  const noisy = live?.noisy
  return (
    <div className="whatif">
      <div className="row wrap" style={{ gap: 12 }}>
        <span className="label">What if the hardware were better?</span>
        <input type="range" min={0} max={120} value={k} aria-label="Noise level"
          onChange={(e) => { const v = Number(e.target.value); setK(v); onScale(sliderScale(v)) }} style={{ flex: 1, minWidth: 180 }} />
        <span className="mono whatif-scale">{scaleText(scale)}</span>
      </div>
      {noisy && live?.ideal && (
        <>
          <div className="row wrap" style={{ gap: 18, margin: '10px 0 4px' }}>
            <span className="sub">Match to ideal <strong className="mono" style={{ color: noisy.fidelity >= 0.99 ? 'var(--pass)' : 'var(--text)' }}>{pct(noisy.fidelity, 2)}</strong></span>
            {noisy.success !== null && <span className="sub">Right answer <strong className="mono">{pct(noisy.success, 1)}</strong></span>}
          </div>
          <Histogram predicted={noisy.distribution} ideal={live.ideal} predictedLabel={`Exact odds with ${scaleText(scale)}`} />
        </>
      )}
    </div>
  )
}

/** Match to the ideal as hardware noise is scaled down or up from today's preset. */
export function SweepChart({ sweep, spec }: { sweep: NoiseSweep; spec?: CircuitSpec }) {
  const [tip, setTip] = useState<number | null>(null)
  const [probe, setProbe] = useState<number | null>(null)
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
          {probe !== null && probe <= pts[pts.length - 1].scale && (
            <line x1={xScale(probe)} x2={xScale(probe)} y1={SP.t} y2={SH - SP.b} stroke="var(--text)" strokeWidth={1.2} />
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
      {spec && <WhatIf spec={spec} baseline={sweep.baseline} onScale={setProbe} />}
    </div>
  )
}

export function LayoutsPanel({ ins }: { ins: CircuitInsights }) {
  if (!ins.layouts.length) return null
  return (
    <div className="panel">
      <div className="panel-head"><h2>On real chip layouts</h2><span className="sub">routed by Qiskit</span></div>
      <p className="lead">{ins.layout_summary}</p>
      <table className="data">
        <thead><tr><th>Wiring</th><th className="num">Depth</th><th className="num">CNOTs</th><th className="num">Extra SWAPs</th><th className="num">Rough success</th></tr></thead>
        <tbody>
          {ins.layouts.map((l) => (
            <tr key={l.layout}>
              <td><strong>{l.layout}</strong> <span className="sub">{l.description}</span></td>
              <td className="num">{l.depth}</td>
              <td className="num">{l.two_qubit_gates}</td>
              <td className="num">{l.swaps_added}</td>
              <td className="num">{pct(l.estimated_success, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="sub" style={{ marginTop: 6 }}>Rough success multiplies gate and readout fidelities and ignores decoherence; the verified numbers above are exact.</div>
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

/** Probability of the ideal answer at 1x, 3x, 5x noise, the parabola through them, and where it meets zero noise. */
function ZneChart({ z }: { z: ZeroNoise }) {
  const W = 520, H = 204, L = 44, R = 16, T = 28, B = 34
  const xs = z.scales, ys = z.outcome_at
  const all = [...ys, z.outcome_zero, z.outcome_ideal]
  const lo = Math.max(0, Math.min(...all) - 0.04), hi = Math.min(1, Math.max(...all) + 0.03)
  const xMax = Math.max(...xs) + 0.5
  const px = (x: number) => L + (x / xMax) * (W - L - R)
  const py = (y: number) => T + ((hi - y) / (hi - lo)) * (H - T - B)
  // the Lagrange parabola through the three points; at x = 0 it equals the Richardson value
  const quad = (x: number) => xs.reduce((acc, xi, i) => acc + ys[i] * xs.reduce((p, xj, j) => (j === i ? p : p * ((x - xj) / (xi - xj))), 1), 0)
  const path = (from: number, to: number, k = 40) =>
    Array.from({ length: k + 1 }, (_, i) => { const x = from + ((to - from) * i) / k; return `${i ? 'L' : 'M'}${px(x).toFixed(1)} ${py(quad(x)).toFixed(1)}` }).join('')
  const ticks = [lo, (lo + hi) / 2, hi].map((t) => Math.round(t * 100) / 100)
  const tick = (t: number) => `${Math.round(t * 100)}%`
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block' }} role="img"
      aria-label={`Probability of ${z.outcome}: ${ys.map((y, i) => `${pct(y)} at ${xs[i]}x noise`).join(', ')}; extrapolated to ${pct(z.outcome_zero)} at zero noise; ideal ${pct(z.outcome_ideal)}`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={py(t)} y2={py(t)} stroke="var(--line)" />
          <text x={L - 6} y={py(t) + 4} textAnchor="end" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{tick(t)}</text>
        </g>
      ))}
      <line x1={L} x2={W - R} y1={py(z.outcome_ideal)} y2={py(z.outcome_ideal)} stroke="var(--text-2)" strokeDasharray="2 4" />
      <text x={W - R} y={py(z.outcome_ideal) - 5} textAnchor="end" fontSize={10.5} fill="var(--text-2)">noiseless ideal</text>
      <path d={path(xs[0], xs[xs.length - 1])} fill="none" stroke="var(--measured)" strokeWidth={2} />
      <path d={path(0, xs[0], 12)} fill="none" stroke="var(--measured)" strokeWidth={2} strokeDasharray="4 4" />
      {xs.map((x, i) => (
        <g key={x}>
          <circle cx={px(x)} cy={py(ys[i])} r={5} fill="var(--measured)" stroke="var(--panel)" strokeWidth={2}><title>{`${x}x noise: ${pct(ys[i])}`}</title></circle>
          <text x={px(x)} y={H - B + 16} textAnchor="middle" fontSize={11} fill="var(--text-2)" fontFamily="var(--mono)">{x}x</text>
        </g>
      ))}
      <circle cx={px(0)} cy={py(z.outcome_zero)} r={6} fill="var(--panel)" stroke="var(--text)" strokeWidth={2}><title>{`extrapolated to zero noise: ${pct(z.outcome_zero)}`}</title></circle>
      <text x={px(0) + 10} y={py(z.outcome_zero) - 10} fontSize={11} fill="var(--text)">zero noise: {pct(z.outcome_zero)}</text>
      <text x={px(0)} y={H - B + 16} textAnchor="middle" fontSize={11} fill="var(--text-2)" fontFamily="var(--mono)">0</text>
      <text x={(L + W - R) / 2} y={H - 4} textAnchor="middle" fontSize={11} fill="var(--muted)">noise level (every gate folded into G·G⁻¹·G)</text>
    </svg>
  )
}

export function ZnePanel({ z }: { z: ZeroNoise }) {
  return (
    <div className="panel">
      <div className="panel-head"><h2>Zero-noise extrapolation</h2><span className="sub">noisier on purpose, then back to zero</span></div>
      <div className="tiles zne-tiles">
        <div className="tile"><div className="k">As measured</div><div className="v">{z.fidelity_raw.toFixed(3)}</div><div className="s">match to the ideal</div></div>
        <div className="tile"><div className="k">Readout corrected</div><div className="v">{z.fidelity_readout.toFixed(3)}</div></div>
        <div className="tile"><div className="k">Extrapolated (exact)</div><div className="v good">{z.fidelity_mitigated.toFixed(3)}</div></div>
        <div className="tile"><div className="k">With {z.shots.toLocaleString()} shots per level</div><div className="v">{z.fidelity_shots.toFixed(3)}</div>
          <div className="s">vs {z.fidelity_readout_shots.toFixed(3)} without</div></div>
      </div>
      <div className="label" style={{ marginBottom: 4 }}>Probability of |{z.outcome}⟩ as the noise is raised</div>
      <ZneChart z={z} />
      <p className="lead" style={{ margin: '10px 0 0' }}>{z.summary}</p>
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
        <div className="panel-head"><h2>Inside the circuit, gate by gate</h2><span className="sub">exact state after each gate</span></div>
        <StepInspector spec={spec} steps={ins.steps} />
      </div>
      <div className={wide ? 'two-col' : 'stack'}>
        {ins.entanglement && <EntanglementPanel ent={ins.entanglement} />}
        {ins.budget && <ErrorBudgetPanel budget={ins.budget} />}
      </div>
      {ins.factoring && <ShorPanel lab={ins.factoring} title="From counts to factors" sub="Shor's algorithm: the classical finish for every reading"
        shotsLabel={ins.factoring.shots ? `this run's ${ins.factoring.shots.toLocaleString()} shots` : 'this run'} />}
      {ins.bell && <BellPanel bell={ins.bell} />}
      {ins.tomography && <TomographyPanel tomo={ins.tomography} />}
      {ins.sweep && <SweepChart sweep={ins.sweep} spec={spec} />}
      <LayoutsPanel ins={ins} />
      {ins.mitigation && <ReadoutPanel m={ins.mitigation} />}
      {ins.zne && <ZnePanel z={ins.zne} />}
      {ins.notes.map((t, k) => <div key={k} className="notice">{t}</div>)}
    </div>
  )
}
