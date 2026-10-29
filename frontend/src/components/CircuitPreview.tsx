import { useState, type ReactElement } from 'react'
import type { CircuitSpec, Gate, Operation } from '../types'
import { angleText } from '../util'

const COL = 64
const ROW = 46
const LEFT = 46
const MULTI = new Set(['CX', 'CZ', 'CP', 'CCX'])
export const SHORT: Record<string, string> = { SDG: 'S†', TDG: 'T†', SX: '√X' }

/** How many wires a composer click sequence picks for a gate: controls first, then the target. */
export const wiresFor = (g: Gate) => (g === 'CCX' ? 3 : MULTI.has(g) || g === 'SWAP' ? 2 : 1)

/** Click-to-compose state, owned by the editor. */
export interface Compose {
  tool: Gate | 'ERASE' | null
  pending: number[]  // wires already picked for a multi-qubit gate
  onWire: (q: number) => void
  onGate: (i: number) => void
}

/** The wires a gate occupies in the drawing: multi-qubit gates block every wire between their ends. */
function lane(gate: Gate, qs: number[], n: number): number[] {
  const span = qs.length ? [Math.min(...qs), Math.max(...qs)] : [0, n - 1]
  return MULTI.has(gate) || gate === 'SWAP' || gate === 'BARRIER'
    ? Array.from({ length: span[1] - span[0] + 1 }, (_, i) => span[0] + i) : qs
}

/** Assign each operation a column, packing gates that touch different qubits; also the next free column per wire. */
function layout(ops: Operation[], n: number): { cols: number[]; free: number[] } {
  const free = new Array(n).fill(0)
  const cols = ops.map((op) => {
    const qs = [...op.targets, ...(op.controls ?? [])].filter((q) => q >= 0 && q < n)
    const span = qs.length ? [Math.min(...qs), Math.max(...qs)] : [0, n - 1]
    const range = op.gate === 'BARRIER' && !op.targets.length ? [0, n - 1] : span
    const lane = MULTI.has(op.gate) || op.gate === 'SWAP' || op.gate === 'BARRIER'
      ? Array.from({ length: range[1] - range[0] + 1 }, (_, i) => range[0] + i) : qs
    const col = Math.max(0, ...lane.map((q) => free[q]))
    lane.forEach((q) => { free[q] = col + 1 })
    return col
  })
  return { cols, free }
}

