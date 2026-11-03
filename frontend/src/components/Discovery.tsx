import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { CircuitSpec, DiscoveryEntry, DiscoveryGoal, DiscoveryHardware, DiscoveryResult } from '../types'
import { CallBadge } from './CallBadge'
import { CircuitPreview } from './CircuitPreview'

const SOURCE: Record<string, string> = {
  textbook: 'textbook', compiler: 'Qiskit compiler', muse: 'Muse idea', tree: 'spanning tree', search: 'search',
}

function Bars({ entries }: { entries: DiscoveryEntry[] }) {
  const shown = [...entries.filter((e) => e.source === 'textbook' || e.source === 'compiler'), entries.find((e) => e.source !== 'textbook' && e.source !== 'compiler')]
    .filter((e): e is DiscoveryEntry => !!e)
  const lo = Math.max(0, Math.floor((Math.min(...shown.map((e) => e.noisy_fidelity)) - 0.08) * 10) / 10)
  return (
    <div className="disc-bars" role="img" aria-label={shown.map((e) => `${e.label}: ${e.cx} CNOTs, ${e.noisy_fidelity.toFixed(3)} of the state survives`).join('; ')}>
      {shown.map((e) => {
        const found = e.source !== 'textbook' && e.source !== 'compiler'
        return (
          <div key={e.label} className="disc-bar-row">
            <span className="disc-bar-label">{found ? 'Discovered' : e.source === 'textbook' ? 'Textbook' : 'Compiler'} · <b>{e.cx}</b> CNOTs</span>
            <span className="disc-bar-track">
              <span className={`disc-bar ${found ? 'found' : ''}`} style={{ width: `${((e.noisy_fidelity - lo) / (1 - lo)) * 100}%` }} />
            </span>
            <span className="mono disc-bar-val">{e.noisy_fidelity.toFixed(3)}</span>
          </div>
        )
      })}
      <div className="sub" style={{ marginTop: 2 }}>share of the state that survives realistic noise (exact density matrix; axis from {lo.toFixed(1)})</div>
    </div>
  )
}

/** Autonomous discovery: Muse Spark proposes CNOT layouts, an exact optimiser fits them, Qiskit proves them, the ML
 *  verifier screens and exact noisy simulation decides. */
