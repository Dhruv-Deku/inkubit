import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { DecoderReport } from '../types'
import { LineChart } from './Observatory'

const ERR = ['', 'X', 'Y', 'Z']
const SUP = '⁰¹²³⁴⁵⁶⁷⁸⁹'
const pctTxt = (v: number) => `${+(v * 100).toPrecision(2)}%`
/** 0.00297 -> "3.0 × 10⁻³" */
const sci = (v: number) => {
  const e = Math.floor(Math.log10(v))
  return `${(v / 10 ** e).toFixed(1)} × 10⁻${String(-e).split('').map((c) => SUP[+c]).join('')}`
}

/** One sampled shot on the d x d lattice: the errors that happened, the checks that fired, and both verdicts. */
function Lattice({ ex }: { ex: DecoderReport['example'] }) {
  const d = ex.d, S = d === 3 ? 52 : 40, O = 36
  const pos = (q: number) => [O + (q % d) * S, O + Math.floor(q / d) * S] as const
  const kinds = Array.from({ length: d * d }, (_, q) => ex.errors.map((r) => r[q]).filter((k) => k > 0))
  const firedZ = ex.z_checks.map((_, c) => ex.dz.some((r) => r[c] === 1))
  const firedX = ex.x_checks.map((_, c) => ex.dx.some((r) => r[c] === 1))
  const edge = O + (d - 1) * S
  const centre = (qs: number[]) => {
    const ps = qs.map(pos)
    let x = ps.reduce((s, p) => s + p[0], 0) / ps.length, y = ps.reduce((s, p) => s + p[1], 0) / ps.length
    if (qs.length === 2) {
      if (ps[0][1] === ps[1][1]) y += ps[0][1] === O ? -S / 3 : ps[0][1] === edge ? S / 3 : 0
      else x += ps[0][0] === O ? -S / 3 : ps[0][0] === edge ? S / 3 : 0
    }
    return [x, y] as const
  }
  const W = 2 * O + (d - 1) * S
  return (
    <svg viewBox={`0 0 ${W} ${W}`} width={W} style={{ maxWidth: '100%' }} role="img" aria-label={`Distance-${d} surface code lattice for one shot`}>
      {[...ex.x_checks.map((c, i) => ({ c, i, t: 'X' })), ...ex.z_checks.map((c, i) => ({ c, i, t: 'Z' }))].map(({ c, i, t }) => {
        const [x, y] = centre(c)
        const fired = t === 'Z' ? firedZ[i] : firedX[i]
        return (
          <g key={t + i}>
            <rect x={x - 9} y={y - 9} width={18} height={18} rx={4} fill={fired ? (t === 'Z' ? '#d95926' : '#3987e5') : 'var(--panel-3)'} stroke="var(--line-2)" />
            <text x={x} y={y + 4} textAnchor="middle" fontSize={10} fill={fired ? '#fff' : 'var(--muted)'} fontFamily="var(--mono)">{t}</text>
          </g>
        )
      })}
      {Array.from({ length: d * d }, (_, q) => {
        const [x, y] = pos(q)
        const k = kinds[q]
        return (
          <g key={q}>
            <circle cx={x} cy={y} r={d === 3 ? 12 : 10} fill={k.length ? 'var(--gold)' : 'var(--panel-2)'} stroke="var(--text-2)" strokeWidth={1.2} />
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
  const [dist, setDist] = useState(3)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.decoder(p, seed, dist).then((x) => { setR(x); setError(null) }).catch((e) => setError(e instanceof ApiError ? e.message : 'Failed.')) }, [p, seed, dist])
  const at = r?.curve.find((c) => Math.abs(c.p - 0.01) < 1e-9)
  const ex = r?.example
  const d5 = r?.d5
  const at5 = d5?.curve.find((c) => Math.abs(c.p - 0.01) < 1e-9)
  const below = d5?.curve.filter((c) => (c.lam ?? 0) > 1) ?? []
  const above = d5?.curve.filter((c) => (c.lam ?? 0) < 1) ?? []
  const nnWins = d5?.curve.filter((c) => c.paired_z > 1.96).length ?? 0
  const last5 = d5?.curve[d5.curve.length - 1]
  return (
    <div className="panel decoder">
      <div className="panel-head">
        <h2>ML error-correction decoder</h2>
        <span className="sub">surface code, distance 3 and 5</span>
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
                  {d5 && <div className="seg" role="group" aria-label="Code distance">{[3, 5].map((v) => <button key={v} className={dist === v ? 'on' : ''} aria-pressed={dist === v} onClick={() => setDist(v)}>d = {v}</button>)}</div>}
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
                <p className="sub">Gold: data qubits hit by X, Y or Z errors over the {ex.d === 3 ? 3 : 5} rounds. Orange Z checks and blue X checks fired at least once.</p>
              </div>
            )}
          </div>
          <p className="sub obs-method">How it is computed: rotated surface code, 9 data qubits, Z-basis memory over 3 rounds with phenomenological noise (each data qubit X, Y or Z with p/3 per round, each check flipped with p, readout flips p),
            sampled exactly. Matching: exact minimum-weight perfect matching on the space-time graph of Z-check events. Neural: a 25-128-128-1 network in NumPy trained on {r.train_shots.toLocaleString()} fresh shots at
            noise from {r.train_p[0] * 100}% to {r.train_p[r.train_p.length - 1] * 100}%, with every detection event and log p as input; both scored on the same 200,000 new shots per point. scripts/train_decoder.py rebuilds it.</p>
          {d5 && at5 && at5.lam !== null && (
            <div className="d5">
              <h3 style={{ margin: '18px 0 4px' }}>Distance 5: a bigger code, below threshold</h3>
              <p className="obs-head" style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '88ch' }}>
                At 1% noise per round, distance 5 lets through {sci(at5.per_round_d5)} logical errors per round against {sci(at5.per_round_d3)} at distance 3:
                a suppression of <b>Λ = {at5.lam.toFixed(1)}</b>{below.length && above.length
                  ? `; the curves cross between ${pctTxt(below[below.length - 1].p)} and ${pctTxt(above[0].p)} noise, the threshold above which a bigger code makes things worse`
                  : last5 && last5.lam !== null ? `, shrinking towards 1 as the noise nears threshold (Λ = ${last5.lam.toFixed(2)} at ${pctTxt(last5.p)})` : ''}.
                Google's Willow chip measured Λ = 2.14 on real hardware in 2024. {nnWins >= Math.ceil(d5.curve.length / 2)
                  ? `On top of matching, a network that also sees where both kinds of matching put their corrections (a qubit in both is a Y error, invisible to matching on one kind) makes ${Math.round((1 - at5.neural / at5.d5) * 100)}% fewer logical errors at 1% noise: on the same shots it fixes ${at5.fixes} that matching gets wrong and breaks ${at5.breaks} (paired test z = ${at5.paired_z.toFixed(1)}), significant at ${nnWins} of ${d5.curve.length} noise levels.`
                  : `On top of matching, a network that also sees both matchings' corrections is significantly better (paired test) at only ${nnWins} of ${d5.curve.length} noise levels.`}</p>
              <LineChart xLog yLog xLabel="physical error per round, p" yLabel="logical error per round" fmtX={(v) => pctTxt(v)}
                fmtY={(v) => `${+(v * 100).toPrecision(2)}%`} height={280}
                aria="Logical error per round against physical error on log scales: below threshold distance 5 lies below distance 3, above it the order flips"
                lines={[{ id: 'bare5', label: 'Bare qubit (X or Y error, 2p/3)', points: d5.curve.map((c) => [c.p, (2 * c.p) / 3]), color: 'var(--text-2)', dash: '6 4' },
                  { id: 'd3', label: 'Distance 3, matching', points: d5.curve.map((c) => [c.p, c.per_round_d3]), color: 'var(--predicted)', dash: '3 3', markers: true },
                  { id: 'd5', label: 'Distance 5, matching', points: d5.curve.map((c) => [c.p, c.per_round_d5]), color: 'var(--predicted)', markers: true },
                  { id: 'd5nn', label: 'Distance 5, network on matching', points: d5.curve.map((c) => [c.p, c.per_round_neural]), color: 'var(--primary)', markers: true }]} labels={false} />
              <p className="sub obs-method">Distance 5: 25 data qubits, 12 X and 12 Z checks, 5 rounds (distance 3: 3 rounds), the same noise; per-round error from 1 − 2P = (1 − 2e)^rounds. Matching: PyMatching on the same graph and weights,
                equal to the exact matcher on every one of 20,000 distance-3 shots (tested). Network: 172-256-256-1, trained on {d5.train_shots.toLocaleString()} fresh shots (none seen twice); input: every event of both kinds, where each matching put its corrections, matching's verdict and log p
                (a first version without the corrections only learned to copy matching);
                {' '}{d5.curve[0].shots.toLocaleString()} to {d5.curve[d5.curve.length - 1].shots.toLocaleString()} new shots per point. scripts/train_decoder_d5.py rebuilds it.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
