import { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api'
import type { CircuitSpec, DistributedResult, Examples } from '../types'
import { LineChart } from './Observatory'

const KMS = [0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30, 100]
const SAT_KMS = [600, 1200, 2000]
const fmtKm = (v: number) => (v < 1 ? `${Math.round(v * 1000)} m` : `${v.toLocaleString()} km`)
const fmtRate = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)} M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)} k` : v.toPrecision(3))
const fmtTime = (s: number) => (s < 1e-3 ? `${(s * 1e6).toFixed(1)} µs` : s < 1 ? `${(s * 1e3).toFixed(1)} ms` : `${s.toFixed(2)} s`)

/** Two chips and the link between them, the qubits on each, and how many CNOTs cross. */
function Chips({ r }: { r: DistributedResult }) {
  const W = 560, H = 150, cw = 190
  const link = r.options[0].link
  const dots = (qs: number[], x0: number) => qs.map((q, i) => {
    const cols = Math.min(3, qs.length), row = Math.floor(i / cols), col = i % cols
    return (
      <g key={q}>
        <circle cx={x0 + 40 + col * 55} cy={52 + row * 44} r={15} fill="var(--panel-3)" stroke="var(--text)" strokeWidth={1.4} />
        <text x={x0 + 40 + col * 55} y={56 + row * 44} textAnchor="middle" fontSize={11.5} fontFamily="var(--mono)" fill="var(--text)">q{q}</text>
      </g>
    )
  })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block' }} role="img"
      aria-label={`Chip A holds qubits ${r.best.chip_a.join(', ')}; chip B holds ${r.best.chip_b.join(', ')}; ${r.best.remote} CNOTs cross a ${link.label} link`}>
      {[0, W - cw].map((x, k) => (
        <g key={k}>
          <rect x={x + 1} y={18} width={cw - 2} height={H - 30} rx={12} fill="var(--panel-2)" stroke="var(--line-2)" />
          <text x={x + 14} y={12} fontSize={11} fill="var(--text-2)">{k ? 'Chip B' : 'Chip A'}</text>
        </g>
      ))}
      {dots(r.best.chip_a, 0)}
      {dots(r.best.chip_b, W - cw)}
      <line x1={cw} x2={W - cw} y1={H / 2 + 6} y2={H / 2 + 6} stroke="var(--gold)" strokeWidth={2} strokeDasharray={r.best.remote ? undefined : '4 4'} />
      <text x={W / 2} y={H / 2 - 4} textAnchor="middle" fontSize={11.5} fill="var(--text)">{r.best.remote} remote CNOT{r.best.remote === 1 ? '' : 's'}</text>
      <text x={W / 2} y={H / 2 + 24} textAnchor="middle" fontSize={10.5} fill="var(--text-2)">{link.label}</text>
      <text x={W / 2} y={H / 2 + 38} textAnchor="middle" fontSize={10.5} fill="var(--text-2)">pairs {link.fidelity.toFixed(3)} fidelity</text>
    </svg>
  )
}

/** One circuit on two small chips joined by a quantum link: where to cut, what each remote CNOT costs, and how the
 *  answer survives as the chips move apart. */
export function DistributedPanel({ examples, onOpen }: { examples: Examples | null; onOpen?: (s: CircuitSpec) => void }) {
  const circuits = useMemo(() => (examples?.specs ?? []).filter((s) => s.kind === 'circuit' && s.valid
    && (s.spec as CircuitSpec).num_qubits >= 3 && (s.spec as CircuitSpec).num_qubits <= 5), [examples])
  const [id, setId] = useState('teleportation')
  const [medium, setMedium] = useState<'fiber' | 'satellite'>('fiber')
  const [ki, setKi] = useState(4)
  const [si, setSi] = useState(1)
  const [r, setR] = useState<DistributedResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const km = medium === 'fiber' ? KMS[ki] : SAT_KMS[si]
  const spec = circuits.find((c) => c.id === id)?.spec as CircuitSpec | undefined
  useEffect(() => {
    if (!spec) return
    let live = true
    setBusy(true)
    const t = setTimeout(() => {
      api.distributed(spec, medium, km).then((res) => { if (live) { setR(res); setError(null) } })
        .catch((e) => { if (live) setError(e instanceof ApiError ? e.message : 'The run failed.') })
        .finally(() => { if (live) setBusy(false) })
    }, 150)
    return () => { live = false; clearTimeout(t) }
  }, [spec, medium, km])
  const o = r?.options[0]
  return (
    <div className="panel distributed">
      <div className="panel-head">
        <h2>Distributed quantum computer</h2>
        <span className="sub">one circuit across two linked chips</span>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        <span className="label">Circuit</span>
        {circuits.map((c) => (
          <button key={c.id} className={`chip-btn${id === c.id ? ' on' : ''}`} aria-pressed={id === c.id} onClick={() => setId(c.id)}>{c.title}</button>
        ))}
      </div>
      <div className="row wrap" style={{ gap: 10, marginTop: 10 }}>
        <div className="seg" role="group" aria-label="Link">
          <button className={medium === 'fiber' ? 'on' : ''} onClick={() => setMedium('fiber')}>Fiber</button>
          <button className={medium === 'satellite' ? 'on' : ''} onClick={() => setMedium('satellite')}>Satellite</button>
        </div>
        <span className="label">Distance</span>
        {medium === 'fiber'
          ? <input type="range" min={0} max={KMS.length - 1} value={ki} onChange={(e) => setKi(Number(e.target.value))} aria-label="Distance between the chips" style={{ flex: 1, minWidth: 160, maxWidth: 360 }} />
          : <div className="seg">{SAT_KMS.map((d, i) => <button key={d} className={si === i ? 'on' : ''} onClick={() => setSi(i)}>{d.toLocaleString()} km</button>)}</div>}
        <span className="mono sub" style={{ minWidth: 70 }}>{fmtKm(km)}</span>
        {busy && <span className="sub">simulating…</span>}
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {r && o && (
        <>
          <p className="obs-head" style={{ margin: '12px 0 6px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '86ch' }}>{r.finding}</p>
          <div className="dist-grid">
            <div>
              <Chips r={r} />
              <div className="mini-tiles">
                <span><b>{r.monolithic_fidelity.toFixed(3)}</b> one big chip</span>
                <span><b>{o.fidelity?.toFixed(3) ?? '–'}</b> two chips, today's qubits</span>
                <span><b>{o.fidelity_memory?.toFixed(3) ?? '–'}</b> with memory qubits</span>
                <span><b>{r.best.remote}</b> remote CNOTs (naive split {r.naive.remote})</span>
                <span><b>{fmtRate(o.link.pair_rate_hz)}</b> pairs/s</span>
                <span><b>{o.link.latency_us < 1000 ? `${o.link.latency_us.toFixed(1)} µs` : `${(o.link.latency_us / 1000).toFixed(1)} ms`}</b> wait per remote CNOT</span>
                {o.seconds_per_run !== null && <span><b>{fmtTime(o.seconds_per_run)}</b> of pairs per run</span>}
              </div>
              {o.note && <div className="notice" style={{ marginTop: 8 }}>{o.note}</div>}
              {onOpen && spec && <button className="btn small" style={{ marginTop: 8 }} onClick={() => onOpen(spec)}>Open the circuit in the editor</button>}
            </div>
            <LineChart xLog xLabel="distance between the chips, km" yLabel="process fidelity: how faithfully the pair of chips runs the circuit"
              yDomain={[0, 1]} fmtX={(v) => (v < 1 ? String(v) : v.toLocaleString())} fmtY={(v) => v.toFixed(2)} height={270}
              refs={[{ value: r.monolithic_fidelity, label: 'one big chip', axis: 'y' }, ...(medium === 'fiber' ? [{ value: km, label: fmtKm(km), axis: 'x' as const }] : [])]}
              aria="Process fidelity against distance: today's qubits fall off within a few kilometres as they wait for messages; long-lived memory qubits stay flat"
              lines={[
                { id: 'today', label: "Today's qubits (T2 80 µs)", points: r.sweep.map(([d, f]) => [d, f]), color: 'var(--primary)', labelAt: 'start' },
                { id: 'memory', label: 'Memory qubits (T2 1 s)', points: r.sweep.map(([d, , m]) => [d, m]), color: 'var(--predicted)', labelAt: 'start' },
              ]} />
          </div>
          <p className="sub obs-method">How it is computed: the circuit is compiled to CNOTs and one-qubit gates; every placement of its qubits on the two chips is tried and the one with the fewest crossing CNOTs wins.
            A crossing CNOT is done by gate teleportation (Eisert et al., 2000) with one Bell pair from the link model: with pair fidelity F it adds X on the target, Z on the control, or both, each with probability (1−F)/3;
            ancilla readout flips and the two extra local CNOTs are charged too, and every qubit idles under T1/T2 while a message crosses each way. Exact density matrices; process fidelity over all inputs
            (chance is {r.floor < 0.001 ? r.floor.toExponential(1) : r.floor.toFixed(3)}). Pairs are made just in time, so the pair rate sets the time per run.</p>
        </>
      )}
    </div>
  )
}
