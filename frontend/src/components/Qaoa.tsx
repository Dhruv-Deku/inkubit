import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { CircuitSpec, QaoaLab, QaoaSplit } from '../types'
import { pct } from '../util'

// Two tables. Validated pair on the dark panel (CVD-safe); shape repeats the team so colour is never alone.
const TEAM = ['#3987e5', '#d0702c']
const TABLE = ['Table A', 'Table B']
const NAMES = ['Ana', 'Ben', 'Cai', 'Dev', 'Eli', 'Fay', 'Gus', 'Hal']
const MIN = 3, MAX = 8

type Edge = [number, number]
interface Graph { n: number; edges: Edge[]; pos?: [number, number][] }

const ring = (n: number): Edge[] => Array.from({ length: n }, (_, i) => [Math.min(i, (i + 1) % n), Math.max(i, (i + 1) % n)] as Edge)
const PRESETS: { id: string; label: string; graph: Graph }[] = [
  { id: 'party', label: 'Dinner party', graph: { n: 6, edges: [[0, 1], [1, 2], [0, 2], [2, 3], [3, 4], [4, 5], [3, 5], [1, 4]] } },
  { id: 'ring5', label: 'Ring of 5', graph: { n: 5, edges: ring(5) } },
  { id: 'all5', label: 'Everyone feuds', graph: { n: 5, edges: [[0, 1], [0, 2], [0, 3], [0, 4], [1, 2], [1, 3], [1, 4], [2, 3], [2, 4], [3, 4]] } },
  {
    id: 'cube', label: 'Office of 8', graph: {
      n: 8, edges: [[0, 1], [1, 2], [2, 3], [0, 3], [4, 5], [5, 6], [6, 7], [4, 7], [0, 4], [1, 5], [2, 6], [3, 7]],
      pos: [[-95, -95], [95, -95], [95, 95], [-95, 95], [-42, -42], [42, -42], [42, 42], [-42, 42]],
    },
  },
]

const key = (a: number, b: number) => `${Math.min(a, b)}-${Math.max(a, b)}`
const signature = (n: number, edges: Edge[]) => `${n}:${edges.map(([a, b]) => key(a, b)).sort().join(',')}`

// ---------------------------------------------------------------- exact depth-1 QAOA in the browser (n <= 8)

function cutsOf(n: number, edges: Edge[]): Float64Array {
  const out = new Float64Array(1 << n)
  for (let i = 0; i < out.length; i++) for (const [a, b] of edges) out[i] += ((i >> a) ^ (i >> b)) & 1
  return out
}

/** |+>^n, then exp(-i g C) and exp(-i b X) on every qubit; the same circuit the backend optimises. */
function depthOne(n: number, cuts: Float64Array, g: number, b: number): Float64Array {
  const N = 1 << n, amp = Math.pow(2, -n / 2)
  const re = new Float64Array(N), im = new Float64Array(N)
  for (let i = 0; i < N; i++) { re[i] = amp * Math.cos(g * cuts[i]); im[i] = -amp * Math.sin(g * cuts[i]) }
  const c = Math.cos(b), s = Math.sin(b)
  for (let k = 0; k < n; k++) {
    const bit = 1 << k
    for (let i = 0; i < N; i++) {
      if (i & bit) continue
      const j = i | bit
      const r0 = re[i], i0 = im[i], r1 = re[j], i1 = im[j]
      re[i] = c * r0 + s * i1; im[i] = c * i0 - s * r1   // c*a0 - i s*a1
      re[j] = c * r1 + s * i0; im[j] = c * i1 - s * r0   // c*a1 - i s*a0
    }
  }
  const probs = new Float64Array(N)
  for (let i = 0; i < N; i++) probs[i] = re[i] * re[i] + im[i] * im[i]
  return probs
}

