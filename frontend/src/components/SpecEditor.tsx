import { useEffect, useState } from 'react'
import type { CircuitSpec, Gate, NetLink, NetNode, NetworkSpec, Operation, Spec, SpecIssue } from '../types'
import { GATE_LABEL, GATES } from '../types'
import { angleText, clone, parseAngle, parseIntList, resizeCircuit } from '../util'
import { CircuitPreview } from './CircuitPreview'
import { Down, Trash, Up } from './Icons'

interface Props {
  spec: Spec
  issues: SpecIssue[]
  highlight: string | null
  onPick: (key: string | null) => void
  onChange: (spec: Spec) => void
}

export function SpecEditor({ spec, issues, highlight, onPick, onChange }: Props) {
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
          ? <CircuitForm spec={spec} highlight={highlight} onPick={onPick} onChange={onChange} />
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

function CircuitForm({ spec, highlight, onPick, onChange }: {
  spec: CircuitSpec; highlight: string | null; onPick: (k: string | null) => void; onChange: (s: Spec) => void
}) {
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
      <CircuitPreview spec={spec} highlight={highlight} onPick={onPick} />
      <table className="ops" style={{ marginTop: 12 }} onMouseLeave={() => onPick(null)}>
        <thead>
          <tr><th>#</th><th>Gate</th><th>Target</th><th>Control</th><th>Angle</th><th>From sketch</th><th /></tr>
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
        <span className="spacer grow" />
        <span className="sub">Measure:</span>
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
