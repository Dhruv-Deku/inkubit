import { useEffect, useRef, useState } from 'react'
import type { CircuitSpec, Gate, NetLink, NetNode, NetworkSpec, Operation, Spec, SpecIssue } from '../types'
import { GATE_LABEL, GATES } from '../types'
import { angleText, clone, condFrom, condPairs, parseAngle, parseIntList, resizeCircuit } from '../util'
import { CircuitPreview, SHORT, wiresFor, type Compose } from './CircuitPreview'
import { Down, Trash, Up } from './Icons'
import { LiveStrip } from './LiveState'
import { Optimizer } from './Optimizer'
import { AskAlone } from './Arena'

interface Props {
  spec: Spec
  issues: SpecIssue[]
  highlight: string | null
  onPick: (key: string | null) => void
  onChange: (spec: Spec) => void
  allowed?: Gate[] | null  // a challenge may restrict the palette
  valid?: boolean
  optimizer?: boolean  // off in challenges, where it would give the answer away
}

export function SpecEditor({ spec, issues, highlight, onPick, onChange, allowed, valid = true, optimizer = true }: Props) {
  const [mode, setMode] = useState<'form' | 'json'>('form')
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Spec</h2>
        <span className="badge">{spec.kind}</span>
        <span className="spacer" />
        <div className="seg">
          <button className={mode === 'form' ? 'on' : ''} onClick={() => setMode('form')}>Form</button>
          <button className={mode === 'json' ? 'on' : ''} onClick={() => setMode('json')}>JSON</button>
        </div>
      </div>
      {mode === 'json' ? <JsonEditor spec={spec} onChange={onChange} />
        : spec.kind === 'circuit'
          ? <CircuitForm spec={spec} highlight={highlight} onPick={onPick} onChange={onChange} allowed={allowed} valid={valid} optimizer={optimizer} />
          : <NetworkForm spec={spec} highlight={highlight} onPick={onPick} onChange={onChange} />}
      {issues.length > 0 && (
        <div className="notice error" style={{ marginTop: 14 }}>
          <strong>Fix {issues.length === 1 ? 'this' : `these ${issues.length}`} before running:</strong>
          <ul className="issues">
            {issues.map((i, k) => (
              <li key={k}>{i.path && <code>{i.path}</code>} {i.message}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function JsonEditor({ spec, onChange }: { spec: Spec; onChange: (s: Spec) => void }) {
  const [text, setText] = useState(() => JSON.stringify(spec, null, 2))
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    try {
      if (JSON.stringify(JSON.parse(text)) === JSON.stringify(spec)) return
    } catch { /* user is mid-edit */ return }
    setText(JSON.stringify(spec, null, 2))
  }, [spec])
  return (
    <div>
      <textarea rows={22} value={text} spellCheck={false} onChange={(e) => {
        setText(e.target.value)
        try {
          const parsed = JSON.parse(e.target.value)
          setErr(null)
          onChange(parsed)
        } catch (x) {
          setErr((x as Error).message)
        }
      }} />
      {err && <div className="notice warn" style={{ marginTop: 8 }}>JSON syntax: {err}</div>}
    </div>
  )
}

const needsControl = (g: Gate) => g === 'CX' || g === 'CZ' || g === 'CP' || g === 'CCX'
const needsAngle = (g: Gate) => g === 'RX' || g === 'RY' || g === 'RZ' || g === 'CP'

const PALETTE: Gate[] = ['H', 'X', 'Y', 'Z', 'S', 'T', 'SDG', 'TDG', 'SX', 'RX', 'RY', 'RZ', 'CX', 'CZ', 'CP', 'SWAP', 'CCX']
const PALETTE_TIP: Partial<Record<Gate, string>> = {
  H: 'Hadamard: |0⟩ → equal superposition', X: 'NOT: swaps |0⟩ and |1⟩', Y: 'Y: bit and phase flip', Z: 'Z: minus sign on |1⟩',
  S: 'S: phase i on |1⟩ (quarter turn)', T: 'T: phase e^(iπ/4) on |1⟩', SDG: 'S†: undoes S', TDG: 'T†: undoes T', SX: '√X: half a NOT',
  RX: 'Rotate about x (π/2; edit the angle below)', RY: 'Rotate about y (π/2; edit the angle below)', RZ: 'Rotate about z (π/2; edit the angle below)',
  CX: 'CNOT: click the control, then the target', CZ: 'CZ: click two qubits', CP: 'Controlled phase: control, then target',
  SWAP: 'SWAP: click two qubits', CCX: 'Toffoli: two controls, then the target',
}

/** What the next click does, in words. */
function composeHint(tool: Gate | 'ERASE' | null, picked: number): string {
  if (!tool) return 'Pick a gate, then click a wire to add it. Or edit the table below.'
  if (tool === 'ERASE') return 'Click a gate in the drawing to remove it.'
  const need = wiresFor(tool)
  const name = SHORT[tool] ?? tool
  if (need === 1) return `Click a wire to add ${name}.`
  if (tool === 'SWAP') return picked ? 'Now click the second qubit.' : 'Click the first qubit to swap.'
  if (picked === need - 1) return `Now click the target of the ${name}.`
  return tool === 'CCX' && picked === 1 ? 'Click the second control.' : 'Click the control qubit.'
}

function CircuitForm({ spec, highlight, onPick, onChange, allowed, valid, optimizer }: {
  spec: CircuitSpec; highlight: string | null; onPick: (k: string | null) => void; onChange: (s: Spec) => void
  allowed?: Gate[] | null; valid: boolean; optimizer: boolean
}) {
  const [tool, setTool] = useState<Gate | 'ERASE' | null>(null)
  const [pending, setPending] = useState<number[]>([])
  const undo = useRef<CircuitSpec[]>([])
  const [, bump] = useState(0)
  const palette = allowed?.length ? PALETTE.filter((g) => allowed.includes(g)) : PALETTE
  useEffect(() => { setPending([]) }, [tool, spec.num_qubits])
  useEffect(() => {
    if (!tool) return
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { setTool(null); setPending([]) } }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [tool])
  const commit = (next: CircuitSpec) => {
    undo.current = [...undo.current.slice(-49), spec]
    bump((k) => k + 1)
    onChange(next)
  }
  const compose: Compose = {
    tool, pending,
    onWire: (q) => {
      if (!tool || tool === 'ERASE') return
      if (pending.includes(q)) { setPending(pending.filter((p) => p !== q)); return }
      const picked = [...pending, q]
      const need = wiresFor(tool)
      if (picked.length < need) { setPending(picked); return }
      const params = needsAngle(tool) ? [Math.PI / 2] : []
      const op: Operation = tool === 'SWAP' ? { gate: 'SWAP', targets: picked, controls: [], params }
        : need > 1 ? { gate: tool, controls: picked.slice(0, -1), targets: [picked[picked.length - 1]], params }
          : { gate: tool, targets: [q], controls: [], params }
      const next = clone(spec)
      next.operations.push(op)
      setPending([])
      commit(next)
    },
    onGate: (i) => {
      if (tool !== 'ERASE') return
      const next = clone(spec)
      next.operations.splice(i, 1)
      commit(next)
    },
  }
  const update = (fn: (s: CircuitSpec) => void) => { const s = clone(spec); fn(s); onChange(s) }
  const setOp = (i: number, patch: Partial<Operation>) => update((s) => { s.operations[i] = { ...s.operations[i], ...patch } })
  const move = (i: number, d: number) => update((s) => {
    const j = i + d
    if (j < 0 || j >= s.operations.length) return
    ;[s.operations[i], s.operations[j]] = [s.operations[j], s.operations[i]]
  })
  const changeGate = (i: number, g: Gate) => {
    const op = spec.operations[i]
    const next: Operation = { ...op, gate: g }
    if (g === 'MEASURE' || g === 'BARRIER' || g === 'RESET') next.conditional = null
    if (g === 'RESET') {
      setOp(i, { ...next, targets: op.targets.length ? op.targets : [0], controls: [], params: [], clbits: [] })
      return
    }
    if (g === 'MEASURE') {
      const c = freeClbit(spec)
      update((s) => {
        s.operations[i] = { ...next, targets: [op.targets[0] ?? 0], controls: [], params: [], clbits: [c] }
        s.num_clbits = Math.max(s.num_clbits, c + 1)
      })
      return
    }
    next.clbits = []
    if (g === 'CCX') {
      const t = op.targets[0] ?? Math.min(2, spec.num_qubits - 1)
      const pool = [...(op.controls ?? []), ...Array.from({ length: spec.num_qubits }, (_, q) => q)]
      next.controls = pool.filter((q, k) => q !== t && pool.indexOf(q) === k).slice(0, 2)
      next.targets = [t]
    } else if (needsControl(g)) {
      next.controls = op.controls?.length ? [op.controls[0]] : [op.targets[0] === 0 ? 1 : 0]
      next.targets = [op.targets[0] ?? 1]
    } else next.controls = []
    if (g === 'SWAP') next.targets = [op.targets[0] ?? 0, (op.targets[0] ?? 0) === 0 ? 1 : 0]
    next.params = needsAngle(g) ? (op.params?.length ? op.params : [Math.PI / 2]) : []
    setOp(i, next)
  }
  const measuredQ = new Set(spec.measurements.map((m) => m.qubit))

  return (
    <div>
      <div className="fieldline">
        <label>Title</label>
        <input type="text" style={{ flex: 1, minWidth: 160 }} value={spec.metadata?.title ?? ''}
          onChange={(e) => update((s) => { s.metadata = { ...s.metadata, title: e.target.value } })} />
        <label>Qubits</label>
        <input type="number" min={1} max={12} style={{ width: 64 }} value={spec.num_qubits}
          onChange={(e) => onChange(resizeCircuit(spec, Math.max(1, Math.min(12, Number(e.target.value) || 1))))} />
      </div>
      <div className="palette" role="toolbar" aria-label="Gate palette">
        {palette.map((g) => (
          <button key={g} className={`gate-btn ${tool === g ? 'on' : ''} ${wiresFor(g) > 1 ? 'multi' : ''}`} title={PALETTE_TIP[g]}
            onClick={() => setTool(tool === g ? null : g)} disabled={wiresFor(g) > spec.num_qubits}>{SHORT[g] ?? g}</button>
        ))}
        <span className="palette-sep" />
        <button className={`gate-btn ${tool === 'ERASE' ? 'on erase' : ''}`} title="Remove gates by clicking them"
          onClick={() => setTool(tool === 'ERASE' ? null : 'ERASE')} disabled={!spec.operations.length}>Erase</button>
        <button className="gate-btn" title="Undo the last palette change" disabled={!undo.current.length}
          onClick={() => { const prev = undo.current.pop(); bump((k) => k + 1); if (prev) onChange(prev) }}>Undo</button>
        <button className="gate-btn" title="Remove every gate" disabled={!spec.operations.length}
          onClick={() => { const next = clone(spec); next.operations = []; commit(next) }}>Clear</button>
      </div>
      <div className="compose-hint sub">{composeHint(tool, pending.length)}{tool && <span className="muted"> · Esc to stop</span>}</div>
      <CircuitPreview spec={spec} highlight={highlight} onPick={onPick} compose={compose} />
      <LiveStrip spec={spec} valid={valid} />
      {optimizer && <Optimizer spec={spec} valid={valid} onUse={(s) => commit(s)} />}
      {optimizer && <AskAlone spec={spec} valid={valid} />}
      <table className="ops" style={{ marginTop: 12 }} onMouseLeave={() => onPick(null)}>
        <thead>
          <tr><th>#</th><th>Gate</th><th>Target</th><th>Control</th><th>Angle</th>
            <th title="Mid-circuit measurements write a classical bit; a gate can run only when an earlier bit reads 0 or 1">Feed-forward</th>
            <th>From sketch</th><th /></tr>
        </thead>
        <tbody>
          {spec.operations.map((op, i) => {
            const key = `operations[${i}]`
            return (
              <tr key={i} className={highlight === key ? 'hl' : ''} onMouseEnter={() => onPick(key)}>
                <td className="muted">{i}</td>
                <td>
                  <select value={op.gate} onChange={(e) => changeGate(i, e.target.value as Gate)}>
                    {GATES.map((g) => <option key={g} value={g}>{GATE_LABEL[g] ?? g}</option>)}
                  </select>
                </td>
                <td><IntList value={op.targets} onChange={(v) => setOp(i, { targets: v })} /></td>
                <td>{needsControl(op.gate) ? <IntList value={op.controls ?? []} onChange={(v) => setOp(i, { controls: v })} /> : <span className="muted">—</span>}</td>
                <td>{needsAngle(op.gate) ? <AngleInput value={op.params?.[0] ?? 0} onChange={(v) => setOp(i, { params: [v] })} /> : <span className="muted">—</span>}</td>
                <td>{op.gate === 'MEASURE' ? (
                  <span className="ff">into c <IntList value={op.clbits ?? []} onChange={(v) => update((s) => {
                    s.operations[i] = { ...s.operations[i], clbits: v }
                    s.num_clbits = Math.max(s.num_clbits, ...v.map((c) => c + 1))
                  })} /></span>
                ) : op.gate === 'BARRIER' || op.gate === 'RESET' ? <span className="muted">—</span> : (
                  <Condition op={op} bits={bitsBefore(spec, i)} onChange={(c) => setOp(i, { conditional: c })} />
                )}</td>
                <td>{op.source ? <span className="chip-src">{Math.round(op.source.confidence * 100)}% sure</span> : <span className="muted">added</span>}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="icon-btn" title="Move up" disabled={i === 0} onClick={() => move(i, -1)}><Up /></button>
                  <button className="icon-btn" title="Move down" disabled={i === spec.operations.length - 1} onClick={() => move(i, 1)}><Down /></button>
                  <button className="icon-btn" title="Delete" onClick={() => update((s) => { s.operations.splice(i, 1) })}><Trash /></button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="row wrap" style={{ marginTop: 10 }}>
        <button className="btn small" onClick={() => update((s) => { s.operations.push({ gate: 'H', targets: [0], controls: [], params: [] }) })}>+ Gate</button>
        <button className="btn small" disabled={spec.num_qubits < 2} onClick={() => update((s) => { s.operations.push({ gate: 'CX', controls: [0], targets: [1], params: [] }) })}>+ CNOT</button>
        <button className="btn small" title="Measure a qubit halfway through; later gates can depend on the result (feed-forward)"
          onClick={() => update((s) => {
            const c = freeClbit(s)
            s.operations.push({ gate: 'MEASURE', targets: [freeQubit(s)], clbits: [c], controls: [], params: [] })
            s.num_clbits = Math.max(s.num_clbits, c + 1)
          })}>+ Mid-circuit measure</button>
        <span className="spacer grow" />
        <span className="sub">Measure at the end:</span>
        <div className="meas">
          {Array.from({ length: spec.num_qubits }, (_, q) => (
            <label key={q}>
              <input type="checkbox" checked={measuredQ.has(q)} onChange={(e) => update((s) => {
                s.measurements = e.target.checked
                  ? [...s.measurements, { qubit: q, clbit: q }].sort((a, b) => a.qubit - b.qubit)
                  : s.measurements.filter((m) => m.qubit !== q)
                s.num_clbits = Math.max(s.num_clbits, q + 1)
              })} />q{q}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}

/** The smallest classical bit nothing writes yet. */
function freeClbit(s: CircuitSpec): number {
  const used = new Set([...s.measurements.map((m) => m.clbit), ...s.operations.flatMap((o) => (o.gate === 'MEASURE' ? o.clbits ?? [] : []))])
  let c = 0
  while (used.has(c)) c++
  return c
}

/** A qubit nothing measures yet (else q0), for a new mid-circuit measurement. */
function freeQubit(s: CircuitSpec): number {
  const used = new Set([...s.measurements.map((m) => m.qubit), ...s.operations.flatMap((o) => (o.gate === 'MEASURE' ? o.targets : []))])
  return Array.from({ length: s.num_qubits }, (_, q) => q).find((q) => !used.has(q)) ?? 0
}

/** Classical bits written by mid-circuit measurements before operation ``i``: the bits it may depend on. */
function bitsBefore(s: CircuitSpec, i: number): number[] {
  return [...new Set(s.operations.slice(0, i).flatMap((o) => (o.gate === 'MEASURE' ? o.clbits ?? [] : [])))].sort((a, b) => a - b)
}

/** "Make conditional on classical bit X": a checkbox, then one "c[x] = v" per bit; + adds a bit, − drops the last. */
function Condition({ op, bits, onChange }: { op: Operation; bits: number[]; onChange: (c: Operation['conditional']) => void }) {
  const pairs = op.conditional ? condPairs(op.conditional) : []
  const used = pairs.map(([c]) => c)
  const spare = bits.filter((c) => !used.includes(c))
  const set = (k: number, pair: [number, number]) => onChange(condFrom(pairs.map((p, j) => (j === k ? pair : p))))
  return (
    <span className="ff" title={bits.length || pairs.length ? 'Run this gate only when earlier mid-circuit measurements read these values'
      : 'Add a mid-circuit measurement above this gate first: a gate can only depend on a bit measured before it'}>
      <input type="checkbox" aria-label="Make conditional on a classical bit" checked={pairs.length > 0} disabled={!pairs.length && !bits.length}
        onChange={(e) => onChange(e.target.checked ? condFrom([[bits[bits.length - 1], 1]]) : null)} />
      {pairs.length ? (
        <>
          {pairs.map(([c, v], k) => {
            const options = [c, ...spare].sort((a, b) => a - b)
            return (
              <span key={k} className="ff-bit">{k ? 'and ' : 'if '}c<select aria-label="Classical bit" value={c}
                onChange={(e) => set(k, [Number(e.target.value), v])}>
                {options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>=<select aria-label="Value" value={v} onChange={(e) => set(k, [c, Number(e.target.value)])}>
                <option value={1}>1</option><option value={0}>0</option>
              </select></span>
            )
          })}
          {spare.length > 0 && <button className="icon-btn ff-more" title="Also depend on another measured bit"
            onClick={() => onChange(condFrom([...pairs, [spare[0], 1]]))}>+</button>}
          {pairs.length > 1 && <button className="icon-btn ff-more" title="Drop the last bit"
            onClick={() => onChange(condFrom(pairs.slice(0, -1)))}>−</button>}
        </>
      ) : <span className="muted">{bits.length ? 'conditional' : 'measure first'}</span>}
    </span>
  )
}

function IntList({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  const [text, setText] = useState(value.join(', '))
  useEffect(() => { if (parseIntList(text).join() !== value.join()) setText(value.join(', ')) }, [value])
  return <input type="text" value={text} onChange={(e) => { setText(e.target.value); onChange(parseIntList(e.target.value)) }} />
}

function AngleInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [text, setText] = useState(angleText(value))
  const ok = parseAngle(text) !== null
  return (
    <input type="text" className="angle" title="radians, or e.g. pi/4" value={text}
      style={ok ? undefined : { borderColor: 'var(--fail)' }}
      onChange={(e) => { setText(e.target.value); const v = parseAngle(e.target.value); if (v !== null) onChange(v) }} />
  )
}

function NetworkForm({ spec, highlight, onPick, onChange }: {
  spec: NetworkSpec; highlight: string | null; onPick: (k: string | null) => void; onChange: (s: Spec) => void
}) {
  const update = (fn: (s: NetworkSpec) => void) => { const s = clone(spec); fn(s); onChange(s) }
  const setNode = (i: number, patch: Partial<NetNode>) => update((s) => { s.nodes[i] = { ...s.nodes[i], ...patch } })
  const setLink = (i: number, patch: Partial<NetLink>) => update((s) => { s.links[i] = { ...s.links[i], ...patch } })
  const ids = spec.nodes.map((n) => n.id)
  return (
    <div onMouseLeave={() => onPick(null)}>
      <div className="fieldline">
        <label>Title</label>
        <input type="text" style={{ flex: 1 }} value={spec.metadata?.title ?? ''}
          onChange={(e) => update((s) => { s.metadata = { ...s.metadata, title: e.target.value } })} />
      </div>
      <div className="fieldline">
        <label>Pair from</label>
        <select value={spec.source} onChange={(e) => update((s) => { s.source = e.target.value })}>{ids.map((id) => <option key={id}>{id}</option>)}</select>
        <label>to</label>
        <select value={spec.destination} onChange={(e) => update((s) => { s.destination = e.target.value })}>{ids.map((id) => <option key={id}>{id}</option>)}</select>
        <label title="Entanglement purification (BBPSSW) on every segment before swapping: two noisy pairs in, one better pair out">Purification rounds</label>
        <select value={spec.purification_rounds ?? 0} onChange={(e) => update((s) => { s.purification_rounds = Number(e.target.value) })}>
          {[0, 1, 2, 3].map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <h3 style={{ margin: '6px 0' }}>Nodes</h3>
      <table className="ops">
        <thead><tr><th>Id</th><th>Type</th><th>Label</th><th>Memory T2 (ms)</th><th>From sketch</th><th /></tr></thead>
        <tbody>
          {spec.nodes.map((n, i) => (
            <tr key={i} className={highlight === `nodes[${i}]` ? 'hl' : ''} onMouseEnter={() => onPick(`nodes[${i}]`)}>
              <td><input type="text" value={n.id} onChange={(e) => setNode(i, { id: e.target.value })} /></td>
              <td>
                <select value={n.type} onChange={(e) => setNode(i, { type: e.target.value as NetNode['type'] })}>
                  <option value="ground_station">ground station</option><option value="satellite">satellite</option><option value="repeater">repeater</option>
                </select>
              </td>
              <td><input type="text" style={{ width: 150 }} value={n.label ?? ''} onChange={(e) => setNode(i, { label: e.target.value })} /></td>
              <td>{n.type === 'repeater'
                ? <input type="number" style={{ width: 80 }} min={0.001} step={1} value={n.memory_t2_ms ?? 10} onChange={(e) => setNode(i, { memory_t2_ms: Number(e.target.value) })} />
                : <span className="muted">—</span>}</td>
              <td>{n.source ? <span className="chip-src">{Math.round(n.source.confidence * 100)}% sure</span> : <span className="muted">added</span>}</td>
              <td><button className="icon-btn" title="Delete" onClick={() => update((s) => { s.nodes.splice(i, 1) })}><Trash /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3 style={{ margin: '12px 0 6px' }}>Links</h3>
      <table className="ops">
        <thead><tr><th>From</th><th>To</th><th>Medium</th><th>Length (km)</th><th>From sketch</th><th /></tr></thead>
        <tbody>
          {spec.links.map((l, i) => (
            <tr key={i} className={highlight === `links[${i}]` ? 'hl' : ''} onMouseEnter={() => onPick(`links[${i}]`)}>
              <td><select value={l.from} onChange={(e) => setLink(i, { from: e.target.value })}>{ids.map((id) => <option key={id}>{id}</option>)}</select></td>
              <td><select value={l.to} onChange={(e) => setLink(i, { to: e.target.value })}>{ids.map((id) => <option key={id}>{id}</option>)}</select></td>
              <td>
                <select value={l.medium} onChange={(e) => setLink(i, { medium: e.target.value as NetLink['medium'] })}>
                  <option value="fiber">fiber</option><option value="free_space">free space</option>
                </select>
              </td>
              <td><input type="number" style={{ width: 90 }} min={1} value={l.length_km} onChange={(e) => setLink(i, { length_km: Number(e.target.value) })} /></td>
              <td>{l.source ? <span className="chip-src">{Math.round(l.source.confidence * 100)}% sure</span> : <span className="muted">added</span>}</td>
              <td><button className="icon-btn" title="Delete" onClick={() => update((s) => { s.links.splice(i, 1) })}><Trash /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn small" onClick={() => update((s) => { s.nodes.push({ id: `r${s.nodes.length}`, type: 'repeater', label: 'Repeater', memory_t2_ms: 10 }) })}>+ Node</button>
        <button className="btn small" disabled={ids.length < 2} onClick={() => update((s) => { s.links.push({ from: ids[0], to: ids[ids.length - 1], medium: 'fiber', length_km: 50 }) })}>+ Link</button>
      </div>
    </div>
  )
}
