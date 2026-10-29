import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ChallengeCheck, ChallengeInfo, CircuitSpec, Explanation } from '../types'
import { pct } from '../util'
import { BlochSphere } from './Bloch'
import { CallBadge } from './CallBadge'
import { AmplitudeTable } from './LiveState'

export type Progress = Record<string, number>

const KEY = 'qcanvas.challenges.v1'

export function loadProgress(): Progress {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Progress) : {}
  } catch {
    return {}
  }
}

export function saveProgress(p: Progress) {
  try { localStorage.setItem(KEY, JSON.stringify(p)) } catch { /* private window: progress lasts this visit only */ }
}

export function Stars({ n, of = 3, size = 15, pop = false }: { n: number; of?: number; size?: number; pop?: boolean }) {
  return (
    <span className="stars" role="img" aria-label={`${n} of ${of} stars`}>
      {Array.from({ length: of }, (_, k) => (
        <svg key={k} width={size} height={size} viewBox="0 0 24 24" className={k < n ? `star on ${pop ? 'pop' : ''}` : 'star'}
          style={pop ? { animationDelay: `${k * 140}ms` } : undefined} aria-hidden="true">
          <path d="M12 2.8l2.75 5.9 6.45.7-4.8 4.38 1.33 6.36L12 16.9l-5.73 3.24 1.33-6.36-4.8-4.38 6.45-.7z" />
        </svg>
      ))}
    </span>
  )
}

