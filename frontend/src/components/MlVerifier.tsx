import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { MlReport } from '../types'

/** Predicted against exact fidelity for held-out circuits: the ML verifier and the rule of thumb it replaces. */
function Scatter({ rows, showBase }: { rows: MlReport['scatter']; showBase: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(560)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.min(620, Math.round(e.contentRect.width)))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const H = Math.min(W, 420), L = 46, R = 14, T = 12, B = 38
  const x = (v: number) => L + v * (W - L - R)
  const y = (v: number) => T + (1 - v) * (H - T - B)
  const [hover, setHover] = useState<number | null>(null)
  const h = hover !== null ? rows[hover] : null
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  return (
    <div ref={box}>
      <div className="sub mono qaoa-readout" aria-live="polite">
        {h ? `exact ${h[0].toFixed(3)} · ML ${h[1].toFixed(3)} (off by ${Math.abs(h[1] - h[0]).toFixed(3)}) · rule of thumb ${h[2].toFixed(3)} (off by ${Math.abs(h[2] - h[0]).toFixed(3)})`
          : 'predicted fidelity against the exact answer, one dot per held-out circuit'}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ display: 'block', maxWidth: '100%', cursor: 'crosshair' }} role="img"
        aria-label="Scatter of predicted against exact fidelity: the ML verifier's dots hug the diagonal, the rule of thumb's fall well below it"
        onMouseLeave={() => setHover(null)}
        onPointerMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          const px = ((e.clientX - r.left) / r.width) * W, py = ((e.clientY - r.top) / r.height) * H
          let best = -1, dist = 400
          rows.forEach((p, i) => { const d = (x(p[0]) - px) ** 2 + (y(p[1]) - py) ** 2; if (d < dist) { dist = d; best = i } })
          setHover(best >= 0 ? best : null)
        }}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--line)" />
            <text x={L - 7} y={y(v) + 4} textAnchor="end" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{v}</text>
            <text x={x(v)} y={H - B + 16} textAnchor="middle" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{v}</text>
          </g>
        ))}
        <text x={W - R} y={H - 4} textAnchor="end" fontSize={11} fill="var(--text-2)">exact fidelity →</text>
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--text-2)" strokeDasharray="2 4" />
        <text x={x(0.04)} y={y(0.06) - 6} fontSize={11} fill="var(--text-2)" transform={`rotate(${-Math.atan((H - T - B) / (W - L - R)) * 180 / Math.PI} ${x(0.04)} ${y(0.06) - 6})`}>perfect prediction</text>
        {showBase && rows.map((p, i) => <circle key={`b${i}`} cx={x(p[0])} cy={y(p[2])} r={2.6} fill="none" stroke="var(--predicted)" strokeOpacity={0.7} strokeWidth={1.1} />)}
        {rows.map((p, i) => <circle key={`m${i}`} cx={x(p[0])} cy={y(p[1])} r={2.6} fill="var(--primary)" fillOpacity={0.85} />)}
        {h && <>
          <line x1={x(h[0])} x2={x(h[0])} y1={y(Math.min(h[1], h[2]))} y2={y(Math.max(h[1], h[2]))} stroke="var(--line-2)" />
          <circle cx={x(h[0])} cy={y(h[1])} r={5} fill="var(--primary)" stroke="var(--panel)" strokeWidth={2} />
          {showBase && <circle cx={x(h[0])} cy={y(h[2])} r={5} fill="var(--panel)" stroke="var(--predicted)" strokeWidth={2} />}
        </>}
      </svg>
      <div className="row wrap legend" style={{ gap: 14 }}>
        <span className="sub"><svg width={10} height={10} aria-hidden><circle cx={5} cy={5} r={4} fill="var(--primary)" /></svg> ML verifier</span>
        {showBase && <span className="sub"><svg width={10} height={10} aria-hidden><circle cx={5} cy={5} r={3.5} fill="none" stroke="var(--predicted)" strokeWidth={1.3} /></svg> rule of thumb (product of gate fidelities)</span>}
      </div>
    </div>
  )
}

