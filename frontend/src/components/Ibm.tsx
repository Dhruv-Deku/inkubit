import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { CircuitSpec, IbmAdvice, IbmExperiments, IbmQubit, IbmRun, IbmSnapshot, IbmStatus } from '../types'

type Metric = 'readout' | 'two_qubit' | 't1' | 't2'
const METRICS: { id: Metric; label: string }[] = [
  { id: 'two_qubit', label: 'two-qubit gate error' }, { id: 'readout', label: 'readout error' },
  { id: 't1', label: 'T1' }, { id: 't2', label: 'T2' },
]
const UNUSABLE = 0.5
const pct = (x: number | null | undefined, d = 2) => (x == null ? '–' : `${(x * 100).toFixed(d)}%`)
const readout = (q: IbmQubit) => (q.p01 == null || q.p10 == null ? null : (q.p01 + q.p10) / 2)

/** Bad is hot: a neutral grey for the best values on the chip, orange for the worst (log scale for errors). */
function ramp(values: number[], higherIsBetter: boolean) {
  const good = values.filter((v) => Number.isFinite(v) && v > 0).sort((a, b) => a - b)
  const lo = good[Math.floor(good.length * 0.05)] ?? 1e-4
  const hi = good[Math.floor(good.length * 0.95)] ?? 1e-1
  const f = (v: number) => {
    const t = higherIsBetter ? (hi - v) / (hi - lo) : Math.log(v / lo) / Math.log(hi / lo)
    return Math.max(0, Math.min(1, t))
  }
  return (v: number | null) => {
    if (v == null || !Number.isFinite(v)) return '#2a2c31'
    const t = f(v)
    const mix = (a: number, b: number) => Math.round(a + (b - a) * t)
    return `rgb(${mix(64, 217)}, ${mix(68, 89)}, ${mix(78, 38)})`  // #40444e → #d95926
  }
}

function ChipMap({ snap, metric, highlight }: { snap: IbmSnapshot; metric: Metric; highlight: number[] | null }) {
  const sx = 34, sy = 26, pad = 18
  const xs = snap.coords.map((c) => c[0]), ys = snap.coords.map((c) => c[1])
  const w = (Math.max(...xs) - Math.min(...xs)) * sx + pad * 2, h = (Math.max(...ys) - Math.min(...ys)) * sy + pad * 2
  const X = (q: number) => (snap.coords[q][0] - Math.min(...xs)) * sx + pad
  const Y = (q: number) => (snap.coords[q][1] - Math.min(...ys)) * sy + pad
  const qVal = (q: IbmQubit) => (metric === 't1' ? q.t1_us : metric === 't2' ? q.t2_us : readout(q))
  const qColor = ramp(snap.qubits.map((q) => qVal(q) ?? NaN), metric === 't1' || metric === 't2')
  const eColor = ramp(Object.values(snap.edges).filter((e) => e < UNUSABLE), false)
  const hl = new Set(highlight ?? [])
  const hlEdge = (a: number, b: number) => hl.has(a) && hl.has(b)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img"
      aria-label={`${snap.device} coupling map coloured by ${metric}`}>
      {Object.entries(snap.edges).map(([k, err]) => {
        const [a, b] = k.split('-').map(Number)
        const bad = err >= UNUSABLE
        return (
          <line key={k} x1={X(a)} y1={Y(a)} x2={X(b)} y2={Y(b)} strokeWidth={hlEdge(a, b) ? 6 : 4} strokeLinecap="round"
            stroke={hlEdge(a, b) ? 'var(--primary)' : bad ? '#e5484d' : metric === 'two_qubit' ? eColor(err) : '#3a3d45'}
            strokeDasharray={bad ? '3 3' : undefined}>
            <title>{`coupler ${a}–${b}: ${snap.two_qubit_gate.toUpperCase()} error ${pct(err, 3)}${bad ? ' (unusable)' : ''}`}</title>
          </line>
        )
      })}
      {snap.qubits.map((q, i) => (
        <g key={i}>
          <circle cx={X(i)} cy={Y(i)} r={hl.has(i) ? 9 : 7.5}
            fill={metric === 'two_qubit' ? '#2f3138' : qColor(qVal(q))}
            stroke={hl.has(i) ? 'var(--primary)' : '#111214'} strokeWidth={hl.has(i) ? 2.5 : 1}>
            <title>{`qubit ${i}: readout ${pct(readout(q))}, sx error ${pct(q.sx_error, 3)}, T1 ${q.t1_us?.toFixed(0) ?? '–'} µs, T2 ${q.t2_us?.toFixed(0) ?? '–'} µs`}</title>
          </circle>
          {hl.has(i) && <text x={X(i)} y={Y(i) + 3} textAnchor="middle" fontSize={8} fill="#fff" pointerEvents="none">{i}</text>}
        </g>
      ))}
    </svg>
  )
}

