import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { DecoderReport } from '../types'
import { LineChart } from './Observatory'

const Z_CHECKS = [[1, 2, 4, 5], [3, 4, 6, 7], [0, 3], [5, 8]]
const X_CHECKS = [[0, 1, 3, 4], [4, 5, 7, 8], [1, 2], [6, 7]]
const ERR = ['', 'X', 'Y', 'Z']

/** One sampled shot on the 3x3 lattice: the errors that happened, the checks that fired, and both verdicts. */
function Lattice({ ex }: { ex: DecoderReport['example'] }) {
  const S = 52, O = 40
  const pos = (q: number) => [O + (q % 3) * S, O + Math.floor(q / 3) * S] as const
  const kinds = Array.from({ length: 9 }, (_, q) => ex.errors.map((r) => r[q]).filter((k) => k > 0))
  const firedZ = Z_CHECKS.map((_, c) => ex.dz.some((r) => r[c] === 1))
  const firedX = X_CHECKS.map((_, c) => ex.dx.some((r) => r[c] === 1))
  const centre = (qs: number[]) => {
    const ps = qs.map(pos)
    let x = ps.reduce((s, p) => s + p[0], 0) / ps.length, y = ps.reduce((s, p) => s + p[1], 0) / ps.length
    if (qs.length === 2) { if (ps[0][1] === ps[1][1]) y += ps[0][1] === O ? -S / 3 : S / 3; else x += ps[0][0] === O ? -S / 3 : S / 3 }
    return [x, y] as const
  }
  return (
    <svg viewBox={`0 0 ${2 * O + 2 * S} ${2 * O + 2 * S}`} width={2 * O + 2 * S} style={{ maxWidth: '100%' }} role="img" aria-label="Surface code lattice for one shot">
      {[...X_CHECKS.map((c, i) => ({ c, i, t: 'X' })), ...Z_CHECKS.map((c, i) => ({ c, i, t: 'Z' }))].map(({ c, i, t }) => {
        const [x, y] = centre(c)
        const fired = t === 'Z' ? firedZ[i] : firedX[i]
        return (
          <g key={t + i}>
            <rect x={x - 9} y={y - 9} width={18} height={18} rx={4} fill={fired ? (t === 'Z' ? '#d95926' : '#3987e5') : 'var(--panel-3)'} stroke="var(--line-2)" />
            <text x={x} y={y + 4} textAnchor="middle" fontSize={10} fill={fired ? '#fff' : 'var(--muted)'} fontFamily="var(--mono)">{t}</text>
          </g>
        )
      })}
      {Array.from({ length: 9 }, (_, q) => {
        const [x, y] = pos(q)
        const k = kinds[q]
        return (
          <g key={q}>
            <circle cx={x} cy={y} r={12} fill={k.length ? 'var(--gold)' : 'var(--panel-2)'} stroke="var(--text-2)" strokeWidth={1.2} />
            <text x={x} y={y + 4} textAnchor="middle" fontSize={10} fill={k.length ? '#16171b' : 'var(--muted)'} fontFamily="var(--mono)">{k.length ? k.map((v) => ERR[v]).join('') : q}</text>
          </g>
        )
      })}
    </svg>
  )
}

export function DecoderPanel() {
  const [r, setR] = useState<DecoderReport | null>(null)
  const [p, setP] = useState(0.02)
  const [seed, setSeed] = useState(1)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.decoder(p, seed).then((x) => { setR(x); setError(null) }).catch((e) => setError(e instanceof ApiError ? e.message : 'Failed.')) }, [p, seed])
  const at = r?.curve.find((c) => Math.abs(c.p - 0.01) < 1e-9)
  const ex = r?.example
  return (
    <div className="panel decoder">
      <div className="panel-head">
        <h2>ML error-correction decoder</h2>
        <span className="sub">the distance-3 surface code: minimum-weight matching against a neural network that sees both kinds of checks</span>
      </div>
      {error && <div className="notice error">{error}</div>}
      {r && at && (
        <>
          <p className="obs-head" style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '88ch' }}>
            At 1% physical error per round the neural decoder lets through {(at.neural * 100).toFixed(2)}% logical errors against {(at.mwpm * 100).toFixed(2)}% for matching
            ({Math.round((1 - at.neural / at.mwpm) * 100)}% fewer, each ±{(at.neural_ci * 100).toFixed(2)} at 95%) and {(at.unprotected * 100).toFixed(2)}% for a bare qubit. Y errors fire both kinds of check at once;
            matching reads only one kind, the network learned to use both, the reason learned decoders such as AlphaQubit beat matching.</p>
          <div className="dist-grid">
            <LineChart xLog yLog xLabel="physical error per round, p" yLabel="logical error after 3 rounds" fmtX={(v) => `${+(v * 100).toPrecision(2)}%`}
              fmtY={(v) => `${+(v * 100).toPrecision(3)}%`} height={280}
              aria="Logical error against physical error on log scales: the neural decoder lies below matching at every noise level, both below the bare qubit at low noise"
              lines={[{ id: 'bare', label: 'Bare qubit', points: r.curve.map((c) => [c.p, c.unprotected]), color: 'var(--text-2)', dash: '6 4' },
                { id: 'mwpm', label: 'Matching (MWPM)', points: r.curve.map((c) => [c.p, c.mwpm]), color: 'var(--predicted)', markers: true },
                { id: 'nn', label: 'Neural decoder', points: r.curve.map((c) => [c.p, c.neural]), color: 'var(--primary)', markers: true }]} labels={false} />
            {ex && (
              <div>
                <div className="row wrap" style={{ gap: 8 }}>
                  <span className="label">One shot at p</span>
                  {[0.01, 0.02, 0.04].map((v) => <button key={v} className={`chip-btn${p === v ? ' on' : ''}`} onClick={() => setP(v)}>{v * 100}%</button>)}
                  <button className="btn small" onClick={() => setSeed((s) => s + 1)}>New shot</button>
                </div>
                <div className="row wrap" style={{ gap: 16, alignItems: 'center', marginTop: 8 }}>
                  <Lattice ex={ex} />
                  <div className="mini-tiles col">
                    <span>logical flipped: <b>{ex.flip ? 'yes' : 'no'}</b></span>
                    <span>matching says <b className={ex.mwpm === ex.flip ? 'good' : ''}>{ex.mwpm ? 'flip' : 'no flip'}</b> {ex.mwpm === ex.flip ? '✓' : '✕'}</span>
                    <span>neural says <b className={ex.neural === ex.flip ? 'good' : ''}>{ex.neural ? 'flip' : 'no flip'}</b> {ex.neural === ex.flip ? '✓' : '✕'}</span>
                  </div>
                </div>
                <p className="sub">Gold: data qubits hit by X, Y or Z errors over the 3 rounds. Orange Z checks and blue X checks fired at least once.</p>
              </div>
            )}
          </div>
          <p className="sub obs-method">How it is computed: rotated surface code, 9 data qubits, Z-basis memory over 3 rounds with phenomenological noise (each data qubit X, Y or Z with p/3 per round, each check flipped with p, readout flips p),
            sampled exactly. Matching: exact minimum-weight perfect matching on the space-time graph of Z-check events. Neural: a 25-128-128-1 network in NumPy trained on {r.train_shots.toLocaleString()} fresh shots at
            noise from {r.train_p[0] * 100}% to {r.train_p[r.train_p.length - 1] * 100}%, with every detection event and log p as input; both scored on the same 200,000 new shots per point. scripts/train_decoder.py rebuilds it.</p>
        </>
      )}
    </div>
  )
}
