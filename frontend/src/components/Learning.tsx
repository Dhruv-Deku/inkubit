import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { LineChart } from './Observatory'

interface LProposal { cnots: [number, number][]; why: string; count: number; verdict: string; infidelity: number | null; proof: number | null; note: string }
interface LRound { round: number; proposals: LProposal[]; best_so_far: number | null; seconds: number }
export interface LTarget {
  goal: { id: string; title: string; blurb: string; num_qubits: number }; lower_bound: number
  curves: Record<string, (number | null)[]>; reach_rate: Record<string, number>; first_proven: number | null; final_proven: number | null
  runs: Record<string, { condition: string; rounds: LRound[] }>
}
export interface LBench { model: string; rounds: number; targets: LTarget[] }

const COND: [string, string, string][] = [['feedback', 'With feedback', 'var(--primary)'], ['fresh', 'No feedback', 'var(--predicted)'], ['random', 'Random wiring', 'var(--text-2)']]
const pct = (v: number) => `${Math.round(v * 100)}%`
const last = (c: (number | null)[]) => c[c.length - 1]

function verdict(p: LProposal) {
  if (p.verdict === 'reached') return <span className="good">✓ proven</span>
  if (p.verdict === 'missed') return <span className="sub">✗ missed, infidelity {p.infidelity !== null ? p.infidelity.toExponential(1) : '?'}{p.note ? ` (${p.note})` : ''}</span>
  return <span className="warn-text">✗ {p.note}</span>
}

/** Muse Spark proposes circuit layouts in rounds and sees what exact physics said; does it get better? Three
 *  conditions with the same number of proposals: with that feedback, without it, and random wiring. */
export function LearningPanel({ live }: { live: boolean }) {
  const [bench, setBench] = useState<LBench | null>(null)
  const [gi, setGi] = useState(0)
  const [liveRun, setLiveRun] = useState<LTarget | null>(null)
  const [progress, setProgress] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const source = useRef<EventSource | null>(null)
  useEffect(() => { api.learningBenchmark().then(setBench).catch(() => setBench(null)); return () => source.current?.close() }, [])
  if (!bench) return null
  const recorded = bench.targets[gi]
  const t = liveRun && liveRun.goal.id === recorded.goal.id ? liveRun : recorded
  const fb = t.curves.feedback, fr = t.curves.fresh, rd = t.curves.random
  const firstRound = fb.findIndex((v) => v !== null) + 1
  const run = async () => {
    source.current?.close()
    setBusy(true); setError(null); setProgress([])
    try {
      const { learning_id } = await api.startLearning(recorded.goal.id)
      const es = new EventSource(`/api/learning/${learning_id}/events`)
      source.current = es
      es.addEventListener('learning', (ev) => {
        const d = JSON.parse((ev as MessageEvent).data) as { kind: string; condition?: string; round?: LRound; result?: LTarget }
        if (d.kind === 'round' && d.round) {
          const r = d.round
          setProgress((p) => [...p, `${COND.find((c) => c[0] === d.condition)?.[1]}, round ${r.round}: ${r.proposals.filter((x) => x.verdict === 'reached').length} of ${r.proposals.length} proven, best ${r.best_so_far ?? 'none yet'}`])
        } else if (d.kind === 'result' && d.result) setLiveRun(d.result)
      })
      es.addEventListener('end', (ev) => {
        const d = JSON.parse((ev as MessageEvent).data) as { error: string | null }
        if (d.error) setError(d.error)
        es.close(); setBusy(false)
      })
      es.onerror = () => { es.close(); setBusy(false) }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The run could not start.')
      setBusy(false)
    }
  }
  const lines = COND.map(([k, label, color]) => ({
    id: k, label, color, markers: true, dash: k === 'random' ? '6 4' : undefined,
    points: t.curves[k].map((v, i) => [i + 1, v] as [number, number | null]).filter((p) => p[1] !== null) as [number, number][],
  })).filter((l) => l.points.length)
  return (
    <div className="panel learning">
      <div className="panel-head">
        <h2>An AI scientist that learns</h2>
        <span className="sub">does feedback make it better?</span>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        {bench.targets.map((x, i) => <button key={x.goal.id} className={`chip-btn${gi === i ? ' on' : ''}`} onClick={() => setGi(i)} disabled={busy}>{x.goal.title}</button>)}
        <span className="spacer" />
        {live && <button className="btn small" onClick={() => { void run() }} disabled={busy}>{busy ? 'Running live…' : 'Run it live'}</button>}
      </div>
      <p className="obs-head" style={{ margin: '12px 0 6px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
        {t.first_proven !== null
          ? <>With feedback, Muse Spark's best proven layout went from <b>{t.first_proven} CNOTs</b> in round {firstRound} to <b>{t.final_proven} CNOTs</b> by round {fb.length}.
            Asked afresh each round, the same model ended at {last(fr) ?? 'no proven layout'}{last(fr) !== null ? ' CNOTs' : ''}; random wiring of the same lengths at {last(rd) ?? 'none'}{last(rd) !== null ? ' CNOTs' : ''}.
            {' '}{pct(t.reach_rate.feedback)} of its layouts with feedback reached the target, against {pct(t.reach_rate.fresh)} without and {pct(t.reach_rate.random)} at random.</>
          : <>No layout reached the target with feedback in {fb.length} rounds.</>}
        {' '}The structure of the state rules out fewer than {t.lower_bound} CNOTs.
      </p>
      <p className="sub" style={{ margin: '0 0 8px', maxWidth: '90ch' }}>{t.goal.blurb}</p>
      {error && <div className="notice error">{error}</div>}
      {progress.length > 0 && <div className="sub mono" style={{ margin: '0 0 8px' }}>{progress.slice(-3).map((p, i) => <div key={i}>{p}</div>)}</div>}
      <div className="dist-grid">
        <LineChart xLabel="round" yLabel="fewest proven CNOTs so far" fmtX={(v) => (Number.isInteger(v) ? `${v}` : '')}
          fmtY={(v) => (Math.abs(v - Math.round(v)) < 1e-6 ? `${Math.round(v)}` : '')} height={260}
          yDomain={[Math.min(...lines.flatMap((l) => l.points.map((p) => p[1]))) - 1, Math.max(...lines.flatMap((l) => l.points.map((p) => p[1]))) + 1]}
          xDomain={[1, fb.length]} aria="Fewest proven CNOTs after each round for the three conditions; lower is better" lines={lines} labels={false} />
        <div className="learn-rounds">
          <h3 style={{ margin: '0 0 6px' }}>What Muse Spark proposed, and what physics said (with feedback)</h3>
          {t.runs.feedback.rounds.map((r) => (
            <div key={r.round} className="learn-round">
              <div className="label">Round {r.round} · best so far {r.best_so_far ?? '–'}</div>
              {r.proposals.map((p, i) => (
                <div key={i} className="learn-prop">
                  <span className="mono">{p.count} CNOTs</span> {verdict(p)}
                  {p.why && <div className="sub">{p.why}</div>}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <p className="sub obs-method">Each round Muse Spark ({bench.model}) proposes up to four CNOT layouts. An exact optimiser fits the single-qubit rotations around every CNOT (L-BFGS on the overlap with the target);
        a layout counts only if it reaches the target to 10⁻⁹ and Qiskit's Statevector then confirms it to 10⁻⁸. With feedback, the next prompt lists every earlier layout with its verdict (proven, how close it came,
        or which pair is not wired) and the best proven count; without feedback, the same model is asked afresh; random wiring uses the feedback run's lengths with random allowed pairs. scripts/learning_bench.py rebuilds it.</p>
    </div>
  )
}
