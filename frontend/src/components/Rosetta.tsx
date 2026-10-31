import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { CircuitSpec, ModelCall, RosettaEntry, RosettaResult } from '../types'
import { CallBadge } from './CallBadge'
import { CircuitPreview } from './CircuitPreview'
import { scrollToPanel } from './UseCases'
import { VoiceButton } from './VoiceButton'

const EXAMPLES: { label: string; text: string }[] = [
  { label: '(|01⟩ − |10⟩)/√2', text: '(|01⟩ − |10⟩)/√2' },
  { label: 'cos(π/8)|0⟩ + e^(iπ/4) sin(π/8)|1⟩', text: 'cos(π/8)|0⟩ + e^(iπ/4) sin(π/8)|1⟩' },
  { label: '(|001⟩ + |010⟩ + |100⟩)/√3', text: '(|001⟩ + |010⟩ + |100⟩)/√3' },
  { label: '|+⟩ ⊗ (|00⟩ + |11⟩)/√2', text: '|+⟩ ⊗ (|00⟩ + |11⟩)/√2' },
  { label: 'LaTeX from a paper', text: '\\frac{1}{\\sqrt{2}}\\left(|00\\rangle + i|11\\rangle\\right)' },
  { label: 'OpenQASM', text: 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[3];\nh q[0];\ncx q[0], q[1];\ncx q[1], q[2];' },
  { label: 'Quil', text: 'H 0\nCNOT 0 1\nRZ(pi/4) 1' },
  { label: 'Qiskit', text: 'qc = QuantumCircuit(2)\nqc.h(0)\nqc.h(1)\nqc.cz(0, 1)' },
  { label: 'words: GHZ on 4 qubits', text: 'a GHZ state on 4 qubits' },
]

function groupsText(groups: number[][]): string {
  return groups.map((g) => g.map((q) => `q${q}`).join('·')).join(', ')
}

function Dictionary({ onTry }: { onTry: (text: string) => void }) {
  const [open, setOpen] = useState(false)
  const [entries, setEntries] = useState<RosettaEntry[] | null>(null)
  const [q, setQ] = useState('')
  useEffect(() => {
    if (open && !entries) api.rosettaDictionary().then((r) => setEntries(r.entries)).catch(() => setEntries([]))
  }, [open, entries])
  const shown = (entries ?? []).filter((e) => `${e.term} ${e.plain}`.toLowerCase().includes(q.trim().toLowerCase()))
  return (
    <div className="ros-dict">
      <button className="btn" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? 'Hide the dictionary' : 'Quantum dictionary: the words of the field, each with a state computed exactly'}
      </button>
      {open && (
        <>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: entanglement, phase, ket, Shor…"
            aria-label="Search the quantum dictionary" style={{ marginTop: 10, maxWidth: 420, width: '100%' }} />
          {!entries && <div className="sub" style={{ marginTop: 10 }}>Computing every example…</div>}
          <div className="dict-grid">
            {shown.map((e) => (
              <div key={e.term} className="dict-card">
                <div className="dict-term">{e.term}</div>
                <p>{e.plain}</p>
                <div className="ket">{e.dirac}</div>
                <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                  <button className="chip-btn" onClick={() => onTry(e.example)}>Translate the example</button>
                  {e.see && <button className="chip-btn" onClick={() => scrollToPanel(e.see as string)}>See it: {e.see}</button>}
                </div>
              </div>
            ))}
          </div>
          {entries && !shown.length && <div className="sub" style={{ marginTop: 10 }}>No word matches “{q}”.</div>}
        </>
      )}
    </div>
  )
}