function fold(n: number, probs: Float64Array, cuts: Float64Array, best: number): QaoaSplit[] {
  const full = (1 << n) - 1
  const merged = new Map<number, number>()
  probs.forEach((p, i) => { const k = i & 1 ? i ^ full : i; merged.set(k, (merged.get(k) ?? 0) + p) })
  return [...merged.entries()].sort((a, b) => b[1] - a[1] || cuts[b[0]] - cuts[a[0]] || a[0] - b[0]).slice(0, 8)
    .map(([k, p]) => ({ teams: Array.from({ length: n }, (_, q) => (k >> q) & 1), cut: cuts[k], prob: p, optimal: cuts[k] === best }))
}

function specFor(n: number, edges: Edge[], g: number, b: number, names: string[]): CircuitSpec {
  const ops: CircuitSpec['operations'] = [{ gate: 'H', targets: Array.from({ length: n }, (_, q) => q), controls: [], params: [] }]
  for (const [i, j] of edges) {
    ops.push({ gate: 'CX', controls: [i], targets: [j], params: [] },
      { gate: 'RZ', controls: [], targets: [j], params: [+(-g).toFixed(6)] },
      { gate: 'CX', controls: [i], targets: [j], params: [] })
  }
  for (let q = 0; q < n; q++) ops.push({ gate: 'RX', controls: [], targets: [q], params: [+(2 * b).toFixed(6)] })
  return {
    kind: 'circuit', version: '1.0', num_qubits: n, num_clbits: n, operations: ops,
    measurements: Array.from({ length: n }, (_, q) => ({ qubit: q, clbit: q })),
    metadata: {
      title: `QAOA Max-Cut, ${edges.length} edges, your angles`, origin: 'manual',
      notes: `Each qubit is a guest (${names.map((x, k) => `q${k} = ${x}`).join(', ')}). One layer at the angles you picked: γ = ${g.toFixed(3)}, β = ${b.toFixed(3)}.`,
    },
  } as CircuitSpec
}

// ---------------------------------------------------------------- the seating chart

function Seating({ graph, names, split, sel, onNode }: {
  graph: Graph; names: string[]; split: QaoaSplit | null; sel: number | null; onNode: (i: number) => void
}) {
  const W = 300, H = 290, R = 108
  const pos = (i: number): [number, number] => {
    const p = graph.pos?.[i]
    if (p) return [W / 2 + p[0], H / 2 + p[1]]
    const t = -Math.PI / 2 + (2 * Math.PI * i) / graph.n
    return [W / 2 + R * Math.cos(t), H / 2 + R * Math.sin(t)]
  }
  const team = (i: number) => (split ? split.teams[i] : null)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block', margin: '0 auto', touchAction: 'manipulation' }}
      role="img" aria-label={`${graph.n} guests and ${graph.edges.length} feuds${split ? `; this seating defuses ${split.cut}` : ''}`}>
      {graph.edges.map(([a, b]) => {
        const [x1, y1] = pos(a), [x2, y2] = pos(b)
        const same = split !== null && team(a) === team(b)
        return <line key={key(a, b)} x1={x1} y1={y1} x2={x2} y2={y2} stroke={same ? 'var(--fail)' : 'var(--text-2)'}
          strokeOpacity={same ? 0.95 : split ? 0.45 : 0.7} strokeWidth={same ? 2 : 1.5} strokeDasharray={same ? '5 4' : undefined}>
          <title>{`${names[a]} and ${names[b]} ${same ? 'feud at the same table' : split ? 'sit apart: defused' : 'feud'}`}</title>
        </line>
      })}
      {Array.from({ length: graph.n }, (_, i) => {
        const [x, y] = pos(i)
        const t = team(i)
        const fill = t === null ? 'var(--panel-3)' : TEAM[t]
        const ink = t === null ? 'var(--text)' : '#111214'
        return (
          <g key={i} onClick={() => onNode(i)} style={{ cursor: 'pointer' }} role="button"
            aria-label={`${names[i]}${t !== null ? `, ${TABLE[t]}` : ''}${sel === i ? ', selected' : ''}`}>
            <circle cx={x} cy={y} r={24} fill="transparent" />
            {sel === i && <circle cx={x} cy={y} r={22} fill="none" stroke="var(--text)" strokeWidth={1.5} strokeDasharray="3 3" />}
            {t === 1
              ? <rect x={x - 16} y={y - 16} width={32} height={32} rx={7} fill={fill} stroke="var(--panel)" strokeWidth={2} />
              : <circle cx={x} cy={y} r={17} fill={fill} stroke={t === null ? 'var(--line-2)' : 'var(--panel)'} strokeWidth={2} />}
            <text x={x} y={y + 4} textAnchor="middle" fontSize={11} fontWeight={600} fill={ink} pointerEvents="none">{names[i]}</text>
          </g>
        )
      })}
    </svg>
  )
}

