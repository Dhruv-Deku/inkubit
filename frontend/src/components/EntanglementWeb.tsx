import type { StepState } from '../types'

/**
 * Who is entangled with whom, for one exact state. Qubits sit on a ring; a gold thread joins two
 * qubits that are entangled as a pair (thicker = higher concurrence), and a gold arc around a qubit
 * shows how entangled it is with the rest (entanglement entropy, 0 to 1 bit).
 */
export function EntanglementWeb({ step, size = 150 }: { step: StepState; size?: number }) {
  const n = step.bloch.length
  const entropy = step.entropy ?? []
  const links = step.links ?? []
  if (n < 2 || !entropy.length) return null
  const node = Math.max(9, Math.min(14, 46 / Math.sqrt(n)))
  const h = n === 2 ? 2 * node + 16 : size  // two qubits sit on one line: no need for a square
  const c = size / 2, r = n === 2 ? size * 0.3 : size * 0.33
  const at = (q: number): [number, number] => {
    if (n === 2) return [c + (q === 0 ? -r : r), h / 2]
    const a = -Math.PI / 2 + (2 * Math.PI * q) / n
    return [c + r * Math.cos(a), c + r * Math.sin(a)]
  }
  const tangled = entropy.filter((s) => s > 0.01).length
  const group = tangled >= 2 && !links.length  // e.g. GHZ: entangled as a whole, no pair on its own
  const arc = (q: number, frac: number) => {
    const [x, y] = at(q)
    const R = node + 4
    if (frac >= 0.999) return <circle cx={x} cy={y} r={R} fill="none" stroke="var(--gold)" strokeWidth={2.2} />
    const end = -Math.PI / 2 + 2 * Math.PI * frac
    const large = frac > 0.5 ? 1 : 0
    return <path d={`M${x} ${y - R}A${R} ${R} 0 ${large} 1 ${x + R * Math.cos(end)} ${y + R * Math.sin(end)}`}
      fill="none" stroke="var(--gold)" strokeWidth={2.2} strokeLinecap="round" />
  }
  const caption = !tangled ? 'no entanglement: every qubit stands alone'
    : group ? `${tangled} qubits entangled as a group; no pair on its own (GHZ-type)`
      : `${links.length} entangled pair${links.length === 1 ? '' : 's'}`
  return (
    <figure className="ent-web">
      <svg viewBox={`0 0 ${size} ${h}`} width={size} height={h} role="img"
        aria-label={`Entanglement web: ${caption}`}>
        {group && (
          <polygon points={entropy.flatMap((s, q) => (s > 0.01 ? [at(q).join(',')] : [])).join(' ')}
            fill="var(--gold)" fillOpacity={0.07} stroke="var(--gold)" strokeOpacity={0.55} strokeDasharray="3 4" />
        )}
        {links.map(([a, b, conc]) => {
          const [x1, y1] = at(a), [x2, y2] = at(b)
          return (
            <line key={`${a}-${b}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--gold)" strokeLinecap="round"
              strokeWidth={1 + 4 * conc} strokeOpacity={0.35 + 0.6 * conc} className="ent-thread">
              <title>{`q${a} and q${b}: concurrence ${conc.toFixed(2)}`}</title>
            </line>
          )
        })}
        {Array.from({ length: n }, (_, q) => {
          const [x, y] = at(q)
          const s = entropy[q] ?? 0
          return (
            <g key={q}>
              <circle cx={x} cy={y} r={node} fill="var(--panel-2)" stroke={s > 0.01 ? 'var(--gold)' : 'var(--line-2)'}
                strokeOpacity={s > 0.01 ? 0.5 : 1} />
              {s > 0.01 && arc(q, Math.min(1, s))}
              <text x={x} y={y + 4} textAnchor="middle" fontSize={11} fill="var(--text)" fontFamily="var(--mono)">q{q}</text>
              <title>{`q${q}: ${s.toFixed(2)} bit of entanglement with the rest`}</title>
            </g>
          )
        })}
      </svg>
      <figcaption className="sub">{caption}</figcaption>
    </figure>
  )
}
