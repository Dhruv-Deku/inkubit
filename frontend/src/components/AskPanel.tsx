import { useState } from 'react'
import { api } from '../api'
import type { Explanation } from '../types'
import { CallBadge } from './CallBadge'

const CIRCUIT_QUESTIONS = ['Why did the first attempt fail?', 'Is it entangled?', 'Which noise costs the most?',
  'How good must the hardware be?', 'Can I trust the verification?']
const NETWORK_QUESTIONS = ['Where is the bottleneck?', 'What fixes did you try?', 'What key rate do we get?',
  'Can I trust these numbers?']

/** Questions about this run, answered only from its facts. */
export function AskPanel({ jobId, kind }: { jobId: string; kind: 'circuit' | 'network' }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [thread, setThread] = useState<{ q: string; a?: Explanation; error?: string }[]>([])
  const ask = async (question: string) => {
    if (!question.trim() || busy) return
    setBusy(true)
    setQ('')
    setThread((t) => [...t, { q: question }])
    try {
      const a = await api.ask(jobId, question)
      setThread((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a } : x)))
    } catch (e) {
      setThread((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: (e as Error).message } : x)))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="panel">
      <div className="panel-head"><h2>Ask about this result</h2><span className="sub">answered only from this run's numbers</span></div>
      {thread.length > 0 && (
        <div className="thread">
          {thread.map((x, i) => (
            <div key={i} className="qa">
              <div className="q">{x.q}</div>
              {x.a ? <div className="a"><p>{x.a.text}</p><CallBadge call={x.a.call} /></div>
                : x.error ? <div className="notice error">{x.error}</div>
                  : <div className="a sub"><span className="spin" style={{ width: 10, height: 10 }} /> thinking…</div>}
            </div>
          ))}
        </div>
      )}
      <form className="row" style={{ gap: 10 }} onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <input type="text" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }}
          placeholder="Ask anything about this run…" aria-label="Question about this result" spellCheck={false} />
        <button className="btn primary" type="submit" disabled={busy || !q.trim()}>Ask</button>
      </form>
      <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
        {(kind === 'circuit' ? CIRCUIT_QUESTIONS : NETWORK_QUESTIONS).map((t) => (
          <button key={t} className="chip-btn" disabled={busy} onClick={() => ask(t)}>{t}</button>
        ))}
      </div>
    </div>
  )
}