export function DiscoveryPanel({ live, onOpen }: { live: boolean; onOpen?: (s: CircuitSpec) => void }) {
  const [goals, setGoals] = useState<DiscoveryGoal[]>([])
  const [goal, setGoal] = useState('w4')
  const [ket, setKet] = useState('')
  const [deep, setDeep] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [result, setResult] = useState<DiscoveryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [pick, setPick] = useState(0)
  const [hw, setHw] = useState<DiscoveryHardware | null>(null)
  useEffect(() => { api.discoveryHardware().then((d) => setHw(d.rehearsal ? null : d)).catch(() => setHw(null)) }, [])
  const es = useRef<EventSource | null>(null)
  useEffect(() => { api.discoveryGoals().then((r) => setGoals(r.goals)).catch(() => {}) }, [])
  useEffect(() => () => es.current?.close(), [])
  useEffect(() => {
    if (!busy) return
    const t0 = performance.now()
    const id = window.setInterval(() => setElapsed((performance.now() - t0) / 1000), 100)
    return () => window.clearInterval(id)
  }, [busy])
  const start = async (custom = false, goalId?: string) => {
    if (busy) return
    es.current?.close()
    setLog([]); setResult(null); setError(null); setBusy(true); setElapsed(0); setPick(0)
    try {
      const { discovery_id } = await api.startDiscovery(custom ? { ket } : { goal: goalId ?? goal }, live && deep)
      const src = new EventSource(`/api/discovery/${discovery_id}/events`)
      es.current = src
      src.addEventListener('discovery', (ev) => {
        const d = JSON.parse((ev as MessageEvent).data) as { kind: string; text?: string; result?: DiscoveryResult }
        if (d.kind === 'log' && d.text) setLog((l) => [...l, d.text!])
        if (d.kind === 'result' && d.result) setResult(d.result)
      })
      src.addEventListener('end', (ev) => {
        const d = JSON.parse((ev as MessageEvent).data) as { error: string | null }
        if (d.error) setError(d.error)
        src.close(); setBusy(false)
      })
      src.onerror = () => { src.close(); setBusy(false) }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The discovery run could not start.')
      setBusy(false)
    }
  }
  useEffect(() => {  // the guided tour starts a discovery run
    const onTour = (e: Event) => {
      const d = (e as CustomEvent<{ action: string; goal?: string }>).detail
      if (d.action !== 'discovery' || !d.goal) return
      setGoal(d.goal)
      void start(false, d.goal)
    }
    window.addEventListener('inkubit:tour', onTour)
    return () => window.removeEventListener('inkubit:tour', onTour)
  })
  const g = goals.find((x) => x.id === goal)
  const found = result?.entries.filter((e) => e.source !== 'textbook' && e.source !== 'compiler') ?? []
  const shown = result ? result.entries[Math.min(pick, result.entries.length - 1)] : null
  return (
    <div className="panel discovery">
      <div className="panel-head">
        <h2>Discovery lab</h2>
        <span className="sub">{live ? 'Muse Spark proposes circuits, physics proves them' : 'offline layouts, the same proofs'}</span>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        <span className="label">Goal</span>
        {goals.map((x) => (
          <button key={x.id} className={`chip-btn${goal === x.id ? ' on' : ''}`} aria-pressed={goal === x.id} onClick={() => setGoal(x.id)} disabled={busy}>{x.title}</button>
        ))}
      </div>
      {g && <p className="sub" style={{ margin: '8px 0 0', maxWidth: '86ch' }}>{g.blurb}</p>}
      <OnChip hw={hw} goal={goal} />
      <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
        <button className="btn primary" onClick={() => { void start(false) }} disabled={busy}>{busy ? `Discovering… ${elapsed.toFixed(0)} s` : 'Start discovery'}</button>
        {live && (
          <div className="seg" role="group" aria-label="Idea model">
            <button type="button" className={deep ? '' : 'on'} aria-pressed={!deep} onClick={() => setDeep(false)} disabled={busy}>Muse Spark</button>
            <button type="button" className={deep ? 'on' : ''} aria-pressed={deep} onClick={() => setDeep(true)} disabled={busy}>Muse Wonder</button>
          </div>
        )}
        <span className="sub">or your own state:</span>
        <input type="text" className="disc-ket mono" value={ket} onChange={(e) => setKet(e.target.value)} placeholder="(|001⟩ + |010⟩ − |100⟩)/√3" aria-label="Your own state" disabled={busy} />
        <button className="btn" onClick={() => { void start(true) }} disabled={busy || !ket.trim()}>Discover for it</button>
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {log.length > 0 && (
        <ol className="disc-log" aria-live="polite">
          {log.slice(-8).map((l, i) => <li key={log.length - 8 + i}>{l}</li>)}
        </ol>
      )}
      {result && (
        <div className="disc-result">
          <p className="mission-headline">{result.finding}</p>
          {found.length > 0 && <Bars entries={result.entries} />}
          <div className="mini-tiles">
            <span><b>{result.tried}</b> layouts tried</span>
            <span><b>{result.fewest_cnots ?? '–'}</b> fewest CNOTs found (baseline {result.baseline_cnots}, at least {result.lower_bound})</span>
            <span><b>{result.ml_milliseconds.toFixed(0)} ms</b> ML screening of {result.entries.length}{result.ml_agrees === null ? '' : result.ml_agrees ? ', same verdict as exact' : ', verdict differs from exact'}</span>
            <span><b>{result.seconds.toFixed(0)} s</b> total</span>
          </div>
          <table className="calls disc-table">
            <thead><tr><th>Circuit</th><th>From</th><th className="num">CNOTs</th><th className="num">1-qubit</th><th className="num">Proof</th><th className="num">Survives noise</th><th className="num">ML says</th></tr></thead>
            <tbody>
              {result.entries.map((e, i) => (
                <tr key={e.label} className={i === pick ? 'sel' : ''} onClick={() => setPick(i)} style={{ cursor: 'pointer' }} title={e.why || e.label}>
                  <td>{e.label}</td><td>{SOURCE[e.source] ?? e.source}</td><td className="num">{e.cx}</td><td className="num">{e.one_qubit}</td>
                  <td className="num">{e.source === 'textbook' || e.source === 'compiler' ? 'Qiskit' : e.proof.toFixed(9)}</td>
                  <td className="num">{e.noisy_fidelity.toFixed(3)}</td><td className="num">{e.ml_fidelity?.toFixed(3) ?? '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown && (
            <div className="disc-circuit">
              <div className="row wrap" style={{ gap: 8, marginBottom: 6 }}>
                <b>{shown.label}</b>{shown.why && <span className="sub">{shown.why}</span>}<span className="spacer" />
                {onOpen && <button className="btn small" onClick={() => onOpen(shown.spec as unknown as CircuitSpec)}>Open in the editor</button>}
              </div>
              <CircuitPreview spec={shown.spec as unknown as CircuitSpec} highlight={null} onPick={() => {}} />
            </div>
          )}
          <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
            {result.calls.map((c, i) => <CallBadge key={i} call={c} />)}
            <span className="sub">"Fewest found" is the best within the search budget, not a proof that nothing shorter exists.</span>
          </div>
        </div>
      )}
    </div>
  )
}

/** One line: how this goal's discovered circuit did on a real IBM chip against the baselines, when that run exists. */
function OnChip({ hw, goal }: { hw: DiscoveryHardware | null; goal: string }) {
  const g = hw?.goals.find((x) => x.id === goal)
  if (!hw || !g) return null
  const base = (s: string) => s === 'textbook' || s === 'compiler'
  const found = g.variants.find((v) => !base(v.source))
  const rivals = g.variants.filter((v) => base(v.source))
  if (!found || !rivals.length) return null
  const metric = found.ghz ? 'GHZ fidelity' : 'outcome fidelity'
  const val = (v: typeof found) => v.ghz?.fidelity ?? v.outcome_fidelity
  const best = rivals.reduce((a, b) => (val(b) > val(a) ? b : a))
  const z = g.comparison?.z
  const said = z === undefined ? '' : z > 2 ? `: a win by ${z.toFixed(1)} standard errors` : z < -2 ? `: a loss by ${(-z).toFixed(1)} standard errors` : ': a tie within shot noise'
  return (
    <p className="sub" style={{ margin: '6px 0 0', maxWidth: '86ch' }}>
      <b>On a real IBM quantum computer</b> ({hw.device}, {hw.date_utc.slice(0, 10)}): the discovered circuit ({found.two_qubit_gates} two-qubit gates on the chip) reached a {metric} of <b>{val(found).toFixed(3)}</b>,
      {' '}against {val(best).toFixed(3)} for {best.label.toLowerCase().startsWith('textbook') ? 'the textbook circuit' : "Qiskit's state preparation"} ({best.two_qubit_gates}){said}. Details under Evidence.
    </p>
  )
}
