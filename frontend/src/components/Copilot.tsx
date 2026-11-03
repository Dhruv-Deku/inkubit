import { useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { ChemLab, CircuitSpec, CopilotReply, CopilotTool, QaoaLab, QkdLab, RosettaResult, ShorLab } from '../types'
import { CallBadge } from './CallBadge'
import { CircuitPreview } from './CircuitPreview'
import { Histogram } from './Histogram'
import { EnergyChart, QberChart } from './Science'
import { VoiceButton } from './VoiceButton'

const IDEAS = [
  'What is the energy of H₂ at 1.5 Å, and can a noisy quantum computer get it right?',
  'Eve listens to 30% of the photons. Is she caught?',
  'Ana fights with Ben and Cai, Ben with Dev, Cai with Dev and Eli. Split them into two teams.',
  'Make a 4-qubit GHZ state. How well does it survive real hardware?',
  "Factor 15 with Shor's algorithm using a = 7.",
  'Plan a 600 km fiber link with 2 repeaters.',
  'When does error correction start to help?',
  'Compare H₂ at 0.74 Å and 2.5 Å.',
  'Plan a 1,200 km satellite key link, then check whether a spy on 20% of the photons would be caught.',
  'What circuit makes the state (|01⟩ − |10⟩)/√2, and is it entangled?',
]

const LABEL: Record<string, string> = {
  simulate_circuit: 'Circuit, simulated exactly', optimize_circuit: 'Shorter circuit, proven equal', molecule_h2: 'H₂ from first principles',
  quantum_key_distribution: 'BB84 key exchange', max_cut: 'QAOA split', factor_with_shor: "Shor's algorithm",
  plan_quantum_link: 'Quantum network link', error_correction: 'Error correction', translate_notation: 'Quantum Rosetta',
  run_algorithm: 'Algorithm library', ml_verify: 'ML verifier', analyze_network: 'Network from the photo',
}
const TEAM = ['#3987e5', '#d0702c']

interface Turn { q: string; deep?: boolean; reply?: CopilotReply; error?: string; seconds?: number }

export function TraceBadge({ trace: t }: { trace: CopilotReply['trace'] }) {
  if (!t.checked) return <span className="trace-badge muted">no numbers to trace</span>
  if (!t.untraced.length) {
    return <span className="trace-badge ok" title="Every number in the answer matches a tool result (or your question)">
      ✓ {t.traced + t.given} of {t.checked} numbers traced to exact tools{t.given ? ` (${t.given} from your question)` : ''}</span>
  }
  return <span className="trace-badge warn" title="These numbers are not in any tool result: treat them as the model's own">
    ⚠ {t.untraced.length} of {t.checked} not traced: {t.untraced.slice(0, 4).join(', ')}</span>
}

export function ToolCard({ run, first, onOpen }: { run: CopilotTool; first: boolean; onOpen?: (s: CircuitSpec) => void }) {
  const c = run.card as Record<string, unknown> | null
  const open = (s: unknown) => onOpen && s ? <button className="btn small" onClick={() => onOpen(s as CircuitSpec)}>Open in the editor</button> : null
  let body: React.ReactNode = null
  let action: React.ReactNode = null
  if (run.error || !c) {
    body = <div className="notice error">{run.error ?? 'No result.'}</div>
  } else if (c.type === 'chem') {
    const lab = c.lab as ChemLab
    action = open(lab.spec)
    body = (
      <>
        {first && <EnergyChart lab={lab} onPick={() => {}} />}
        <div className="mini-tiles">
          <span><b>{lab.r.toFixed(2)} Å</b> bond</span>
          <span><b>{lab.exact.toFixed(4)}</b> exact, Ha</span>
          <span><b>+{((lab.hf - lab.exact) * 1000).toFixed(1)}</b> mHa Hartree-Fock error</span>
          <span><b>{lab.mitigated.toFixed(4)}</b> VQE, noise undone</span>
        </div>
      </>
    )
  } else if (c.type === 'qkd') {
    const lab = c.lab as QkdLab
    action = open(lab.spec)
    body = (
      <div className="copilot-split">
        <QberChart lab={lab} />
        <div className="mini-tiles col">
          <span><b className={lab.caught ? 'bad' : 'good'}>{lab.caught ? 'Spy caught' : 'Key kept'}</b></span>
          <span><b>{(lab.qber * 100).toFixed(1)}%</b> error rate (abort above 11%)</span>
          <span><b>{lab.key_bits.toLocaleString()}</b> secret bits</span>
          <span><b>{lab.sifted.toLocaleString()}</b> of {lab.photons.toLocaleString()} photons kept</span>
        </div>
      </div>
    )
  } else if (c.type === 'maxcut') {
    const lab = c.lab as QaoaLab
    const names = c.names as string[]
    const d = lab.depths[lab.depths.length - 1]
    const best = d.top[0]
    action = open(d.spec)
    body = (
      <>
        <div className="teams">
          {[0, 1].map((t) => (
            <div key={t} className="team"><span className="sub">Team {t ? 'B' : 'A'}</span>
              <div>{names.filter((_, i) => best.teams[i] === t).map((n) => <span key={n} className="name-chip" style={{ borderColor: TEAM[t] }}>{n}</span>)}</div></div>
          ))}
        </div>
        <div className="mini-tiles">
          <span><b>{best.cut} / {lab.edges.length}</b> conflicts separated{best.optimal ? ' (best possible)' : ''}</span>
          <span><b>{(d.p_best * 100).toFixed(0)}%</b> chance QAOA reads a best split ({d.p} layers)</span>
          <span><b>{((d.p_best_noisy ?? 0) * 100).toFixed(0)}%</b> with realistic noise</span>
        </div>
      </>
    )
  } else if (c.type === 'rosetta') {
    const r = c.result as RosettaResult
    action = open(r.spec)
    body = (
      <>
        <div className="ket big">{r.state.text}</div>
        <CircuitPreview spec={r.spec as CircuitSpec} highlight={null} onPick={() => {}} />
        <div className="mini-tiles">
          <span><b>{r.state.groups.length ? 'Entangled' : 'Product state'}</b></span>
          {r.preparation && <span><b className="good">fidelity {r.preparation.fidelity.toFixed(6)}</b> circuit proven by exact simulation</span>}
          {r.preparation && <span><b>{r.preparation.gates}</b> gates, {r.preparation.two_qubit} two-qubit</span>}
          <span>read as {r.source.label}</span>
        </div>
      </>
    )
  } else if (c.type === 'circuit') {
    action = open(c.spec)
    body = (
      <>
        <CircuitPreview spec={c.spec as CircuitSpec} highlight={null} onPick={() => {}} />
        <Histogram predicted={(c.noisy ?? c.ideal) as Record<string, number>} ideal={c.ideal as Record<string, number>}
          predictedLabel={c.noisy ? 'Realistic hardware (exact, with noise)' : 'Perfect qubits'} />
      </>
    )
  } else if (c.type === 'optimize') {
    const best = c.best as { cost?: { gates: number; two_qubit: number; depth: number }; spec?: CircuitSpec; label: string } | null
    const orig = c.original as { gates: number; two_qubit: number; depth: number }
    action = best?.spec ? open(best.spec) : null
    body = (
      <div className="mini-tiles">
        <span><b>{orig.gates} → {best?.cost?.gates ?? orig.gates}</b> gates</span>
        <span><b>{orig.two_qubit} → {best?.cost?.two_qubit ?? orig.two_qubit}</b> CNOTs</span>
        <span><b>{best ? best.label : 'no shorter circuit'}</b>, proven by exact simulation</span>
      </div>
    )
  } else if (c.type === 'shor') {
    const lab = c.lab as ShorLab
    action = lab.spec ? open(lab.spec) : null
    const good = lab.outcomes.find((o) => o.ok)
    body = (
      <div className="mini-tiles">
        <span><b>{lab.coprime ? (good?.factors ? `15 = ${good.factors.join(' × ')}` : 'no factors') : `gcd = ${lab.shortcut}`}</b></span>
        {lab.coprime && <span><b>r = {lab.period}</b> period of {lab.a}ˣ mod 15</span>}
        {lab.coprime && <span><b>{(lab.success_ideal * 100).toFixed(0)}%</b> per run, perfect · <b>{(lab.success_noisy * 100).toFixed(0)}%</b> noisy</span>}
      </div>
    )
  } else if (c.type === 'network') {
    const r = c.result as { before: { end_to_end: Record<string, number> }; after: { end_to_end: Record<string, number> } | null; fix: { description: string } | null }
    const row = (label: string, k: string, f: (v: number) => string) => (
      <tr><td>{label}</td><td className="mono num">{f(r.before.end_to_end[k])}</td><td className="mono num">{r.after ? f(r.after.end_to_end[k]) : '–'}</td></tr>)
    body = (
      <>
        <div className="sub" style={{ marginTop: 4 }}>{String(c.title)}</div>
        <table className="calls net"><thead><tr><th>End to end</th><th className="num">Before</th><th className="num">After the fix</th></tr></thead>
          <tbody>
            {row('Entangled pairs per second', 'pair_rate_hz', (v) => v.toPrecision(3))}
            {row('Fidelity', 'fidelity', (v) => v.toFixed(3))}
            {row('Secret key, bits/s', 'key_rate_bps', (v) => v.toPrecision(3))}
          </tbody></table>
        {r.fix && <div className="sub" style={{ marginTop: 6 }}>Fix: {r.fix.description}</div>}
      </>
    )
  } else if (c.type === 'qec') {
    const lab = c.lab as { summary: string }
    body = <p className="sub" style={{ margin: 0 }}>{lab.summary}</p>
  } else if (c.type === 'mlverify') {
    const k = c.check as { prediction: { fidelity: number; low: number; high: number; baseline: number; microseconds: number }; exact: number | null; exact_ms: number | null; inside: boolean | null; verdict: string }
    action = open(c.spec)
    body = (
      <>
        <div className="mini-tiles">
          <span><b>{k.prediction.fidelity.toFixed(3)}</b> ML prediction, {k.prediction.microseconds.toFixed(0)} µs</span>
          <span><b>{k.prediction.low.toFixed(3)} to {k.prediction.high.toFixed(3)}</b> 90% interval</span>
          {k.exact !== null && <span><b>{k.exact.toFixed(3)}</b> exact, {k.exact_ms?.toFixed(0)} ms</span>}
          <span><b>{k.prediction.baseline.toFixed(3)}</b> rule of thumb</span>
        </div>
        <div className={`sub ${k.inside === false ? 'warn-text' : ''}`} style={{ marginTop: 6 }}>{k.inside === false ? '⚠ ' : k.inside ? '✓ ' : ''}{k.verdict}</div>
      </>
    )
  }
  return (
    <div className="copilot-card">
      <div className="row" style={{ gap: 8, marginBottom: 8 }}>
        <span className="tool-name">{LABEL[run.name] ?? run.name}</span>
        <span className="sub mono">{run.name}({Object.entries(run.args).filter(([k]) => k !== 'operations').map(([k, v]) => `${k}=${Array.isArray(v) ? `[${v.length}]` : String(v)}`).join(', ')}) · {run.seconds.toFixed(1)} s</span>
        <span className="spacer" />
        {action}
      </div>
      {body}
    </div>
  )
}

/** One assistant for the whole lab: Muse Spark (or Muse Wonder, deep mode) picks the exact tools, and every number it says is traced. */
export function CopilotPanel({ live, onOpen }: { live: boolean; onOpen?: (s: CircuitSpec) => void }) {
  const [text, setText] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [deep, setDeep] = useState(false)
  const endRef = useRef<HTMLDivElement | null>(null)
  const ask = async (q: string) => {
    const question = q.trim()
    if (!question || busy) return
    setText('')
    setBusy(true)
    const history = turns.flatMap((t) => (t.reply ? [{ role: 'user', content: t.q }, { role: 'assistant', content: t.reply.answer }] : []))
    const wonder = live && deep
    setTurns((ts) => [...ts, { q: question, deep: wonder }])
    const t0 = performance.now()
    try {
      const reply = await api.copilot(question, history, wonder)
      setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, reply, seconds: (performance.now() - t0) / 1000 } : t)))
    } catch (e) {
      setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, error: e instanceof ApiError ? e.message : 'The request failed.' } : t)))
    } finally {
      setBusy(false)
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50)
    }
  }
  return (
    <div className="panel copilot">
      <div className="panel-head">
        <h2>Ask Inkubit</h2>
        <span className="sub">{live ? 'one assistant for the whole lab: Muse Spark, or Muse Wonder for harder questions, calls exact tools, and every number it says is traced'
          : 'offline: a keyword router reaches the same exact tools; the live model answers anything'}</span>
      </div>
      <form className="row wrap" style={{ gap: 10, alignItems: 'stretch' }} onSubmit={(e) => { e.preventDefault(); void ask(text) }}>
        <input type="text" value={text} onChange={(e) => setText(e.target.value)} style={{ flex: '1 1 260px', minWidth: 0 }} className="copilot-input"
          placeholder="Ask about a molecule, a spy, a schedule, a circuit, a network…" aria-label="Ask Inkubit" disabled={busy} />
        <VoiceButton onText={setText} onDone={(t) => { void ask(t) }} disabled={busy} live={live} />
        {live && (
          <div className="seg" role="group" aria-label="Assistant model">
            <button type="button" className={deep ? '' : 'on'} aria-pressed={!deep} onClick={() => setDeep(false)} disabled={busy}
              title="Muse Spark 1.3: fast">Muse Spark</button>
            <button type="button" className={deep ? 'on' : ''} aria-pressed={deep} onClick={() => setDeep(true)} disabled={busy}
              title="Muse Wonder 1.0: Meta's most capable model, for questions that need several steps (slower)">Muse Wonder</button>
          </div>
        )}
        <button className="btn primary" type="submit" disabled={busy || !text.trim()}>{busy ? 'Working…' : 'Ask'}</button>
      </form>
      {!turns.length && (
        <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
          {IDEAS.map((t) => <button key={t} className="chip-btn" onClick={() => { void ask(t) }} disabled={busy}>{t}</button>)}
        </div>
      )}
      {turns.map((t, i) => {
        const chem = t.reply?.tools.findIndex((r) => r.name === 'molecule_h2') ?? -1
        return (
          <div key={i} className="copilot-turn">
            <div className="copilot-q">{t.q}</div>
            {!t.reply && !t.error && <div className="copilot-wait">{!live ? 'Routing to a tool…' : t.deep ? 'Muse Wonder is planning, calling tools and checking the results…' : 'Muse Spark is choosing tools and running them…'}</div>}
            {t.error && <div className="notice error">{t.error}</div>}
            {t.reply && (
              <>
                <p className="copilot-a">{t.reply.answer}</p>
                <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
                  <TraceBadge trace={t.reply.trace} />
                  {t.reply.calls[0] && <CallBadge call={t.reply.calls[0]} />}
                  <span className="sub">{t.reply.tools.length} tool call{t.reply.tools.length === 1 ? '' : 's'} · {t.reply.calls.length} model turn{t.reply.calls.length === 1 ? '' : 's'}{t.seconds ? ` · ${t.seconds.toFixed(1)} s` : ''}</span>
                </div>
                {t.reply.tools.map((r, k) => <ToolCard key={k} run={r} first={r.name !== 'molecule_h2' || k === chem} onOpen={onOpen} />)}
              </>
            )}
          </div>
        )
      })}
      {turns.length > 0 && !busy && (
        <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
          <span className="sub">Try:</span>
          {IDEAS.filter((x) => !turns.some((t) => t.q === x)).slice(0, 3).map((x) => <button key={x} className="chip-btn" onClick={() => { void ask(x) }}>{x}</button>)}
          <button className="chip-btn" onClick={() => setTurns([])}>Clear</button>
        </div>
      )}
      <div ref={endRef} />
    </div>
  )
}