/** Live drawing of the spec as it is edited (entangling gates in gold); with ``compose``, click wires to add gates. */
export function CircuitPreview({ spec, highlight, onPick, compose }: {
  spec: CircuitSpec; highlight: string | null; onPick: (k: string) => void; compose?: Compose
}) {
  const [hoverQ, setHoverQ] = useState<number | null>(null)
  const n = Math.max(1, Math.min(spec.num_qubits, 12))
  const ops = spec.operations
  const { cols, free } = layout(ops, n)
  const nCols = Math.max(1, ...cols.map((c) => c + 1))
  const adding = compose && compose.tool && compose.tool !== 'ERASE' ? compose.tool : null
  const erasing = compose?.tool === 'ERASE'
  const pickedQs = [...(compose?.pending ?? []), ...(hoverQ !== null && !compose?.pending.includes(hoverQ) ? [hoverQ] : [])]
  const ghostCol = adding && pickedQs.length ? Math.max(0, ...lane(adding, pickedQs, n).map((q) => free[q])) : nCols
  const width = LEFT + (Math.max(nCols, ghostCol + 1) + 1 + (adding ? 1 : 0)) * COL + 40
  const height = n * ROW + 16
  const y = (q: number) => 24 + q * ROW
  const x = (c: number) => LEFT + 30 + c * COL
  const mx = x(adding ? Math.max(nCols, ghostCol + 1) : nCols) + 8
  const measured = new Set(spec.measurements.map((m) => m.qubit))
  ops.forEach((op) => op.gate === 'MEASURE' && op.targets.forEach((q) => measured.add(q)))
  const valid = (q: number) => q >= 0 && q < n

  const drawOp = (op: Operation, i: number): ReactElement | null => {
    const cx = x(cols[i])
    const hl = highlight === `operations[${i}]`
    const ink = hl ? '#ffffff' : '#ecebe8'
    if (MULTI.has(op.gate) && op.controls?.length && op.targets.length) {
      const cs = op.controls, t = op.targets[0]
      if (!cs.every(valid) || !valid(t)) return null
      const ys = [...cs, t].map(y)
      const top = Math.min(...ys), bottom = Math.max(...ys)
      return (
        <>
          <line x1={cx} x2={cx} y1={top} y2={bottom} stroke="var(--gold)" strokeWidth={2} />
          {cs.map((c) => <circle key={c} cx={cx} cy={y(c)} r={5.5} fill="var(--gold)" />)}
          {op.gate === 'CP' && (
            <text x={cx + 9} y={(top + bottom) / 2 + 4} fontSize={10.5} fill="var(--gold)" fontFamily="var(--mono)">
              P({angleText(op.params?.[0] ?? 0)})
            </text>
          )}
          {op.gate === 'CX' || op.gate === 'CCX' ? (
            <g>
              <circle cx={cx} cy={y(t)} r={11} fill="var(--panel-2)" stroke="var(--gold)" strokeWidth={2} />
              <path d={`M${cx - 11} ${y(t)}h22M${cx} ${y(t) - 11}v22`} stroke="var(--gold)" strokeWidth={2} />
            </g>
          ) : <circle cx={cx} cy={y(t)} r={5.5} fill="var(--gold)" />}
          {hl && <rect x={cx - 17} y={top - 17} width={34} height={bottom - top + 34} rx={6} fill="none" stroke="#fff" strokeDasharray="3 3" />}
          <rect x={cx - 17} y={top - 17} width={34} height={bottom - top + 34} fill="transparent" />
        </>
      )
    }
    if (op.gate === 'SWAP' && op.targets.length === 2 && op.targets.every(valid)) {
      const [a, b] = op.targets
      const xs = (q: number) => `M${cx - 6} ${y(q) - 6}l12 12M${cx + 6} ${y(q) - 6}l-12 12`
      return (
        <>
          <line x1={cx} x2={cx} y1={y(a)} y2={y(b)} stroke={ink} strokeWidth={1.5} />
          <path d={xs(a) + xs(b)} stroke={ink} strokeWidth={2} />
          <rect x={cx - 12} y={Math.min(y(a), y(b)) - 12} width={24} height={Math.abs(y(a) - y(b)) + 24} fill="transparent" />
        </>
      )
    }
    if (op.gate === 'BARRIER') {
      return <line x1={cx} x2={cx} y1={6} y2={height - 6} stroke="#6b6e76" strokeDasharray="4 4" />
    }
    return (
      <>
        {op.targets.filter(valid).map((q) => (
          <g key={q}>
            <rect x={cx - 17} y={y(q) - 15} width={34} height={30} rx={6}
              fill={hl ? '#3a3d45' : '#2d3036'} stroke={hl ? '#fff' : '#5c6068'} strokeWidth={1.2} />
            <text x={cx} y={y(q) + 4.5} textAnchor="middle" fontSize={12.5} fontWeight={600} fill={ink}>{SHORT[op.gate] ?? op.gate}</text>
            {op.params?.length ? (
              <text x={cx} y={y(q) + 25} textAnchor="middle" fontSize={9.5} fill="var(--muted)">{angleText(op.params[0])}</text>
            ) : null}
          </g>
        ))}
      </>
    )
  }

  /** Where the next click would put the gate: dashed, at the end of the circuit. */
  const ghost = () => {
    if (!adding || !compose) return null
    const gx = x(ghostCol)
    const picked = compose.pending
    const need = wiresFor(adding)
    const parts: ReactElement[] = []
    const allQs = [...picked, ...(hoverQ !== null && !picked.includes(hoverQ) ? [hoverQ] : [])]
    if (need > 1 && allQs.length > 1) {
      parts.push(<line key="l" x1={gx} x2={gx} y1={y(Math.min(...allQs))} y2={y(Math.max(...allQs))} stroke="var(--gold)" strokeWidth={1.6} strokeDasharray="4 3" />)
    }
    picked.forEach((q) => parts.push(adding === 'SWAP'
      ? <path key={`p${q}`} d={`M${gx - 6} ${y(q) - 6}l12 12M${gx + 6} ${y(q) - 6}l-12 12`} stroke="var(--text)" strokeWidth={2} />
      : <circle key={`p${q}`} cx={gx} cy={y(q)} r={5.5} fill="var(--gold)" />))
    if (hoverQ !== null && !picked.includes(hoverQ)) {
      const last = picked.length === need - 1
      const q = hoverQ
      if (need === 1) {
        parts.push(
          <g key="h">
            <rect x={gx - 17} y={y(q) - 15} width={34} height={30} rx={6} fill="rgba(57,135,229,0.12)" stroke="var(--primary)" strokeDasharray="4 3" />
            <text x={gx} y={y(q) + 4.5} textAnchor="middle" fontSize={12.5} fontWeight={600} fill="var(--text-2)">{SHORT[adding] ?? adding}</text>
          </g>)
      } else if (adding === 'SWAP') {
        parts.push(<path key="h" d={`M${gx - 6} ${y(q) - 6}l12 12M${gx + 6} ${y(q) - 6}l-12 12`} stroke="var(--text-2)" strokeWidth={2} opacity={0.7} />)
      } else if (last && (adding === 'CX' || adding === 'CCX')) {
        parts.push(
          <g key="h" opacity={0.75}>
            <circle cx={gx} cy={y(q)} r={11} fill="none" stroke="var(--gold)" strokeWidth={1.8} strokeDasharray="4 3" />
            <path d={`M${gx - 11} ${y(q)}h22M${gx} ${y(q) - 11}v22`} stroke="var(--gold)" strokeWidth={1.6} />
          </g>)
      } else {
        parts.push(<circle key="h" cx={gx} cy={y(q)} r={5.5} fill="none" stroke="var(--gold)" strokeWidth={1.8} />)
      }
    }
    return <g pointerEvents="none">{parts}</g>
  }

  return (
    <div className={`preview ${adding ? 'composing' : ''} ${erasing ? 'erasing' : ''}`}>
      <svg width={width} height={height} role="img" aria-label="Circuit preview">
        {Array.from({ length: n }, (_, q) => (
          <g key={q}>
            <text x={8} y={y(q) + 4} fontSize={12} fill={hoverQ === q && adding ? 'var(--text)' : 'var(--muted)'} fontFamily="var(--mono)">q{q}</text>
            <line x1={LEFT} x2={width - 10} y1={y(q)} y2={y(q)} stroke={hoverQ === q && adding ? '#7a7e87' : '#55585f'} strokeWidth={1.5} />
          </g>
        ))}
        {adding && compose && Array.from({ length: n }, (_, q) => (
          <rect key={`hit${q}`} x={0} y={y(q) - ROW / 2} width={width} height={ROW} fill="transparent" style={{ cursor: 'crosshair' }}
            onMouseEnter={() => setHoverQ(q)} onMouseLeave={() => setHoverQ(null)} onClick={() => compose.onWire(q)}
            role="button" aria-label={`Add to q${q}`} />
        ))}
        {ops.map((op, i) => {
          const el = drawOp(op, i)
          return el && (
            <g key={i} className={erasing ? 'op erasable' : 'op'} onMouseEnter={() => onPick(`operations[${i}]`)}
              onClick={erasing ? () => compose?.onGate(i) : undefined} style={{ cursor: erasing ? 'pointer' : adding ? 'crosshair' : 'default' }}
              pointerEvents={adding ? 'none' : undefined}>
              {el}
            </g>
          )
        })}
        {ghost()}
        {Array.from({ length: n }, (_, q) => measured.has(q) && (
          <g key={`m${q}`} pointerEvents="none">
            <rect x={mx - 16} y={y(q) - 14} width={32} height={28} rx={6} fill="#2d3036" stroke="#5c6068" />
            <path d={`M${mx - 9} ${y(q) + 6}a9 9 0 0118 0`} stroke="#ecebe8" fill="none" strokeWidth={1.4} />
            <path d={`M${mx} ${y(q) + 6}l6 -10`} stroke="#ecebe8" strokeWidth={1.4} />
          </g>
        ))}
      </svg>
    </div>
  )
}
