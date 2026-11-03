import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { ArenaBenchmark, ArenaResult, ArenaRow, ArenaSet, CircuitSpec, Health } from '../types'
import { CallBadge } from './CallBadge'
import { Histogram } from './Histogram'

const VERDICT: Record<string, { icon: string; cls: string; word: string }> = {
  wrong: { icon: '✗', cls: 'bad', word: 'wrong' },
  close: { icon: '≈', cls: 'warn', word: 'close' },
  matched: { icon: '✓', cls: 'good', word: 'right' },
}
const NOANSWER = { icon: '✗', cls: 'bad', word: 'no answer' }

let health: Promise<Health> | null = null
const live = () => (health ??= api.health()).then((h) => h.mode === 'meta').catch(() => false)

/** Start page: the recorded run of Muse Spark answering alone, on famous circuits and on new ones. */
export function ArenaPanel() {
  const [bench, setBench] = useState<ArenaBenchmark | null>(null)
  const [model, setModel] = useState('spark')
  const [open, setOpen] = useState<Record<string, boolean>>({ 'Bigger new circuits': true })
  useEffect(() => { api.arenaBenchmark(model).then(setBench).catch(() => setBench(null)) }, [model])
  if (!bench) return null
  const glimmer = model === 'glimmer'
  const t = bench.textbook, f = bench.new, b = bench.bigger
  const misses = (s: ArenaSet) => s.wrong + s.no_answer
  const fresh = misses(f) + misses(b)
  const miss = (s: ArenaSet) => `wrong on ${s.wrong}${s.no_answer ? `, no usable answer on ${s.no_answer}` : ''}${s.close ? ` · close on ${s.close}` : ''}`
  const groups: [string, string, ArenaRow[]][] = [
    ['Bigger new circuits', '6 to 8 qubits, 4 measured: up to 256 amplitudes to track', bench.rows.filter((r) => r.set === 'bigger')],
    ['New circuits', 'no textbook contains these, like your own sketch', bench.rows.filter((r) => r.set === 'new')],
    ['Textbook circuits', 'famous ones it has seen many times', bench.rows.filter((r) => r.set === 'textbook')],
  ]
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>AI alone vs Inkubit</h2>
        <span className="sub">why no answer here reaches you unchecked</span>
        <span className="spacer" />
        <span className="sub mono">{bench.model} · {bench.date}</span>
      </div>
      {(bench.available?.length ?? 0) > 1 && (
        <div className="seg" role="group" aria-label="Which model answers alone" style={{ marginBottom: 10 }}>
          <button className={model === 'spark' ? 'on' : ''} aria-pressed={model === 'spark'} onClick={() => setModel('spark')}>Muse Spark, hosted</button>
          <button className={glimmer ? 'on' : ''} aria-pressed={glimmer} onClick={() => setModel('glimmer')}>Muse Glimmer, open weights on a laptop</button>
        </div>
      )}
      <p className="lead">
        A chat model answers from patterns and has nothing to check itself against. We asked {glimmer
          ? 'Muse Glimmer, Meta\'s open-weight model, running on this laptop (30B, 4-bit, Ollama),'
          : 'the same model Inkubit uses'} to predict what circuits output on its own, like a chatbot with no simulator, and scored every answer against exact
        simulation: famous textbook circuits, new ones no textbook contains, and bigger new ones.
      </p>
      <div className="tiles" style={{ marginTop: 4 }}>
        <div className="tile"><div className="k">Textbook circuits</div><div className={`v ${t.matched === t.count ? 'good' : ''}`}>{t.matched} of {t.count} exact</div>
          <div className="s">{t.count - t.matched ? `wrong on ${t.wrong}${t.no_answer ? `, no answer on ${t.no_answer}` : ''}` : 'it has seen these many times'}</div></div>
        <div className="tile"><div className="k">New circuits, like yours</div><div className={`v ${misses(f) ? 'bad' : 'good'}`}>{f.matched} of {f.count} exact</div>
          <div className="s">{misses(f) || f.close ? miss(f) : 'all right this time'}</div></div>
        {b.count > 0 && <div className="tile"><div className="k">Bigger new circuits</div><div className={`v ${misses(b) ? 'bad' : 'good'}`}>{b.matched} of {b.count} exact</div>
          <div className="s">{misses(b) || b.close ? miss(b) : 'all right this time'}</div></div>}
        <div className="tile"><div className="k">In Inkubit</div><div className="v good">Checked</div>
          <div className="s">every run against exact simulation · 55 of 55 in the fault benchmark</div></div>
      </div>
      {groups.map(([label, sub, rows]) => rows.length > 0 && (
        <div key={label} className="arena-rows">
          <div className="arena-group"><span>{label}</span><span className="sub">{sub}</span><span className="spacer" />
            <span className="sub mono">{rows.filter((r) => r.verdict === 'matched').length} of {rows.length} exact</span>
            <button className="chip-btn" onClick={() => setOpen((o) => ({ ...o, [label]: !o[label] }))} aria-expanded={!!open[label]}>{open[label] ? 'hide' : 'show'}</button>
          </div>
          {open[label] && rows.map((r) => {
            const v = VERDICT[r.verdict] ?? NOANSWER
            return (
              <div key={r.id} className="arena-row" title={r.tvd === null ? 'the model gave no usable answer' : `${r.impossible} impossible outcomes given · ${r.missed} real outcomes missed`}>
                <span className="t">{r.title}</span>
                <span className="sub mono">{r.qubits}q · {r.gates} gates</span>
                <span className="track"><span className={v.cls} style={{ width: `${r.tvd === null ? 100 : Math.max(0.6, r.tvd * 100)}%`, opacity: r.tvd === null ? 0.35 : 1 }} /></span>
                <span className={`verdict ${v.cls}`}>{r.tvd === null ? '✗ no answer' : r.verdict === 'matched' ? '✓ exact' : `${v.icon} off by ${(r.tvd * 100).toFixed(0)}%`}</span>
              </div>
            )
          })}
        </div>
      ))}
      <p className="lead" style={{ margin: '12px 0 0' }}>
        {fresh
          ? 'On small circuits the model alone is excellent. As circuits grow, working them out by hand gets exponentially harder (each qubit doubles the amplitudes), and that is where an answer with nothing behind it fails. Exact simulation does not get tired: Inkubit computes every circuit up to 12 qubits exactly. '
          : 'It did well on every set. Inkubit still checks every answer, because you cannot tell in advance which one is wrong. '}
        In Inkubit the model does what it is good at (reading your drawing, writing the code), and nothing it says is shown
        until the code has run and matched an independent exact simulation; when it is wrong, the agent sees the exact
        difference and repairs it. Try any circuit with “Ask the AI alone” under the editor.
      </p>
    </div>
  )
}