/** The puzzle board on the start page. */
export function ChallengeList({ list, progress, onStart }: {
  list: ChallengeInfo[]; progress: Progress; onStart: (c: ChallengeInfo) => void
}) {
  if (!list.length) return null
  const earned = list.reduce((t, c) => t + (progress[c.id] ?? 0), 0)
  const levels = [...new Set(list.map((c) => c.level))]
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Challenges</h2>
        <span className="sub">build the target state or gate; scored exactly, with par like golf</span>
        <span className="spacer" />
        <span className="sub mono">{earned} / {list.length * 3}</span><Stars n={1} of={1} />
      </div>
      <div className="challenge-levels">
        {levels.map((lv) => (
          <div key={lv}>
            <div className="label" style={{ marginBottom: 6 }}>{lv}. {list.find((c) => c.level === lv)?.level_name}</div>
            <div className="challenge-grid">
              {list.filter((c) => c.level === lv).map((c) => (
                <button key={c.id} className={`challenge-card ${progress[c.id] ? 'done' : ''}`} onClick={() => onStart(c)}>
                  <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                    <strong>{c.title}</strong><Stars n={progress[c.id] ?? 0} size={13} />
                  </div>
                  <span className="mono target-text">{c.target_text}</span>
                  <span className="sub">{c.num_qubits} qubit{c.num_qubits > 1 ? 's' : ''} · par {c.par}{c.allowed ? ` · only ${c.allowed.join(', ')}` : ''}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** The goal, the target, a live exact score of the circuit in the editor, and hints. */
export function ChallengePanel({ ch, spec, best, onScore, onNext, onExit, hasNext }: {
  ch: ChallengeInfo; spec: CircuitSpec | null; best: number; onScore: (stars: number) => void
  onNext: () => void; onExit: () => void; hasNext: boolean
}) {
  const [res, setRes] = useState<ChallengeCheck | null>(null)
  const [hints, setHints] = useState<Explanation[]>([])
  const [asking, setAsking] = useState(false)
  const [hintError, setHintError] = useState<string | null>(null)
  const [justSolved, setJustSolved] = useState(false)
  useEffect(() => { setHints([]); setRes(null); setJustSolved(false); setHintError(null) }, [ch.id])
  useEffect(() => {
    if (!spec) return
    const ctl = new AbortController()
    const t = setTimeout(() => {
      api.checkChallenge(ch.id, spec, ctl.signal).then((r) => {
        setRes((prev) => {
          if (r.solved && !prev?.solved) setJustSolved(true)
          if (!r.solved) setJustSolved(false)
          return r
        })
        if (r.stars > 0) onScore(r.stars)
      }).catch(() => { /* superseded */ })
    }, 120)
    return () => { clearTimeout(t); ctl.abort() }
  }, [spec, ch.id])
  const askHint = async () => {
    if (!spec) return
    setAsking(true)
    setHintError(null)
    try {
      const h = await api.hint(ch.id, spec, hints.length)
      setHints((hs) => [...hs, h])
    } catch (e) {
      setHintError((e as Error).message)
    } finally {
      setAsking(false)
    }
  }
  const solved = !!res?.solved
  return (
    <div className={`panel challenge ${solved ? 'solved' : ''}`}>
      <div className="panel-head">
        <span className="badge">Challenge · {ch.level_name}</span>
        <h2>{ch.title}</h2>
        <Stars n={best} />
        <span className="spacer" />
        <button className="btn small ghost" onClick={onExit}>All challenges</button>
      </div>
      <p className="lead" style={{ marginTop: 0 }}>{ch.goal}</p>
      <div className="challenge-cols">
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Target <span className="mono target-text">{ch.target_text}</span></div>
          {ch.target && <AmplitudeTable amps={ch.target} />}
          {ch.target_bloch && (
            <div className="spheres" style={{ marginTop: 8 }}>
              {ch.target_bloch.map((v, q) => (
                <BlochSphere key={q} vec={v} entangled={Math.hypot(...v) < 0.999} label={`q${q}`} size={84} />
              ))}
            </div>
          )}
          {ch.table && (
            <table className="data truth">
              <thead><tr><th>Input</th><th>Must become</th></tr></thead>
              <tbody>{ch.table.map((r) => <tr key={r.input}><td className="mono">{r.input}</td><td className="mono">{r.output}</td></tr>)}</tbody>
            </table>
          )}
          <div className="sub" style={{ marginTop: 8 }}>
            {ch.num_qubits} qubit{ch.num_qubits > 1 ? 's' : ''} · par {ch.par} gate{ch.par > 1 ? 's' : ''}
            {ch.allowed && <> · gates allowed: <span className="mono">{ch.allowed.join(', ')}</span></>}
            {ch.kind === 'state' ? ' · global phase does not count' : ' · checked on every input, up to a global phase'}
          </div>
        </div>
        <div>
          <div className="label" style={{ marginBottom: 6 }}>Your circuit</div>
          {!res ? <div className="sub">Scoring…</div> : (
            <>
              <div className="score-row">
                <div className="meter-track" style={{ flex: 1 }}>
                  <div className={`meter-bar ${solved ? 'good' : ''}`} style={{ width: `${Math.max(2, res.fidelity * 100)}%` }} />
                </div>
                <span className="mono">{pct(res.fidelity, 1)}</span>
              </div>
              <div className={`check-msg ${solved ? 'pass' : res.illegal.length ? 'fail' : ''}`}>{res.message}</div>
              {res.state && !solved && <AmplitudeTable amps={res.state} max={8} />}
              {res.rows_right !== null && !solved && (
                <div className="sub">{res.rows_right} of {2 ** ch.num_qubits} inputs right</div>
              )}
            </>
          )}
        </div>
      </div>
      {solved && res && (
        <div className={`solved-box ${justSolved ? 'fresh' : ''}`}>
          <div className="row wrap" style={{ gap: 12 }}>
            <Stars n={res.stars} size={26} pop={justSolved} />
            <strong>{res.stars === 3 ? 'Perfect.' : res.stars === 2 ? 'Solved, close to par.' : 'Solved.'}</strong>
            <span className="sub">{res.gates} gate{res.gates === 1 ? '' : 's'}, par {res.par}</span>
            <span className="spacer" />
            {hasNext && <button className="btn primary" onClick={onNext}>Next challenge</button>}
          </div>
          {res.lesson && <p className="lead" style={{ margin: '10px 0 0' }}>{res.lesson}</p>}
          {res.noisy_fidelity !== null && (
            <div className="sub" style={{ marginTop: 8 }}>
              On realistic superconducting hardware this circuit keeps {pct(res.noisy_fidelity, 1)} of the target state.
              Press Run below to see the agent verify it under that noise.
            </div>
          )}
        </div>
      )}
      <div className="hints">
        {hints.map((h, k) => (
          <div key={k} className="hint">
            <span className="label">Hint {k + 1}</span><span>{h.text}</span><CallBadge call={h.call} />
          </div>
        ))}
        {hintError && <div className="notice error">{hintError}</div>}
        {!solved && (
          <button className="btn small" onClick={askHint} disabled={asking || !spec}>
            {asking ? 'Thinking…' : hints.length ? 'Another hint' : 'Hint'}
          </button>
        )}
      </div>
    </div>
  )
}
