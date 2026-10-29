import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Amplitude, CircuitSpec, LiveState } from '../types'
import { pct } from '../util'
import { BlochSphere } from './Bloch'
import { EntanglementWeb } from './EntanglementWeb'

/** Phase in units of pi, e.g. "π/2", "-π/4", "0". */
export function phaseText(phase: number): string {
  const k = phase / Math.PI
  if (Math.abs(k) < 1e-3) return '0'
  for (const d of [1, 2, 4, 8, 3, 6]) {
    const n = Math.round(k * d)
    if (Math.abs(k * d - n) < 1e-3) return `${n < 0 ? '-' : ''}${Math.abs(n) === 1 ? '' : Math.abs(n)}π${d === 1 ? '' : `/${d}`}`
  }
  return `${k.toFixed(2)}π`
}

/** Basis states with probability bars and a phase dial each (phase relative to the largest amplitude). */
export function AmplitudeTable({ amps, hidden = 0, max = 16 }: { amps: Amplitude[]; hidden?: number; max?: number }) {
  const shown = amps.slice(0, max)
  const rest = hidden + amps.slice(max).reduce((t, a) => t + a.probability, 0)
  return (
    <>
      <table className="amps">
        <tbody>
          {shown.map((a) => (
            <tr key={a.basis}>
              <td className="mono">|{a.basis}⟩</td>
              <td style={{ width: '100%' }}>
                <div className="amp-track"><div className="amp-bar" style={{ width: `${Math.max(1.5, a.probability * 100)}%` }} /></div>
              </td>
              <td className="num">{pct(a.probability)}</td>
              <td className="num">
                <svg width={18} height={18} aria-hidden="true" style={{ verticalAlign: -4 }}>
                  <circle cx={9} cy={9} r={7.5} fill="none" stroke="var(--line-2)" />
                  <line x1={9} y1={9} x2={9 + 7 * Math.cos(a.phase)} y2={9 - 7 * Math.sin(a.phase)} stroke="var(--text)"
                    strokeWidth={1.6} strokeLinecap="round" style={{ transition: 'all .2s ease' }} />
                </svg>
              </td>
              <td className="mono muted" style={{ whiteSpace: 'nowrap' }}>{phaseText(a.phase)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rest > 1e-6 && <div className="sub">+ {pct(rest)} spread over smaller amplitudes</div>}
    </>
  )
}

/** The exact final state, recomputed on every edit: Bloch spheres with each qubit's path, and the amplitudes. */
export function LiveStrip({ spec, valid }: { spec: CircuitSpec; valid: boolean }) {
  const [live, setLive] = useState<LiveState | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!valid) return
    const ctl = new AbortController()
    const t = setTimeout(() => {
      api.state(spec, 'realistic', undefined, ctl.signal)
        .then((s) => { setLive(s); setError(null) })
        .catch((e: Error) => { if (!ctl.signal.aborted) setError(e.message) })
    }, 90)
    return () => { clearTimeout(t); ctl.abort() }
  }, [spec, valid])
  if (!live) return error ? <div className="notice error" style={{ marginTop: 12 }}>{error}</div> : null
  const last = live.steps[live.steps.length - 1]
  const n = last.bloch.length
  const ent = last.entangled.filter(Boolean).length
  return (
    <div className={`live-strip ${valid ? '' : 'stale'}`}>
      <div className="row wrap" style={{ gap: 8, marginBottom: 8 }}>
        <span className="label">Live state</span>
        <span className="sub">
          {valid ? 'exact, recomputed as you edit' : 'fix the spec to update'} · {last.amplitudes.length} basis state{last.amplitudes.length === 1 ? '' : 's'}
          {ent >= 2 && <> · <span className="gold">{ent} qubits entangled</span></>}
        </span>
      </div>
      <div className="live-grid">
        <div className="spheres">
          {Array.from({ length: n }, (_, q) => (
            <BlochSphere key={q} vec={last.bloch[q]} entangled={last.entangled[q]} label={`q${q}`} size={96}
              trail={live.steps.map((s) => s.bloch[q])} />
          ))}
        </div>
        <div style={{ minWidth: 0 }}><AmplitudeTable amps={last.amplitudes} hidden={last.hidden_probability} max={8} /></div>
        {n >= 2 && n <= 8 && <EntanglementWeb step={last} size={140} />}
      </div>
    </div>
  )
}