export function MlVerifierView() {
  const [r, setR] = useState<MlReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showBase, setShowBase] = useState(true)
  useEffect(() => { api.mlReport().then(setR).catch((e: Error) => setError(e.message)) }, [])
  if (error) return <div className="notice error">{error}</div>
  if (!r) return <div className="sub">Loading the model report…</div>
  const m = r.metrics as Record<string, number>
  const factor = m.test_mae_baseline / m.test_mae_ml
  return (
    <>
      <div className="obs-head">
        <h3>ML verifier: noise predicted in microseconds, then checked exactly</h3>
        <p>On {m.test} held-out circuits a neural network predicts how much of the answer survives today's noise with an average error of {m.test_mae_ml.toFixed(3)}: {factor.toFixed(0)} times
          smaller than the usual rule of thumb ({m.test_mae_baseline.toFixed(3)}) and better than a global-depolarizing physics model ({m.test_mae_depolarizing.toFixed(3)}), in about {Math.round(m.predict_us)} µs instead of {m.exact_ms_mean.toFixed(0)} ms.
          Its 90% interval held for {(m.test_coverage * 100).toFixed(0)}% of them, and for {(m.gallery_coverage * 100).toFixed(0)}% of the {m.gallery_cases} textbook cases it never saw. Every prediction up to 10 qubits is still checked against the exact answer.</p>
      </div>
      <div className="mini-tiles" style={{ marginBottom: 10 }}>
        <span><b>{m.test_mae_ml.toFixed(3)}</b> ML error, held out</span>
        <span><b>{m.test_mae_depolarizing.toFixed(3)}</b> physics model</span>
        <span><b>{m.test_mae_baseline.toFixed(3)}</b> rule of thumb</span>
        <span><b>{(m.test_coverage * 100).toFixed(0)}%</b> inside the 90% interval</span>
        <span><b>{m.gallery_mae_ml.toFixed(3)}</b> ML error, textbook circuits (physics model {m.gallery_mae_depolarizing.toFixed(3)}, rule of thumb {m.gallery_mae_baseline.toFixed(3)})</span>
        <span><b>{Math.round(m.exact_ms_mean * 1000 / m.predict_us)}×</b> faster than exact</span>
      </div>
      <label className="row sub" style={{ gap: 6, marginBottom: 4 }}>
        <input type="checkbox" checked={showBase} onChange={(e) => setShowBase(e.target.checked)} /> show the rule of thumb
      </label>
      <Scatter rows={r.scatter} showBase={showBase} />
      <details className="obs-table">
        <summary className="sub">Textbook circuits it never saw ({r.gallery.length} cases)</summary>
        <div className="obs-table-scroll">
          <table>
            <thead><tr><th style={{ textAlign: 'left' }}>circuit</th><th>noise</th><th>exact</th><th>ML ± interval</th><th>physics model</th><th>rule of thumb</th></tr></thead>
            <tbody>{r.gallery.map((g, i) => (
              <tr key={i}><td style={{ textAlign: 'left' }}>{g.circuit}</td><td>{g.scale}×</td><td>{g.exact.toFixed(3)}</td>
                <td>{g.ml.toFixed(3)} ± {g.half_width.toFixed(3)}{Math.abs(g.ml - g.exact) <= g.half_width ? '' : ' ⚠'}</td><td>{g.depolarizing.toFixed(3)}</td><td>{g.baseline.toFixed(3)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </details>
      <p className="sub obs-method">How it is computed: {m.samples} random circuits of {r.metrics.trained_qubits} qubits (gate soup, layered entanglers, mirror circuits, reversible logic) at noise from 0.05× to 5×
        the realistic preset, each labelled by exact density-matrix simulation; 16 inputs (size, depth, the ideal distribution's spread, the rule of thumb, and the physics model: exact readout errors and global depolarizing applied to the ideal odds); five tanh networks in NumPy; adaptive split-conformal
        intervals from {m.calibration} calibration circuits nobody trained on. scripts/train_ml_verifier.py rebuilds it.</p>
    </>
  )
}