// ---------------------------------------------------------------- the depth-1 landscape

const PI = Math.PI
/** Opaque blend from the panel to the primary blue (overlapping translucent cells would show seams). */
const shade = (t: number) => {
  const a = [27, 28, 32], b = [57, 135, 229]
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`
}
function Landscape({ lab, mine, onPick }: { lab: QaoaLab; mine: [number, number] | null; onPick: (g: number, b: number) => void }) {
  const W = 470, H = 268, L = 40, R = 10, T = 10, B = 36
  const cols = lab.gammas.length, rows = lab.betas.length
  const cw = (W - L - R) / cols, ch = (H - T - B) / rows
  const flat = lab.landscape.flat()
  const lo = Math.min(...flat), hi = Math.max(...flat)
  const gx = (g: number) => L + (g / PI) * (W - L - R)
  const by = (b: number) => H - B - (b / (PI / 2)) * (H - T - B)
  const [hover, setHover] = useState<{ g: number; b: number; v: number } | null>(null)
  const pathPts = lab.path.map(([g, b]) => `${gx(g).toFixed(1)},${by(b).toFixed(1)}`).join(' ')
  const end = lab.path[lab.path.length - 1]
  const at = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * W, py = ((e.clientY - box.top) / box.height) * H
    const g = Math.min(PI, Math.max(0, ((px - L) / (W - L - R)) * PI))
    const b = Math.min(PI / 2, Math.max(0, ((H - B - py) / (H - T - B)) * (PI / 2)))
    const c = Math.min(cols - 1, Math.floor((g / PI) * cols)), r = Math.min(rows - 1, Math.floor((b / (PI / 2)) * rows))
    return { g, b, v: lab.landscape[r][c] }
  }
  return (
    <div>
      <div className="sub mono qaoa-readout" aria-live="polite">
        {hover ? `γ ${hover.g.toFixed(2)} · β ${hover.b.toFixed(2)} → expects ${pct(hover.v, 0)} of the best cut · click to try it`
          : `one layer, every angle pair: brighter expects a bigger cut (${pct(lo, 0)} to ${pct(hi, 0)})`}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block', cursor: 'crosshair', touchAction: 'manipulation' }}
        role="img" aria-label={`Expected cut for one QAOA layer over gamma 0 to pi and beta 0 to pi/2; the optimizer ends at gamma ${end[0].toFixed(2)}, beta ${end[1].toFixed(2)}`}
        onMouseMove={(e) => setHover(at(e))} onMouseLeave={() => setHover(null)}
        onClick={(e) => { const p = at(e); onPick(p.g, p.b) }}>
        {lab.landscape.map((row, r) => row.map((v, c) => (
          <rect key={`${r}-${c}`} x={L + c * cw} y={H - B - (r + 1) * ch} width={cw + 0.4} height={ch + 0.4}
            fill={shade(0.05 + 0.95 * Math.pow((v - lo) / Math.max(1e-9, hi - lo), 1.6))} />
        )))}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <text key={f} x={gx(f * PI)} y={H - B + 16} textAnchor="middle" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">
            {['0', 'π/4', 'π/2', '3π/4', 'π'][f * 4]}</text>
        ))}
        {[0, 0.5, 1].map((f) => (
          <text key={f} x={L - 6} y={by((f * PI) / 2) + 4} textAnchor="end" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">
            {['0', 'π/4', 'π/2'][f * 2]}</text>
        ))}
        <text x={W - R} y={H - 4} textAnchor="end" fontSize={11} fill="var(--text-2)">γ, cost angle →</text>
        <text x={12} y={T + 2} fontSize={11} fill="var(--text-2)" transform={`rotate(-90 12 ${T + 2})`} textAnchor="end">β, mixer →</text>
        <polyline points={pathPts} fill="none" stroke="var(--text)" strokeWidth={1.5} strokeOpacity={0.9} />
        {lab.path.slice(0, -1).map(([g, b], i) => <circle key={i} cx={gx(g)} cy={by(b)} r={i === 0 ? 4 : 2.5} fill={i === 0 ? 'var(--panel)' : 'var(--text)'} stroke="var(--text)" strokeWidth={1.2} />)}
        <circle cx={gx(end[0])} cy={by(end[1])} r={6} fill="var(--text)" stroke="var(--panel)" strokeWidth={2}><title>{`optimizer: γ ${end[0].toFixed(3)}, β ${end[1].toFixed(3)}`}</title></circle>
        {mine && (
          <g pointerEvents="none">
            <rect x={gx(mine[0]) - 6} y={by(mine[1]) - 6} width={12} height={12} transform={`rotate(45 ${gx(mine[0])} ${by(mine[1])})`}
              fill="none" stroke="var(--text)" strokeWidth={2} />
          </g>
        )}
      </svg>
      <div className="row wrap legend" style={{ gap: 14 }}>
        <span className="sub"><svg width={12} height={12} aria-hidden><circle cx={6} cy={6} r={4} fill="var(--panel)" stroke="var(--text)" strokeWidth={1.2} /></svg> grid's best guess</span>
        <span className="sub"><svg width={12} height={12} aria-hidden><circle cx={6} cy={6} r={5} fill="var(--text)" /></svg> where the optimizer ended</span>
        {mine && <span className="sub"><svg width={12} height={12} aria-hidden><rect x={2} y={2} width={8} height={8} transform="rotate(45 6 6)" fill="none" stroke="var(--text)" strokeWidth={1.6} /></svg> your angles</span>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- panel

export function QaoaLabPanel({ onOpen }: { onOpen?: (spec: CircuitSpec) => void }) {
  const [preset, setPreset] = useState('party')
  const [graph, setGraph] = useState<Graph>(PRESETS[0].graph)
  const [sel, setSel] = useState<number | null>(null)
  const [lab, setLab] = useState<QaoaLab | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<number | 'mine'>(1)
  const [mine, setMine] = useState<[number, number] | null>(null)
  const [peek, setPeek] = useState<number | null>(null)
  const names = NAMES.slice(0, graph.n)

  useEffect(() => {
    if (!graph.edges.length) { setLab(null); setError('Click two guests to add a feud.'); return }
    const ctl = new AbortController()
    setBusy(true)
    const t = setTimeout(() => {
      api.qaoaLab({ n: graph.n, edges: graph.edges, labels: NAMES.slice(0, graph.n) }, ctl.signal)
        .then((r) => { setLab(r); setError(null); setBusy(false) })
        .catch((e: Error) => { if (!ctl.signal.aborted) { setError(e.message); setBusy(false) } })
    }, 350)
    return () => { clearTimeout(t); ctl.abort() }
  }, [graph])

  const fresh = !!lab && signature(lab.n, lab.edges) === signature(graph.n, graph.edges)
  const cuts = useMemo(() => cutsOf(graph.n, graph.edges), [graph])
  const minePick = useMemo(() => {
    if (!mine || !lab || !fresh) return null
    const probs = depthOne(graph.n, cuts, mine[0], mine[1])
    let exp = 0, best = 0
    probs.forEach((p, i) => { exp += p * cuts[i]; if (cuts[i] === lab.max_cut) best += p })
    return { top: fold(graph.n, probs, cuts, lab.max_cut), ratio: exp / lab.max_cut, p_best: best }
  }, [mine, lab, fresh, cuts, graph.n])

  const depth = lab && fresh && mode !== 'mine' ? lab.depths[mode - 1] : null
  const top = mode === 'mine' ? minePick?.top ?? [] : depth?.top ?? []
  const shown = top.length ? top[peek ?? 0] ?? top[0] : null

  const edit = (g: Graph) => { setPreset('custom'); setGraph(g); setMine(null); if (mode === 'mine') setMode(1) }
  const onNode = (i: number) => {
    if (sel === null) return setSel(i)
    if (sel === i) return setSel(null)
    const k = key(sel, i)
    const has = graph.edges.some(([a, b]) => key(a, b) === k)
    const edges = has ? graph.edges.filter(([a, b]) => key(a, b) !== k) : [...graph.edges, [Math.min(sel, i), Math.max(sel, i)] as Edge]
    setSel(null)
    edit({ ...graph, edges })
  }
  const resize = (n: number) => {
    if (n < MIN || n > MAX) return
    setSel(null)
    edit({ n, edges: graph.edges.filter(([a, b]) => a < n && b < n) })
  }
  const pick = (g: number, b: number) => { setMine([g, b]); setMode('mine'); setPeek(null) }
  const openSpec = mode === 'mine' && mine ? specFor(graph.n, graph.edges, mine[0], mine[1], names) : depth?.spec
  const optimizerRatio = lab && fresh ? lab.depths[0].ratio : null

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Split the party</h2>
        <span className="sub">QAOA seats feuding guests at two tables · Max-Cut</span>
        <span className="spacer" />
        {onOpen && openSpec && <button className="btn small" onClick={() => onOpen(openSpec)}>Open the circuit in the editor</button>}
      </div>
      <div className="row wrap" style={{ gap: 6, marginBottom: 12 }}>
        <div className="seg">
          {PRESETS.map((p) => (
            <button key={p.id} className={preset === p.id ? 'on' : ''}
              onClick={() => { setPreset(p.id); setGraph(p.graph); setSel(null); setMine(null); setMode(1); setPeek(null) }}>{p.label}</button>
          ))}
        </div>
        <span className="spacer" />
        <button className="chip-btn" onClick={() => resize(graph.n - 1)} disabled={graph.n <= MIN} aria-label="Remove a guest">− guest</button>
        <button className="chip-btn" onClick={() => resize(graph.n + 1)} disabled={graph.n >= MAX} aria-label="Add a guest">+ guest</button>
        <button className="chip-btn" onClick={() => edit({ n: graph.n, edges: [] })} disabled={!graph.edges.length}>Clear feuds</button>
      </div>

      <div className={`qaoa-grid ${busy ? 'busy' : ''}`}>
        <div>
          <Seating graph={graph} names={names} split={shown} sel={sel} onNode={onNode} />
          <div className="row wrap legend" style={{ gap: 14, justifyContent: 'center' }}>
            <span className="sub"><svg width={12} height={12} aria-hidden><circle cx={6} cy={6} r={5} fill={TEAM[0]} /></svg> {TABLE[0]}</span>
            <span className="sub"><svg width={12} height={12} aria-hidden><rect x={1} y={1} width={10} height={10} rx={2.5} fill={TEAM[1]} /></svg> {TABLE[1]}</span>
            <span className="sub"><svg width={18} height={10} aria-hidden><line x1={1} x2={17} y1={5} y2={5} stroke="var(--fail)" strokeWidth={2} strokeDasharray="4 3" /></svg> feud at one table</span>
          </div>
          <div className="sub" style={{ textAlign: 'center', marginTop: 4 }}>{sel !== null ? `Now click someone ${names[sel]} feuds with (or ${names[sel]} again to cancel).` : 'Click two guests to add or remove a feud.'}</div>
        </div>
        {lab && fresh && <Landscape lab={lab} mine={mine} onPick={pick} />}
      </div>

      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {lab && fresh && (
        <div className={busy ? 'busy' : ''}>
          <div className="row wrap" style={{ gap: 8, marginTop: 14 }}>
            <span className="label">Seatings QAOA reads with</span>
            <div className="seg">
              {lab.depths.map((d) => <button key={d.p} className={mode === d.p ? 'on' : ''} onClick={() => { setMode(d.p); setPeek(null) }}>{d.p} layer{d.p > 1 ? 's' : ''}</button>)}
              <button className={mode === 'mine' ? 'on' : ''} disabled={!mine} onClick={() => { setMode('mine'); setPeek(null) }}
                title={mine ? 'one layer at the angles you clicked' : 'click the landscape to pick your own angles'}>your angles</button>
            </div>
            {busy && <span className="sub">optimizing…</span>}
          </div>
          <div className="qaoa-splits" onMouseLeave={() => setPeek(null)}>
            {top.slice(0, 6).map((s, i) => {
              const a = names.filter((_, k) => s.teams[k] === 0).join(' '), b = names.filter((_, k) => s.teams[k] === 1).join(' ')
              return (
                <button key={s.teams.join('')} className={`qaoa-split ${(peek ?? 0) === i ? 'on' : ''}`} onMouseEnter={() => setPeek(i)} onFocus={() => setPeek(i)}
                  onClick={() => setPeek(i)} title={`${TABLE[0]}: ${a}; ${TABLE[1]}: ${b}`}>
                  <span className="names mono">{a} <span className="muted">|</span> {b}</span>
                  <span className="track"><span style={{ width: `${Math.max(0.5, s.prob * 100)}%` }} className={s.optimal ? 'best' : ''} /></span>
                  <span className={`cut mono ${s.optimal ? 'best' : ''}`}>{s.optimal ? '✓ ' : ''}{s.cut}/{lab.edges.length}</span>
                  <span className="p mono">{pct(s.prob, 1)}</span>
                </button>
              )
            })}
          </div>
          <div className="row wrap legend" style={{ gap: 14 }}>
            <span className="sub">each row: who sits at {TABLE[0]} | {TABLE[1]}, feuds defused, chance a run reads it</span>
            <span className="sub" style={{ color: 'var(--pass)' }}>✓ a best seating</span>
          </div>
          <div className="tiles">
            <div className="tile"><div className="k">Best seating, all {lab.splits} checked</div><div className="v">{lab.max_cut} / {lab.edges.length}</div>
              <div className="s">feuds defused · {lab.optimal_count === 1 ? 'one way' : `${lab.optimal_count} ways`}</div></div>
            <div className="tile"><div className="k">QAOA expects</div>
              <div className="v">{pct(mode === 'mine' ? minePick?.ratio ?? 0 : depth?.ratio ?? 0, 0)}</div>
              <div className="s">of the best · random seating {pct(lab.random_ratio, 0)}</div></div>
            <div className="tile"><div className="k">A run reads a best seating</div>
              <div className={`v ${((mode === 'mine' ? minePick?.p_best : depth?.p_best) ?? 0) > 0.5 ? 'good' : ''}`}>{pct(mode === 'mine' ? minePick?.p_best ?? 0 : depth?.p_best ?? 0, 0)}</div>
              <div className="s">{mode !== 'mine' && depth?.p_best_noisy != null ? `${pct(depth.p_best_noisy, 0)} with ${lab.noise_label.toLowerCase()} noise` : 'perfect qubits'}</div></div>
            <div className="tile"><div className="k">Circuit</div>
              <div className="v">{mode === 'mine' ? 2 * lab.edges.length : depth?.cx} CNOTs</div>
              <div className="s">{mode === 'mine' ? '1 layer, your 2 angles' : `${depth?.p} layer${(depth?.p ?? 1) > 1 ? 's' : ''}, ${depth?.evals} tries to tune ${2 * (depth?.p ?? 1)} angles`}</div></div>
          </div>
          {mode === 'mine' && minePick && optimizerRatio !== null && (
            <p className="lead" style={{ margin: '12px 0 0' }}>
              Your angles expect {pct(minePick.ratio, 1)} of the best cut; the optimizer's one-layer angles expect {pct(optimizerRatio, 1)}
              {minePick.ratio >= optimizerRatio - 5e-4 ? '. You matched it.' : ` (you are at ${pct(minePick.ratio / optimizerRatio, 0)} of it). Look for the brightest spot.`}
            </p>
          )}
          <p className="lead" style={{ margin: '12px 0 0' }}>{lab.summary}</p>
        </div>
      )}
    </div>
  )
}