function RosettaView({ res, onOpen, photo }: { res: RosettaResult; onOpen?: (s: CircuitSpec) => void; photo: { notes: string; call: ModelCall } | null }) {
  const [lang, setLang] = useState('qiskit')
  const [copied, setCopied] = useState<string | null>(null)
  const spec = res.spec as CircuitSpec
  const cur = res.languages.find((l) => l.id === lang) ?? res.languages[0]
  const gates = spec.operations.filter((o) => o.gate !== 'MEASURE' && o.gate !== 'BARRIER')
  const copy = (s: string, what: string) => {
    navigator.clipboard?.writeText(s).then(() => { setCopied(what); setTimeout(() => setCopied(null), 1400) }).catch(() => {})
  }
  return (
    <div className="ros-result">
      <div className="row wrap" style={{ gap: 8, marginBottom: 12 }}>
        <span className={`badge ${res.source.exact ? 'pass' : 'meta'}`}>Read as {res.source.label}{res.source.exact ? ' · exact' : ''}</span>
        {photo && <CallBadge call={photo.call} />}
        {res.calls.map((c, i) => <CallBadge key={i} call={c} />)}
        {photo?.notes && <span className="sub">Photo: {photo.notes}</span>}
        {res.source.note && <span className="sub">{res.source.note}</span>}
      </div>
      <div className="ros-grid">
        <section className="ros-card">
          <div className="label">Math: the state, before measurement</div>
          <div className="ket big">{res.state.text}</div>
          {res.state.expanded && <div className="ket expanded">= {res.state.expanded}</div>}
          <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
            <span className={`trace-badge ${res.state.groups.length ? 'gold' : ''}`}>
              {res.state.groups.length ? `entangled: ${groupsText(res.state.groups)}` : res.state.product ? 'product state: every qubit on its own' : `${res.state.terms} terms`}
            </span>
            <button className="chip-btn" onClick={() => copy(res.state.latex, 'latex')}>{copied === 'latex' ? 'Copied' : 'Copy LaTeX'}</button>
          </div>
        </section>
        <section className="ros-card">
          <div className="label">Circuit</div>
          <CircuitPreview spec={spec} highlight={null} onPick={() => {}} />
          {res.preparation ? (
            <div className="sub" style={{ marginTop: 6 }}>
              <b className="good">✓ Prepares your state exactly</b> (fidelity {res.preparation.fidelity.toFixed(6)}, checked by exact simulation).
              {' '}{res.preparation.gates} gates, {res.preparation.two_qubit} two-qubit; found by {res.preparation.method}.
            </div>
          ) : <div className="sub" style={{ marginTop: 6 }}>{gates.length} gates on {spec.num_qubits} qubit{spec.num_qubits > 1 ? 's' : ''}.</div>}
          {onOpen && <button className="btn small" style={{ marginTop: 8 }} onClick={() => onOpen(spec)}>Open in the editor and run it</button>}
        </section>
        <section className="ros-card wide">
          <div className="label">In words, gate by gate</div>
          <ol className="ros-steps">
            {res.steps.map((s, i) => (
              <li key={i}>
                <div className="row wrap" style={{ gap: 8, alignItems: 'baseline' }}>
                  <span className="mono step-op">{s.label}</span><span className="sub">{s.meaning}</span>
                </div>
                {i > 0 && <div className="step-effect">{s.effect}</div>}
                <div className="ket">{s.dirac}</div>
              </li>
            ))}
          </ol>
        </section>
        <section className="ros-card wide">
          <div className="label">The same program in eight languages</div>
          <div className="seg wrap ros-tabs" role="tablist" aria-label="Programming language">
            {res.languages.map((l) => (
              <button key={l.id} role="tab" aria-selected={l.id === cur?.id} className={l.id === cur?.id ? 'on' : ''} onClick={() => setLang(l.id)}>
                {l.name}{l.checked ? ' ✓' : ''}
              </button>
            ))}
          </div>
          {cur && (
            <>
              <pre className="ros-code"><code>{cur.code}</code></pre>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className={`trace-badge ${cur.checked ? 'ok' : ''}`}>{cur.checked ? `✓ ${cur.note}` : cur.note}</span>
                <button className="chip-btn" onClick={() => copy(cur.code, 'code')}>{copied === 'code' ? 'Copied' : 'Copy code'}</button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

/** Quantum Rosetta: kets, OpenQASM, Quil, Qiskit, words, voice or a photo in; math, a proven circuit, words and eight languages out. */
export function RosettaPanel({ live, onOpen }: { live: boolean; onOpen?: (s: CircuitSpec) => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<RosettaResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [photo, setPhoto] = useState<{ notes: string; call: ModelCall } | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const topRef = useRef<HTMLDivElement | null>(null)

  const run = async (t: string, fromPhoto: { notes: string; call: ModelCall } | null = null) => {
    if (!t.trim() || busy) return
    setBusy(true)
    setError(null)
    setPhoto(fromPhoto)
    try {
      setRes(await api.rosetta(t))
    } catch (e) {
      setRes(null)
      setError(e instanceof ApiError ? e.message : 'The translation failed.')
    } finally {
      setBusy(false)
    }
  }
  const tryText = (t: string) => {
    setText(t)
    void run(t)
    topRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
  }
  const onPhoto = async (f: File) => {
    setBusy(true)
    setError(null)
    try {
      const read = await api.rosettaPhoto(f)
      setText(read.text)
      setBusy(false)
      await run(read.text, { notes: read.notes, call: read.call })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The photo could not be read.')
      setBusy(false)
    }
  }
  return (
    <div className="panel rosetta" ref={topRef}>
      <div className="panel-head">
        <h2>Quantum Rosetta</h2>
        <span className="sub">the language of quantum computing, translated both ways: math, circuits, plain words and eight programming languages, every translation checked by exact simulation</span>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); void run(text) }}>
        <textarea className="ros-input mono" rows={3} value={text} onChange={(e) => setText(e.target.value)} disabled={busy}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void run(text) } }}
          placeholder="Type, paste, say or photograph a state or a program: (|00⟩ + |11⟩)/√2 · OpenQASM · Quil · qc.h(0) · LaTeX · plain words"
          aria-label="Quantum notation to translate" />
        <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
          <button className="btn primary" type="submit" disabled={busy || !text.trim()}>{busy ? 'Translating…' : 'Translate'}</button>
          <VoiceButton onText={setText} onDone={(t) => { void run(t) }} disabled={busy} live={live} />
          {live && (
            <>
              <button type="button" className="btn" onClick={() => fileRef.current?.click()} disabled={busy}>Photo of an equation</button>
              <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void onPhoto(f) }} />
            </>
          )}
          <span className="sub">Ctrl+Enter translates</span>
        </div>
      </form>
      <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
        {EXAMPLES.map((x) => <button key={x.label} className="chip-btn" onClick={() => tryText(x.text)} disabled={busy}>{x.label}</button>)}
      </div>
      {error && <div className="notice error" style={{ marginTop: 12 }}>{error}</div>}
      {res && <RosettaView key={JSON.stringify(res.spec)} res={res} onOpen={onOpen} photo={photo} />}
      <Dictionary onTry={tryText} />
    </div>
  )
}