/** The IBM quantum computers the account can use: calibration maps, the placement advisor and real experiments. */
export function IbmPanel({ spec }: { spec: CircuitSpec | null }) {
  const [status, setStatus] = useState<IbmStatus | null>(null)
  const [device, setDevice] = useState<string | null>(null)
  const [snap, setSnap] = useState<IbmSnapshot | null>(null)
  const [metric, setMetric] = useState<Metric>('two_qubit')
  const [advice, setAdvice] = useState<IbmAdvice[] | null>(null)
  const [adviceFor, setAdviceFor] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [exp, setExp] = useState<IbmExperiments | null>(null)

  useEffect(() => {
    api.ibmStatus(true).then((s) => { setStatus(s); setDevice((d) => d ?? s.devices[0]?.device ?? null) }).catch(() => setStatus(null))
    api.ibmExperiments().then(setExp).catch(() => setExp(null))
  }, [])
  useEffect(() => { if (device) api.ibmDevice(device).then(setSnap).catch(() => setSnap(null)) }, [device])

  const advise = async () => {
    if (!spec || spec.kind !== 'circuit') return
    setBusy(true)
    try { setAdvice((await api.ibmAdvise(spec)).advice); setAdviceFor(spec.metadata?.title ?? 'circuit') } finally { setBusy(false) }
  }
  const here = advice?.find((a) => a.device === device)
  const highlight = here?.best?.qubits ?? null
  const live = useMemo(() => new Map((status?.live?.devices ?? []).map((d) => [d.device, d])), [status])
  if (!status || !status.devices.length) return null
  const usage = status.live?.usage

  return (
    <div className="panel">
      <div className="panel-head"><h2>IBM Quantum</h2>
        <span className="sub">{status.devices.length} {status.devices[0].processor.family ?? ''} chips from their own calibration{usage ? ` · ${usage.left_s} s of QPU time left this month` : ''}</span></div>
      <p className="obs-head" style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
        Every qubit and coupler as the device reported it. Hover for values; the advisor places a circuit on the qubits most likely to run it without a fault.
        {status.can_run ? ' Run on IBM Quantum (under the editor) sends the circuit in the editor to the least busy chip, placed by the advisor.' : ` Runs from the app are off here (${status.reason}).`}</p>
      <table className="calls">
        <thead><tr><th>Device</th><th className="num">qubits</th><th className="num">2-qubit error</th><th className="num">1-qubit error</th><th className="num">readout</th>
          <th className="num">T1</th><th className="num">T2</th><th className="num">queue</th><th>calibrated</th></tr></thead>
        <tbody>{status.devices.map((d) => (
          <tr key={d.device} className={d.device === device ? 'sel' : ''} onClick={() => setDevice(d.device)} style={{ cursor: 'pointer' }}>
            <td><b>{d.device}</b> <span className="sub">{d.processor.family} r{d.processor.revision}</span></td><td className="num">{d.num_qubits}</td>
            <td className="num">{pct(d.two_qubit_error)}</td><td className="num">{pct(d.sx_error, 3)}</td><td className="num">{pct(d.readout_error)}</td>
            <td className="num">{d.t1_us.toFixed(0)} µs</td><td className="num">{d.t2_us.toFixed(0)} µs</td>
            <td className="num">{live.get(d.device)?.pending_jobs ?? d.pending_jobs}{live.size ? '' : '*'}</td><td className="sub">{(d.calibrated_utc ?? d.taken_utc).slice(0, 16).replace('T', ' ')}</td></tr>
        ))}</tbody>
      </table>
      <p className="sub" style={{ margin: '4px 0 10px' }}>Medians over each chip's working qubits and couplers. {live.size ? `Queues live at ${status.live?.checked_utc?.slice(11, 16)} UTC.` : '* queue at the time of the snapshot.'}</p>
      <div className="row wrap" style={{ gap: 6, marginBottom: 8 }}>
        {status.devices.map((d) => <button key={d.device} className={`chip-btn${d.device === device ? ' on' : ''}`} onClick={() => setDevice(d.device)}>{d.device}</button>)}
        <span className="spacer" />
        {METRICS.map((m) => <button key={m.id} className={`chip-btn${metric === m.id ? ' on' : ''}`} onClick={() => setMetric(m.id)}>{m.label}</button>)}
      </div>
      {snap && <ChipMap snap={snap} metric={metric} highlight={highlight} />}
      <p className="sub" style={{ margin: '4px 0 12px' }}>Grey is the best of this chip, orange the worst (5th to 95th percentile); a dashed red coupler is unusable. Snapshot {snap?.taken_utc.slice(0, 16).replace('T', ' ')} UTC.</p>

      <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
        <button className="btn" onClick={() => { void advise() }} disabled={busy || !spec || spec.kind !== 'circuit'}>
          {busy ? 'Placing…' : spec?.kind === 'circuit' ? `Where should "${spec.metadata?.title ?? 'this circuit'}" run?` : 'Open a circuit to place it'}</button>
        {here && <span className="sub">{here.note}</span>}
      </div>
      {advice && (
        <table className="calls" style={{ marginTop: 8 }}>
          <thead><tr><th>{adviceFor}</th><th>best qubits</th><th className="num">best</th><th className="num">median</th><th className="num">worst</th><th className="num">placements</th></tr></thead>
          <tbody>{advice.map((a) => (
            <tr key={a.device} className={a.device === device ? 'sel' : ''} onClick={() => setDevice(a.device)} style={{ cursor: 'pointer' }}>
              <td>{a.device}</td>
              {a.ok && a.best && a.median && a.worst ? <>
                <td className="mono">{a.best.qubits.join(', ')}</td><td className="num">{a.best.success.toFixed(3)}</td>
                <td className="num">{a.median.success.toFixed(3)}</td><td className="num">{a.worst.success.toFixed(3)}</td><td className="num">{a.candidates.toLocaleString()}</td>
              </> : <td colSpan={5} className="sub">{a.note}</td>}
            </tr>
          ))}</tbody>
        </table>
      )}
      {exp && <IbmExperimentsView exp={exp} />}
    </div>
  )
}

