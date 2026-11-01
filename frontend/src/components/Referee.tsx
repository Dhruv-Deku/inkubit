import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'

interface RClaim {
  question: string; claim_text: string; truth: string; claim_right: boolean; final: string; final_right: boolean
  challenge: { agree: boolean; reason: string; counter: string | null; right: boolean | null }
  reply: { stand: boolean; reason: string }
}
interface RDebate { title: string; qubits?: number; gates?: number; claims?: RClaim[]; spark_first?: number; final_right?: number; caught?: number; false_alarms?: number; talked_out?: number; error?: string; seconds?: number }
export interface RBench {
  spark: string; wonder: string; claims: number; debates: number; wrong_at_first: number
  summary: { spark_first: number; final_right: number; caught: number; false_alarms: number; talked_out: number }; rows: RDebate[]
}

const mark = (ok: boolean | null) => (ok === null ? '' : ok ? '✓' : '✗')

function DebateView({ d }: { d: RDebate }) {
  if (d.error || !d.claims) return <p className="sub">No debate on this circuit: {d.error}</p>
  return (
    <table className="calls disc-table ref-table">
      <thead><tr><th>Question</th><th>Muse Spark claims</th><th>Muse Wonder</th><th>Final answer</th><th>Exact truth</th></tr></thead>
      <tbody>
        {d.claims.map((c, i) => (
          <tr key={i}>
            <td>{c.question}</td>
            <td><span className={c.claim_right ? 'good' : 'bad'}>{mark(c.claim_right)}</span> {c.claim_text}</td>
            <td title={c.challenge.reason}>{c.challenge.agree ? <span className="sub">agrees</span>
              : <><span className={c.challenge.right ? 'good' : 'bad'}>{mark(c.challenge.right)}</span> disputes: {c.challenge.counter}</>}
              <div className="sub ref-reason">{c.challenge.reason}</div></td>
            <td title={c.reply.reason}><span className={c.final_right ? 'good' : 'bad'}>{mark(c.final_right)}</span> {c.final}
              {!c.challenge.agree && <div className="sub">{c.reply.stand ? 'Spark stood by it' : 'Spark conceded'}</div>}</td>
            <td className="mono">{c.truth}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Muse Spark answers three hard questions about a circuit, Muse Wonder challenges, exact simulation decides. */
export function RefereePanel({ live }: { live: boolean }) {
  const [bench, setBench] = useState<RBench | null>(null)
  const [di, setDi] = useState(0)
  const [liveDebate, setLiveDebate] = useState<RDebate | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)
  useEffect(() => { api.refereeBenchmark().then(setBench).catch(() => setBench(null)); return () => { if (timer.current) window.clearInterval(timer.current) } }, [])
  if (!bench) return null
  const s = bench.summary
  const shown = liveDebate ?? bench.rows[di]
  const start = async () => {
    setBusy(true); setError(null); setLiveDebate(null)
    try {
      const { referee_id } = await api.startReferee(di)
      timer.current = window.setInterval(async () => {
        try {
          const r = await api.referee(referee_id)
          if (r.status !== 'running') {
            if (timer.current) window.clearInterval(timer.current)
            setBusy(false)
            if (r.error) setError(r.error); else setLiveDebate(r.result as RDebate)
          }
        } catch { /* keep polling */ }
      }, 3000)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The debate could not start.')
      setBusy(false)
    }
  }
  return (
    <div className="panel referee">
      <div className="panel-head">
        <h2>The AI referee</h2>
        <span className="sub">Muse Spark answers, Muse Wonder challenges, exact simulation decides who was right</span>
      </div>
      <p className="obs-head" style={{ margin: '0 0 10px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
        On {bench.debates} circuits no textbook contains, Muse Spark answered {bench.claims} questions and was right on <b>{s.spark_first}</b> as first stated.
        Muse Wonder caught {s.caught} of its {bench.wrong_at_first} wrong answers, raised {s.false_alarms} false alarm{s.false_alarms === 1 ? '' : 's'}, and talked Spark out of {s.talked_out} right answer{s.talked_out === 1 ? '' : 's'};
        after the debate <b>{s.final_right}</b> of {bench.claims} were right. Two models arguing can catch mistakes, and make new ones; only the simulator knows which.
      </p>
      <div className="row wrap" style={{ gap: 6 }}>
        {bench.rows.map((r, i) => (
          <button key={i} className={`chip-btn${di === i && !liveDebate ? ' on' : ''}`} onClick={() => { setDi(i); setLiveDebate(null) }} disabled={busy}>
            {r.title}{r.final_right !== undefined ? ` · ${r.final_right}/3` : ''}
          </button>
        ))}
        <span className="spacer" />
        {live && <button className="btn small" onClick={() => { void start() }} disabled={busy}>{busy ? 'Debating live (about 2 min)…' : 'Debate this circuit live'}</button>}
      </div>
      {error && <div className="notice error" style={{ marginTop: 8 }}>{error}</div>}
      {shown && <div style={{ marginTop: 10 }}><DebateView d={shown} /></div>}
      <p className="sub obs-method">The referee asks the same three questions about every circuit: the most likely outcome, the probability of the second most likely outcome (picked from the exact odds so it is never trivial),
        and whether two given qubits are entangled before measurement (negativity of their reduced state). Muse Spark ({bench.spark}) answers; Muse Wonder ({bench.wonder}) agrees or disputes with its own value;
        Muse Spark stands by or concedes. Neither runs code. A probability counts as right within 0.02. scripts/referee_bench.py rebuilds it.</p>
    </div>
  )
}
