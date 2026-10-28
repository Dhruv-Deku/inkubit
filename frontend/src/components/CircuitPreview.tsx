import type { CircuitSpec, Operation } from '../types'
import { angleText } from '../util'

const COL = 64
const ROW = 46
const LEFT = 46
const MULTI = new Set(['CX', 'CZ', 'CP', 'CCX'])
const SHORT: Record<string, string> = { SDG: 'S†', TDG: 'T†', SX: '√X' }

/** Assign each operation a column, packing gates that touch different qubits. */
function layout(ops: Operation[], n: number): number[] {
  const free = new Array(n).fill(0)
  return ops.map((op) => {
    const qs = [...op.targets, ...(op.controls ?? [])].filter((q) => q >= 0 && q < n)
    const span = qs.length ? [Math.min(...qs), Math.max(...qs)] : [0, n - 1]
    const range = op.gate === 'BARRIER' && !op.targets.length ? [0, n - 1] : span
    const lane = MULTI.has(op.gate) || op.gate === 'SWAP' || op.gate === 'BARRIER'
      ? Array.from({ length: range[1] - range[0] + 1 }, (_, i) => range[0] + i) : qs
    const col = Math.max(0, ...lane.map((q) => free[q]))
    lane.forEach((q) => { free[q] = col + 1 })
    return col
  })
}

/** Live drawing of the spec as it is edited (entangling gates in gold). */
export function CircuitPreview({ spec, highlight, onPick }: {
  spec: CircuitSpec; highlight: string | null; onPick: (k: string) => void
}) {
  const n = Math.max(1, Math.min(spec.num_qubits, 12))
  const ops = spec.operations
  const cols = layout(ops, n)
  const nCols = Math.max(1, ...cols.map((c) => c + 1))
  const width = LEFT + (nCols + 1) * COL + 40
  const height = n * ROW + 16
  const y = (q: number) => 24 + q * ROW
  const x = (c: number) => LEFT + 30 + c * COL
  const mx = x(nCols) + 8
  const measured = new Set(spec.measurements.map((m) => m.qubit))
  ops.forEach((op) => op.gate === 'MEASURE' && op.targets.forEach((q) => measured.add(q)))

  return (
    <div className="preview">
      <svg width={width} height={height} role="img" aria-label="Circuit preview">
        {Array.from({ length: n }, (_, q) => (
          <g key={q}>
            <text x={8} y={y(q) + 4} fontSize={12} fill="var(--muted)" fontFamily="var(--mono)">q{q}</text>
            <line x1={LEFT} x2={width - 10} y1={y(q)} y2={y(q)} stroke="#55585f" strokeWidth={1.5} />
          </g>
        ))}
        {ops.map((op, i) => {
          const cx = x(cols[i])
          const key = `operations[${i}]`
          const hl = highlight === key
          const ink = hl ? '#ffffff' : '#ecebe8'
          const valid = (q: number) => q >= 0 && q < n
          if (MULTI.has(op.gate) && op.controls?.length && op.targets.length) {
            const cs = op.controls, t = op.targets[0]
            if (!cs.every(valid) || !valid(t)) return null
            const ys = [...cs, t].map(y)
            const top = Math.min(...ys), bottom = Math.max(...ys)
            return (
              <g key={i} onMouseEnter={() => onPick(key)} style={{ cursor: 'pointer' }}>
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
              </g>
            )
          }
          if (op.gate === 'SWAP' && op.targets.length === 2 && op.targets.every(valid)) {
            const [a, b] = op.targets
            const xs = (q: number) => `M${cx - 6} ${y(q) - 6}l12 12M${cx + 6} ${y(q) - 6}l-12 12`
            return (
              <g key={i} onMouseEnter={() => onPick(key)}>
                <line x1={cx} x2={cx} y1={y(a)} y2={y(b)} stroke={ink} strokeWidth={1.5} />
                <path d={xs(a) + xs(b)} stroke={ink} strokeWidth={2} />
              </g>
            )
          }
          if (op.gate === 'BARRIER') {
            return <line key={i} x1={cx} x2={cx} y1={6} y2={height - 6} stroke="#6b6e76" strokeDasharray="4 4" />
          }
          return (
            <g key={i} onMouseEnter={() => onPick(key)} style={{ cursor: 'pointer' }}>
              {op.targets.filter(valid).map((q) => {
                const label = SHORT[op.gate] ?? op.gate
                return (
                  <g key={q}>
                    <rect x={cx - 17} y={y(q) - 15} width={34} height={30} rx={6}
                      fill={hl ? '#3a3d45' : '#2d3036'} stroke={hl ? '#fff' : '#5c6068'} strokeWidth={1.2} />
                    <text x={cx} y={y(q) + 4.5} textAnchor="middle" fontSize={12.5} fontWeight={600} fill={ink}>{label}</text>
                    {op.params?.length ? (
                      <text x={cx} y={y(q) + 25} textAnchor="middle" fontSize={9.5} fill="var(--muted)">{angleText(op.params[0])}</text>
                    ) : null}
                  </g>
                )
              })}
            </g>
          )
        })}
        {Array.from({ length: n }, (_, q) => measured.has(q) && (
          <g key={`m${q}`}>
            <rect x={mx - 16} y={y(q) - 14} width={32} height={28} rx={6} fill="#2d3036" stroke="#5c6068" />
            <path d={`M${mx - 9} ${y(q) + 6}a9 9 0 0118 0`} stroke="#ecebe8" fill="none" strokeWidth={1.4} />
            <path d={`M${mx} ${y(q) + 6}l6 -10`} stroke="#ecebe8" strokeWidth={1.4} />
          </g>
        ))}
      </svg>
    </div>
  )
}