/** Editor: ask Muse Spark alone what this circuit outputs and score it against the exact truth. */
export function AskAlone({ spec, valid }: { spec: CircuitSpec; valid: boolean }) {
  const [on, setOn] = useState<boolean | null>(null)
  const [res, setRes] = useState<{ key: string; r: ArenaResult } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { void live().then(setOn) }, [])
  const key = JSON.stringify(spec)
  const measured = spec.measurements.length > 0 || spec.operations.some((o) => o.gate === 'MEASURE')
  const ask = () => {
    setBusy(true); setError(null)
    api.arena(spec).then((r) => setRes({ key, r })).catch((e: Error) => setError(e instanceof ApiError ? e.message : 'The request failed.'))
      .finally(() => setBusy(false))
  }
  const r = res?.r
  const c = r?.comparison
  const v = c ? VERDICT[c.verdict] ?? VERDICT.wrong : null
  return (
    <div className="arena-ask">
      <div className="row wrap" style={{ gap: 10 }}>
        <button className="btn" onClick={ask} disabled={!on || busy || !valid || !measured}>{busy ? 'Asking…' : 'Ask the AI alone'}</button>
        <span className="sub">{on === false ? 'Live mode only: the start page shows the recorded results.' : !measured ? 'Add measurements first.'
          : 'What would a chatbot say this outputs? Muse Spark answers with no simulator; exact simulation scores it.'}</span>
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {r && c && v && (
        <div className={res!.key !== key ? 'stale' : ''} style={{ marginTop: 12 }}>
          {res!.key !== key && <div className="notice" style={{ marginBottom: 10 }}>The circuit changed since you asked. Ask again for the new one.</div>}
          <div className={`arena-verdict ${v.cls}`}>
            {c.verdict === 'matched' ? '✓ The AI alone got this one right.' : c.verdict === 'close' ? `≈ Close: ${(c.tvd * 100).toFixed(1)}% of the probability in the wrong place.`
              : `✗ The AI alone was wrong: ${(c.tvd * 100).toFixed(0)}% of the probability in the wrong place.`}
          </div>
          <div className="sub" style={{ margin: '4px 0 10px' }}>
            {[c.impossible.length ? `It gave ${c.impossible.length} outcome${c.impossible.length > 1 ? 's' : ''} that cannot happen (${c.impossible.slice(0, 4).join(', ')}).` : '',
              c.missed.length ? `It missed ${c.missed.length} that do (${c.missed.slice(0, 4).join(', ')}).` : '',
              Math.abs(c.guess_sum - 1) > 0.02 ? `Its odds added up to ${(c.guess_sum * 100).toFixed(0)}%, not 100%.` : ''].filter(Boolean).join(' ')
              || 'Same outcomes as the truth; compare the heights.'}
          </div>
          <Histogram predicted={c.truth} ideal={c.truth} measured={c.guess} shots={1}
            predictedLabel="Exact truth (what Inkubit checks against)" measuredLabel="What the AI alone said" idealMarks={false} />
          <div className="bug-muse-says">
            <CallBadge call={r.call} />
            <span>“{r.reasoning}”</span>
          </div>
        </div>
      )}
    </div>
  )
}
