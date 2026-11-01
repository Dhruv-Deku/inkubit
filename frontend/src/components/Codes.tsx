import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'

interface CVerdict { generators: string[]; valid: boolean; note: string; n: number; k: number; d: number | null; dx: number | null; dz: number | null; css: boolean; logical: string | null }
interface CRef extends CVerdict { name: string }
interface CCode extends CVerdict { why: string; verdict: string; score: number | null }
interface CTargetRun { target: { id: string; title: string; goal: string; objective: string; n: number; k: number }; rounds: { round: number; codes: CCode[]; best: CCode | null }[]; curve: (number | null)[]; best: CCode | null }
export interface CodesLab { references: CRef[]; benchmark: { model: string; rounds: number; targets: CTargetRun[] } | null }

const nkd = (v: { n: number; k: number; d: number | null }) => `[[${v.n},${v.k},${v.d ?? '?'}]]`

/** Muse Spark designs error-correcting codes in rounds; exact checks prove what each can correct. */
export function CodesPanel() {
  const [lab, setLab] = useState<CodesLab | null>(null)
  const [ti, setTi] = useState<number | null>(null)
  const [text, setText] = useState('XZZXI\nIXZZX\nXIXZZ\nZXIXZ')
  const [mine, setMine] = useState<CVerdict | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.codesLab().then(setLab).catch(() => setLab(null)) }, [])
  if (!lab) return null
  const runs = lab.benchmark?.targets ?? []
  const shownIndex = ti ?? Math.max(0, runs.findIndex((r) => r.target.objective === 'dz'))  // open on the tailored code
  const t = runs[shownIndex]
  const peer = t ? lab.references.filter((r) => r.n === t.target.n).sort((a, b) => (b.dz ?? 0) - (a.dz ?? 0))[0] : undefined
  const check = async () => {
    setBusy(true); setError(null)
    try { setMine(await api.analyseCode(text.split(/[\s,]+/).filter(Boolean))) } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not check it.') }
    setBusy(false)
  }
  return (
    <div className="panel codes">
      <div className="panel-head">
        <h2>Code lab</h2>
        <span className="sub">Muse Spark designs quantum error-correcting codes; an exact checker proves what each one can correct</span>
      </div>
      {t && (
        <>
          <div className="row wrap" style={{ gap: 6 }}>
            {runs.map((r, i) => <button key={r.target.id} className={`chip-btn${shownIndex === i ? ' on' : ''}`} onClick={() => setTi(i)}>{r.target.title}</button>)}
          </div>
          <p className="obs-head" style={{ margin: '10px 0 6px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
            Aim: {t.target.goal}. {t.best
              ? <>Best proven: <b>{nkd(t.best)}</b>, dX = {t.best.dx}, dZ = {t.best.dz}{t.best.css ? ', CSS' : ''}, first reached in round {t.rounds.findIndex((r) => r.best && r.best.generators.join() === t.best!.generators.join()) + 1} of {t.rounds.length}.
              {t.target.objective === 'dz' && peer && t.best.dz && peer.dz ? <> A logical error from Z noise alone now needs <b>{t.best.dz} errors</b>, {(t.best.dz / peer.dz).toFixed(0)}× the {peer.name.toLowerCase()}'s {peer.dz} (same checker, below), while any error on one qubit is still corrected.</> : null}
              {' '}<span className="sub">Idea: {t.best.why}</span></>
              : <>No proposal met the target in {t.rounds.length} rounds.</>}</p>
          <div className="codes-rounds">
            {t.rounds.map((r) => (
              <div key={r.round} className="learn-round">
                <div className="label">Round {r.round}</div>
                {r.codes.map((c, i) => (
                  <div key={i} className="learn-prop">
                    <span className={c.score !== null ? 'good' : c.valid ? 'sub' : 'warn-text'}>{c.score !== null ? '✓' : '✗'}</span> {c.verdict}
                    <div className="mono sub">{c.generators.join(' ')}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
      <h3 style={{ margin: '14px 0 4px' }}>Known codes, scored by the same checker</h3>
      <table className="calls disc-table">
        <thead><tr><th>Code</th><th>[[n,k,d]]</th><th className="num">dX</th><th className="num">dZ</th><th>CSS</th><th>A smallest logical error</th></tr></thead>
        <tbody>{lab.references.map((r) => (
          <tr key={r.name}><td>{r.name}</td><td className="mono">{nkd(r)}</td><td className="num">{r.dx}</td><td className="num">{r.dz}</td><td>{r.css ? 'yes' : 'no'}</td><td className="mono">{r.logical}</td></tr>
        ))}</tbody>
      </table>
      <h3 style={{ margin: '14px 0 4px' }}>Check your own code</h3>
      <div className="row wrap" style={{ gap: 10, alignItems: 'flex-start' }}>
        <textarea className="mono" rows={5} style={{ width: 240, maxWidth: '100%' }} value={text} onChange={(e) => setText(e.target.value)} aria-label="Stabilizer generators, one per line" />
        <div>
          <button className="btn small primary" onClick={() => { void check() }} disabled={busy}>{busy ? 'Checking…' : 'Check it exactly'}</button>
          {error && <div className="notice error" style={{ marginTop: 8 }}>{error}</div>}
          {mine && (mine.valid
            ? <p style={{ margin: '8px 0 0' }}><b>{nkd(mine)}</b> · dX = {mine.dx} · dZ = {mine.dz}{mine.css ? ' · CSS' : ''}<br /><span className="sub">a smallest undetectable error: <span className="mono">{mine.logical}</span></span></p>
            : <p className="warn-text" style={{ margin: '8px 0 0' }}>Not a valid code: {mine.note}</p>)}
        </div>
      </div>
      <p className="sub obs-method">One generator per line, I, X, Y, Z, qubit 0 leftmost, up to 11 qubits. The checker works in the binary symplectic picture: generators must commute and be independent over GF(2), k = n − rank;
        d is the smallest weight of a Pauli that commutes with every generator but is not in the stabilizer group, found by brute force from weight 1 up; dX and dZ allow only X or only Z errors.
        {lab.benchmark ? ` Muse Spark (${lab.benchmark.model}) saw every earlier verdict in the next round. scripts/codes_bench.py rebuilds it.` : ''}</p>
    </div>
  )
}
