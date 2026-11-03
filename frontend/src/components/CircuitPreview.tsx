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

/** Classical bits a feed-forward drawing shows as wires: those mid-circuit measurements write or gates read. */
function classicalBits(ops: Operation[]): number {
  const used = ops.flatMap((op) => [...(op.gate === 'MEASURE' ? op.clbits ?? [] : []),
    ...(op.conditional ? [op.conditional.classical_register] : [])])
  return used.length ? Math.max(...used) + 1 : 0
}

/** Assign each operation a column, packing gates that touch different qubits; also the next free column per wire.
 * Classical bits are lanes after the qubits: a measurement or a conditional gate occupies every wire its vertical line
 * crosses, so a gate that reads a bit is always drawn after the measurement that writes it. */
function layout(ops: Operation[], n: number, nc: number): { cols: number[]; free: number[] } {
  const free = new Array(n + nc).fill(0)
  const cols = ops.map((op) => {
    const qs = [...op.targets, ...(op.controls ?? [])].filter((q) => q >= 0 && q < n)
    const span = qs.length ? [Math.min(...qs), Math.max(...qs)] : [0, n - 1]
    const range = op.gate === 'BARRIER' && !op.targets.length ? [0, n - 1] : span
    let lane = MULTI.has(op.gate) || op.gate === 'SWAP' || op.gate === 'BARRIER'
      ? Array.from({ length: range[1] - range[0] + 1 }, (_, i) => range[0] + i) : qs
    const bits = op.gate === 'MEASURE' && nc ? op.clbits ?? [] : op.conditional ? [op.conditional.classical_register] : []
    if (bits.length && qs.length) {
      const deepest = Math.max(...bits.filter((c) => c < nc), 0)
      lane = Array.from({ length: n + deepest + 1 - Math.min(...qs) }, (_, i) => Math.min(...qs) + i)
    }
    const col = Math.max(0, ...lane.map((q) => free[q]))
    lane.forEach((q) => { free[q] = col + 1 })
    return col
  })
  return { cols, free: free.slice(0, n) }
}

/** Live drawing of the spec as it is edited (entangling gates in gold); with ``compose``, click wires to add gates. */
export function CircuitPreview({ spec, highlight, onPick, compose }: {
  spec: CircuitSpec; highlight: string | null; onPick: (k: string) => void; compose?: Compose
}) {
  const [hoverQ, setHoverQ] = useState<number | null>(null)
  const n = Math.max(1, Math.min(spec.num_qubits, 12))
  const ops = spec.operations
  const nc = Math.min(classicalBits(ops), 12)
  const { cols, free } = layout(ops, n, nc)
  const nCols = Math.max(1, ...cols.map((c) => c + 1))
  const adding = compose && compose.tool && compose.tool !== 'ERASE' ? compose.tool : null
  const erasing = compose?.tool === 'ERASE'
  const pickedQs = [...(compose?.pending ?? []), ...(hoverQ !== null && !compose?.pending.includes(hoverQ) ? [hoverQ] : [])]
  const ghostCol = adding && pickedQs.length ? Math.max(0, ...lane(adding, pickedQs, n).map((q) => free[q])) : nCols
  const width = LEFT + (Math.max(nCols, ghostCol + 1) + 1 + (adding ? 1 : 0)) * COL + 40
  const CROW = 30
  const height = n * ROW + 16 + (nc ? nc * CROW + 6 : 0)
  const y = (q: number) => 24 + q * ROW
  const yc = (c: number) => y(n - 1) + ROW * 0.85 + c * CROW // classical bit wires sit under the qubits
  const x = (c: number) => LEFT + 30 + c * COL
  const mx = x(adding ? Math.max(nCols, ghostCol + 1) : nCols) + 8
  const measured = new Set(spec.measurements.map((m) => m.qubit)) // terminal meters; MEASURE ops draw in place
  const valid = (q: number) => q >= 0 && q < n

  const meter = (mx: number, my: number, hl = false) => (
    <g>
      <rect x={mx - 16} y={my - 14} width={32} height={28} rx={6} fill={hl ? '#3a3d45' : '#2d3036'} stroke={hl ? '#fff' : '#5c6068'} />
      <path d={`M${mx - 9} ${my + 6}a9 9 0 0118 0`} stroke="#ecebe8" fill="none" strokeWidth={1.4} />
      <path d={`M${mx} ${my + 6}l6 -10`} stroke="#ecebe8" strokeWidth={1.4} />
    </g>
  )

  /** Feed-forward: a dashed line from the gate down to the bit it reads, a dot there (filled 1, hollow 0) and "=v". */
  const condition = (op: Operation, cx: number, from: number): ReactElement | null => {
    const cond = op.conditional
    if (!cond || cond.classical_register >= nc) return null
    const cy = yc(cond.classical_register)
    return (
      <g pointerEvents="none">
        <line x1={cx} x2={cx} y1={from} y2={cy} stroke="var(--primary)" strokeWidth={1.6} strokeDasharray="4 3" />
        <circle cx={cx} cy={cy} r={4.5} fill={cond.value ? 'var(--primary)' : 'var(--bg)'} stroke="var(--primary)" strokeWidth={1.6} />
        <text x={cx + 8} y={cy - 6} fontSize={10.5} fill="var(--primary)" fontFamily="var(--mono)">={cond.value}</text>
      </g>
    )
  }

  const drawOp = (op: Operation, i: number): ReactElement | null => {
    const el = drawGate(op, i)
    if (!el || !op.conditional) return el
    const qs = [...op.targets, ...(op.controls ?? [])].filter(valid)
    if (!qs.length) return el
    const bottom = Math.max(...qs.map(y)) + (op.gate === 'CX' || op.gate === 'CCX' ? 11 : 15)
    return <>{el}{condition(op, x(cols[i]), bottom)}</>
  }

  const drawGate = (op: Operation, i: number): ReactElement | null => {
    const cx = x(cols[i])
    const hl = highlight === `operations[${i}]`
    const ink = hl ? '#ffffff' : '#ecebe8'
    if (op.gate === 'MEASURE') {
      const ys = op.targets.filter(valid).map(y)
      if (!ys.length) return null
      return (
        <>
          {op.targets.map((q, k) => {
            const c = op.clbits?.[k]
            if (!valid(q)) return null
            return (
              <g key={q}>
                {c !== undefined && c < nc && (
                  <path d={`M${cx - 2} ${y(q) + 14}V${yc(c) - 5}M${cx + 2} ${y(q) + 14}V${yc(c) - 5}`} stroke="#8b8f98" strokeWidth={1.2} />
                )}
                {c !== undefined && c < nc && <path d={`M${cx - 5} ${yc(c) - 7}l5 6l5 -6z`} fill="#8b8f98" />}
                {meter(cx, y(q), hl)}
              </g>
            )
          })}
          <rect x={cx - 17} y={Math.min(...ys) - 15} width={34} height={Math.max(...ys) - Math.min(...ys) + 30} fill="transparent" />
        </>
      )
    }
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
        {Array.from({ length: nc }, (_, c) => (
          <g key={`c${c}`} pointerEvents="none">
            <text x={8} y={yc(c) + 4} fontSize={12} fill="var(--muted)" fontFamily="var(--mono)">c{c}</text>
            <path d={`M${LEFT} ${yc(c) - 1.5}H${width - 10}M${LEFT} ${yc(c) + 1.5}H${width - 10}`} stroke="#45484f" strokeWidth={1} />
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
          <g key={`m${q}`} pointerEvents="none">{meter(mx, y(q))}</g>
        ))}
      </svg>
    </div>
  )
}