function IbmExperimentsView({ exp }: { exp: IbmExperiments }) {
  const ff = exp.teleport.feed_forward, nc = exp.teleport.no_corrections
  const [best, , worst] = exp.ghz.rows
  return (
    <div style={{ marginTop: 16 }}>
      <h3 style={{ margin: '0 0 4px' }}>Experiments on {exp.device}</h3>
      <p className="sub" style={{ margin: '0 0 8px', maxWidth: '90ch' }}>{exp.circuits} circuits, job {exp.job_id}, {exp.date_utc.slice(0, 10)}; raw counts, no readout correction.</p>
      <p style={{ margin: '0 0 6px', maxWidth: '90ch' }}><b>Placement matters.</b> The same GHZ-{exp.ghz.n} circuit on the advisor's best, median and worst qubits
        (of {exp.ghz.candidates.toLocaleString()} placements): GHZ fidelity {exp.ghz.rows.map((r) => `${r.fidelity.toFixed(3)} ± ${r.se.toFixed(3)}`).join(', ')}
        {best && worst ? `; best against worst, ${((best.fidelity - worst.fidelity) / Math.hypot(best.se, worst.se)).toFixed(0)} standard errors apart.` : '.'}</p>
      <table className="calls">
        <thead><tr><th>Placement</th><th>physical qubits</th><th className="num">advisor score</th><th className="num">GHZ fidelity on the chip</th><th className="num">digital twin</th></tr></thead>
        <tbody>{exp.ghz.rows.map((r) => (
          <tr key={r.placement}><td>{r.placement}</td><td className="mono">{r.qubits.join(', ')}</td><td className="num">{r.advisor_score.toFixed(3)}</td>
            <td className="num">{r.fidelity.toFixed(3)} ± {r.se.toFixed(3)}</td><td className="num">{r.twin_fidelity.toFixed(3)}</td></tr>
        ))}</tbody>
      </table>
      <p style={{ margin: '10px 0 6px', maxWidth: '90ch' }}><b>Teleportation with real feed-forward.</b> The Bell measurement happens mid-circuit and the chip decides in real time whether to apply X and Z
        (qubits {exp.teleport.qubits.join(', ')}). Averaged over the six axis states, which equals the average over all states: <b>{ff.average.toFixed(3)} ± {ff.se.toFixed(3)}</b> with
        feed-forward, {nc.average.toFixed(3)} ± {nc.se.toFixed(3)} without; no classical scheme beats {exp.teleport.classical_limit.toFixed(3)}.</p>
      <table className="calls">
        <thead><tr><th>State sent</th>{ff.rows.map((r) => <th key={r.state} className="num">{r.state}</th>)}<th className="num">average</th></tr></thead>
        <tbody>
          <tr><td>with feed-forward</td>{ff.rows.map((r) => <td key={r.state} className="num">{r.fidelity.toFixed(3)}</td>)}<td className="num"><b>{ff.average.toFixed(3)}</b></td></tr>
          <tr><td>without corrections</td>{nc.rows.map((r) => <td key={r.state} className="num">{r.fidelity.toFixed(3)}</td>)}<td className="num">{nc.average.toFixed(3)}</td></tr>
        </tbody>
      </table>
    </div>
  )
}

