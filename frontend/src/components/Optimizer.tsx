import { useState } from 'react'
import { api } from '../api'
import type { CircuitSpec, OptimizeCandidate, OptimizeResult } from '../types'
import { CallBadge } from './CallBadge'
import { CircuitPreview } from './CircuitPreview'

const PROOF: Record<string, string> = {
  unitary: 'same gate for every input',
  state: 'same final state',
  outcomes: 'same measured odds',
  none: 'rejected',
}

function ProofBadge({ c }: { c: OptimizeCandidate }) {
  if (!c.proof) return <span className="badge mock">not usable</span>
  const level = c.proof.level
  return (
    <span className={`badge ${level === 'none' ? 'fail' : 'pass'}`} title={c.proof.detail}>
      <span className="dot" />{PROOF[level]}
    </span>
  )
}

/**
 * Find a shorter circuit: rewrite rules, the Qiskit transpiler and (live) Muse Spark each propose one,
 * and exact simulation proves each equal to the original or rejects it. "Use it" swaps it in (Undo restores).
 */
export function Optimizer({ spec, valid, onUse }: { spec: CircuitSpec; valid: boolean; onUse: (s: CircuitSpec) => void }) {
  const [res, setRes] = useState<{ for: string; r: OptimizeResult } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [used, setUsed] = useState<{ key: string; label: string } | null>(null)
  const key = JSON.stringify(spec)
  const inUse = used?.key === key
  const stale = !!res && res.for !== key && !inUse
  const run = () => {
    setBusy(true); setError(null)
    api.optimize(spec)
      .then((r) => { setRes({ for: key, r }); setOpen(r.best) })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false))
  }
  const r = res?.r
  const best = r && r.best !== null ? r.candidates[r.best] : null
  return (
    <div className="optimizer">
      <div className="row wrap" style={{ gap: 10 }}>
        <button className="btn" onClick={run} disabled={!valid || busy}>{busy ? 'Searching…' : r && !stale ? 'Search again' : 'Find a shorter circuit'}</button>
        <span className="sub">
          Rewrite rules, the Qiskit compiler and Muse Spark compete; exact simulation proves each answer or rejects it.
        </span>
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {r && (
        <div className={stale ? 'stale' : ''} style={{ marginTop: 12 }}>
          {stale && <div className="notice" style={{ marginBottom: 10 }}>The circuit changed since this search. Search again to optimise the new one.</div>}
          {inUse && <div className="notice" style={{ marginBottom: 10 }}>Now using the circuit from {used?.label}. Undo in the palette brings yours back.</div>}
          <p className="lead" style={{ marginBottom: 10 }}>{r.summary}</p>
          <div style={{ overflowX: 'auto' }}>
            <table className="data opt-table">
              <thead>
                <tr><th>Proposed by</th><th className="num">Gates</th><th className="num">Two-qubit</th><th className="num">Depth</th>
                  <th className="num" title="Match to the noiseless ideal on realistic hardware, exact">On hardware</th><th>Proof</th><th /></tr>
              </thead>
              <tbody>
                <tr className="muted-row">
                  <td>Your circuit</td><td className="num">{r.original.gates}</td><td className="num">{r.original.two_qubit}</td>
                  <td className="num">{r.original.depth}</td><td className="num">{r.original.fidelity?.toFixed(3) ?? '—'}</td><td /><td />
                </tr>
                {r.candidates.map((c, i) => (
                  <tr key={c.source} className={i === r.best ? 'chosen' : ''} onClick={() => setOpen(open === i ? null : i)} style={{ cursor: 'pointer' }}>
                    <td>
                      {c.label}
                      {c.call && <> <CallBadge call={c.call} showModel={false} /></>}
                      {c.attempts > 1 && <span className="sub"> · {c.attempts} tries</span>}
                    </td>
                    <td className="num">{c.cost ? <Delta now={c.cost.gates} was={r.original.gates} /> : '—'}</td>
                    <td className="num">{c.cost ? <Delta now={c.cost.two_qubit} was={r.original.two_qubit} /> : '—'}</td>
                    <td className="num">{c.cost?.depth ?? '—'}</td>
                    <td className="num">{c.cost?.fidelity?.toFixed(3) ?? '—'}</td>
                    <td><ProofBadge c={c} /></td>
                    <td className="num">
                      {c.better && c.spec && !stale && !inUse && (
                        <button className={`btn small ${i === r.best ? 'primary' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation()
                            setUsed({ key: JSON.stringify(c.spec), label: c.label })
                            onUse(c.spec as CircuitSpec)
                          }}>Use it</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.ai_note && <div className="sub" style={{ marginTop: 6 }}>{r.ai_note}</div>}
          {open !== null && r.candidates[open] && <Detail c={r.candidates[open]} />}
          {best?.spec && open === r.best && (
            <div className="opt-after">
              <div className="label" style={{ margin: '12px 0 4px' }}>{best.label}: the shorter circuit</div>
              <CircuitPreview spec={best.spec as CircuitSpec} highlight={null} onPick={() => {}} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Delta({ now, was }: { now: number; was: number }) {
  return (
    <span>
      {now}
      {now < was && <span className="delta down"> −{was - now}</span>}
      {now > was && <span className="delta up"> +{now - was}</span>}
    </span>
  )
}

/** The exact numbers behind the proof, only the ones that level claims. */
function proofNumbers(c: OptimizeCandidate): string {
  const p = c.proof
  if (!p) return ''
  const tvd = p.outcome_tvd < 1e-12 ? 'outcome distance < 1e-12' : `outcome distance ${p.outcome_tvd.toExponential(1)}`
  if (p.level === 'unitary' && p.process_fidelity !== null) return `process fidelity ${p.process_fidelity.toFixed(9)} · ${tvd}`
  if (p.level === 'state') return `state fidelity ${p.state_fidelity.toFixed(9)} · ${tvd}`
  return tvd
}

const LEVEL_LABEL: Record<string, string> = { 'any input': 'any input', 'from |0>': 'from |0…0⟩', 'measured odds': 'measured odds' }

function Detail({ c }: { c: OptimizeCandidate }) {
  return (
    <div className="opt-detail">
      {c.proof && (
        <div className="sub" style={{ marginBottom: 6 }}>
          <strong>{c.label}:</strong> {c.proof.detail}{' '}
          <span className="mono muted">{proofNumbers(c)}</span>
        </div>
      )}
      {c.note && <div className="sub" style={{ marginBottom: 6 }}>{c.note}</div>}
      {c.rewrites.length > 0 && (
        <ol className="rewrites">
          {c.rewrites.map((w, k) => (
            <li key={k}><span className={`badge ${w.level === 'any input' ? 'pass' : 'mock'}`}>{LEVEL_LABEL[w.level] ?? w.level}</span> {w.text}</li>
          ))}
        </ol>
      )}
    </div>
  )
}