/** Run the circuit in the editor on a real IBM quantum computer, then compare what it measured. Local use only. */
export function IbmRunButton({ spec, valid }: { spec: CircuitSpec; valid: boolean }) {
  const [can, setCan] = useState(false)
  const [run, setRun] = useState<IbmRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.ibmStatus().then((s) => setCan(s.can_run)).catch(() => setCan(false)) }, [])
  useEffect(() => {
    if (!run || run.result) return
    const t = window.setTimeout(() => { api.ibmRunStatus(run.job_id).then(setRun).catch((e) => setError((e as Error).message)) }, 5000)
    return () => window.clearTimeout(t)
  }, [run])
  if (!can) return null
  const r = run?.result
  return (
    <>
      <button className="btn big" disabled={!valid || (!!run && !run.result)} title="Send this circuit to the least busy IBM quantum computer, on the qubits the advisor picks"
        onClick={() => { setError(null); api.ibmRun(spec, 2048).then(setRun).catch((e) => setError((e as Error).message)) }}>
        {run && !run.result ? `IBM: ${run.status.toLowerCase()}…` : 'Run on IBM Quantum'}</button>
      {(error || run) && (
        <div className="notice" style={{ flexBasis: '100%', marginTop: 8 }}>
          {error && <span className="badge fail">{error}</span>}
          {run && <span><b>{run.title}</b> on {run.device}, {run.shots} shots, job {run.job_id}: {run.how}; {run.two_qubit_gates} two-qubit gates on the chip.</span>}
          {r?.error && <span className="badge fail">{r.error}</span>}
          {r?.measured && (
            <span> Measured distance to the ideal odds <b>{r.tvd_ideal?.toFixed(3)}</b>
              {r.tvd_calibrated != null && <>, to Inkubit's calibrated preset <b>{r.tvd_calibrated.toFixed(3)}</b></>}; shot noise alone would leave about {r.shot_noise?.toFixed(3)}.
              Top outcomes: {Object.entries(r.measured).slice(0, 4).map(([k, v]) => `${k} ${(v * 100).toFixed(1)}%`).join(', ')}.</span>
          )}
        </div>
      )}
    </>
  )
}
