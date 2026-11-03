import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import type { ObsChart, ObsReference, Observatory } from '../types'
import { MlVerifierView } from './MlVerifier'

type Pt = [number, number | null]
type Line = { id: string; label: string; points: Pt[]; color: string; dash?: string; markers?: boolean; labelAt?: 'start' | 'end' }
type Band = { low: Pt[]; high: Pt[]; color: string }

const SUP: Record<string, string> = { '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' }
const pow10 = (k: number) => (k === 0 ? '1' : k === 1 ? '10' : `10${String(k).split('').map((c) => SUP[c]).join('')}`)
const UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB']
export const bytes = (v: number) => {
  const k = Math.min(UNITS.length - 1, Math.max(0, Math.floor(Math.log10(v) / 3)))
  const x = v / 10 ** (3 * k)
  return `${Number(x.toPrecision(2))} ${UNITS[k]}`
}
const num = (v: number) => (Math.abs(v) >= 1e5 || (v !== 0 && Math.abs(v) < 1e-2) ? v.toExponential(1).replace('e+', 'e') : v >= 100 ? v.toFixed(0) : v.toPrecision(3))
const pct = (v: number) => `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`

function niceLogTicks(lo: number, hi: number, maxTicks = 6, fixed?: number): number[] {
  const a = Math.floor(Math.log10(lo)), b = Math.ceil(Math.log10(hi))
  const step = fixed ?? Math.max(1, Math.ceil((b - a) / maxTicks))
  const out: number[] = []
  for (let k = Math.ceil(a / step) * step; k <= b; k += step) out.push(k)
  return out
}

function niceLinTicks(lo: number, hi: number, maxTicks = 5): number[] {
  const raw = (hi - lo) / maxTicks
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Number(v.toPrecision(10)))
  return out
}

/** One line chart: log or linear axes, gaps where a value does not exist, crosshair readout, direct labels, a table. */
export function LineChart({ lines, band, refs = [], xLog, yLog, yLogStep, xLabel, yLabel, xDomain, yDomain, fmtX = num, fmtY = num, aria, height = 290, labels = true, table = true }: {
  lines: Line[]; band?: Band; refs?: ObsReference[]; xLog?: boolean; yLog?: boolean; yLogStep?: number; xLabel: string; yLabel: string
  xDomain?: [number, number]; yDomain?: [number, number]; fmtX?: (v: number) => string; fmtY?: (v: number) => string
  aria: string; height?: number; labels?: boolean; table?: boolean
}) {
  const box = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(640)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const H = height, L = W < 480 ? 46 : 58, R = 18, T = 22, B = 40
  const all = lines.flatMap((l) => l.points).concat(band ? [...band.low, ...band.high] : [])
  const xs = [...new Set(lines.flatMap((l) => l.points.map((p) => p[0])))].sort((a, b) => a - b)
  const ys = all.map((p) => p[1]).filter((v): v is number => v !== null && (!yLog || v > 0))
  const [x0, x1] = xDomain ?? [xs[0], xs[xs.length - 1]]
  let [y0, y1] = yDomain ?? [Math.min(...ys), Math.max(...ys)]
  if (yLog && !yDomain) { y0 = 10 ** Math.floor(Math.log10(y0)); y1 = 10 ** Math.ceil(Math.log10(y1)) }
  const tx = (v: number) => (xLog ? Math.log10(v) : v)
  const ty = (v: number) => (yLog ? Math.log10(Math.max(v, 1e-300)) : v)
  const x = (v: number) => L + ((tx(v) - tx(x0)) / (tx(x1) - tx(x0))) * (W - L - R)
  const y = (v: number) => T + (1 - (ty(Math.min(Math.max(v, y0), y1)) - ty(y0)) / (ty(y1) - ty(y0))) * (H - T - B)
  const path = (pts: Pt[]) => {
    let d = '', pen = false
    for (const [px, py] of pts) {
      if (py === null || (yLog && py <= 0)) { pen = false; continue }
      d += `${pen ? 'L' : 'M'}${x(px).toFixed(1)} ${y(py).toFixed(1)}`
      pen = true
    }
    return d
  }
  const yTicks = yLog ? niceLogTicks(y0, y1, 6, yLogStep).map((k) => 10 ** k) : niceLinTicks(y0, y1)
  const xTicks = xLog ? [1, 2, 5].flatMap((m) => niceLogTicks(x0, x1, 12).map((k) => m * 10 ** k)).filter((v) => v >= x0 && v <= x1).sort((a, b) => a - b)
    : niceLinTicks(x0, x1, 6)
  const [hover, setHover] = useState<number | null>(null)
  const hx = hover !== null ? xs[hover] : null
  type End = { id: string; label: string; x: number; y: number; anchor: 'start' | 'end' }
  const ends: End[] = labels ? lines.flatMap((l): End[] => {
    const ok = (p: Pt) => p[1] !== null && (!yLog || (p[1] as number) > 0)
    const start = l.labelAt === 'start'
    const at = start ? l.points.find(ok) : [...l.points].reverse().find(ok)
    return at ? [{ id: l.id, label: l.label, x: x(at[0]) + (start ? 2 : 0), y: y(at[1] as number) - 9, anchor: start ? 'start' : 'end' }] : []
  }).sort((a, b) => a.y - b.y) : []
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14
  const bandPath = band ? `${path(band.low)}${band.high.slice().reverse().map(([px, py]) => `L${x(px).toFixed(1)} ${y(py as number).toFixed(1)}`).join('')}Z` : ''
  return (
    <div className="obs-chart" ref={box}>
      <div className="sub mono qaoa-readout" aria-live="polite">
        {hx !== null ? `${xLabel.split(',')[0]} ${fmtX(hx)} · ` + lines.map((l) => {
          const v = l.points.find((p) => p[0] === hx)?.[1]
          return `${l.label}: ${v === null || v === undefined ? '—' : fmtY(v)}`
        }).join(' · ') : yLabel}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ display: 'block', maxWidth: '100%', cursor: 'crosshair', touchAction: 'pan-y' }} role="img" aria-label={aria}
        onMouseLeave={() => setHover(null)}
        onPointerMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect()
          const px = ((e.clientX - box.left) / box.width) * W
          let best = 0
          xs.forEach((v, i) => { if (Math.abs(x(v) - px) < Math.abs(x(xs[best]) - px)) best = i })
          setHover(best)
        }}>
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--line)" />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">
              {yLog ? (fmtY === bytes ? bytes(v) : pow10(Math.round(Math.log10(v)))) : fmtY(v)}
            </text>
          </g>
        ))}
        {xTicks.map((v) => (
          <text key={v} x={x(v)} y={H - B + 16} textAnchor="middle" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{fmtX(v)}</text>
        ))}
        <text x={W - R} y={H - 4} textAnchor="end" fontSize={11} fill="var(--text-2)">{xLabel} →</text>
        {refs.map((r) => r.axis === 'x' ? (
          <g key={r.label}>
            <line x1={x(r.value)} x2={x(r.value)} y1={T} y2={H - B} stroke="var(--text-2)" strokeDasharray="2 4" />
            {x(r.value) > W - R - 90
              ? <text x={x(r.value) - 5} y={T + 10} textAnchor="end" fontSize={11} fill="var(--text-2)">{r.label}</text>
              : <text x={x(r.value) + 5} y={T + 10} fontSize={11} fill="var(--text-2)">{r.label}</text>}
          </g>
        ) : (
          <g key={r.label}>
            <line x1={L} x2={W - R} y1={y(r.value)} y2={y(r.value)} stroke="var(--text-2)" strokeDasharray="2 4" />
            <text x={L + 6} y={y(r.value) - 5} fontSize={11} fill="var(--text-2)">{r.label}</text>
          </g>
        ))}
        {band && <path d={bandPath} fill={band.color} fillOpacity={0.16} stroke="none" />}
        {hx !== null && <line x1={x(hx)} x2={x(hx)} y1={T} y2={H - B} stroke="var(--line-2)" />}
        {lines.map((l) => (
          <g key={l.id}>
            <path d={path(l.points)} fill="none" stroke={l.color} strokeWidth={2} strokeDasharray={l.dash} strokeLinejoin="round" />
            {l.markers && l.points.map(([px, py]) => py === null ? null : (
              <circle key={px} cx={x(px)} cy={y(py)} r={4} fill={l.color} stroke="var(--panel)" strokeWidth={2} />
            ))}
          </g>
        ))}
        {hx !== null && lines.map((l) => {
          const v = l.points.find((p) => p[0] === hx)?.[1]
          return v === null || v === undefined || (yLog && v <= 0) ? null
            : <circle key={l.id} cx={x(hx)} cy={y(v)} r={4.5} fill={l.color} stroke="var(--panel)" strokeWidth={2} />
        })}
        {ends.map((e) => (
          <text key={e.id} x={Math.min(e.x, W - R)} y={Math.max(e.y, 12)} textAnchor={e.anchor} fontSize={11} fill="var(--text-2)">{e.label}</text>
        ))}
      </svg>
      <div className="row wrap legend" style={{ gap: 14 }}>
        {lines.map((l) => (
          <span key={l.id} className="sub">
            <svg width={22} height={10} aria-hidden><line x1={1} x2={21} y1={5} y2={5} stroke={l.color} strokeWidth={2} strokeDasharray={l.dash} /></svg>
            {l.label}
          </span>
        ))}
        {band && <span className="sub"><svg width={14} height={10} aria-hidden><rect width={14} height={10} rx={2} fill={band.color} fillOpacity={0.3} /></svg>range across runs</span>}
      </div>
      {table && (
        <details className="obs-table">
          <summary className="sub">Show the numbers</summary>
          <div className="obs-table-scroll">
            <table>
              <thead><tr><th>{xLabel}</th>{lines.map((l) => <th key={l.id}>{l.label}</th>)}</tr></thead>
              <tbody>
                {xs.map((xv) => (
                  <tr key={xv}><td>{fmtX(xv)}</td>{lines.map((l) => {
                    const v = l.points.find((p) => p[0] === xv)?.[1]
                    return <td key={l.id}>{v === null || v === undefined ? '—' : fmtY(v)}</td>
                  })}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}

const BLUE = 'var(--primary)', ORANGE = 'var(--predicted)', NEUTRAL = 'var(--text-2)', GOLD = 'var(--gold)'

function Finding({ chart }: { chart: ObsChart }) {
  return (
    <div className="obs-head">
      <h3>{chart.title}</h3>
      <p>{chart.finding}</p>
    </div>
  )
}

function Method({ text }: { text: string }) {
  return <p className="sub obs-method">How it is computed: {text}</p>
}

function SatelliteView({ c }: { c: ObsChart }) {
  const [sat, fiber] = c.series
  return (
    <>
      <Finding chart={c} />
      <LineChart xLog yLog xLabel={c.x_label} yLabel={c.y_label} refs={c.references} fmtX={(v) => v.toLocaleString()}
        aria="Secret key rate against distance on log scales: direct fiber falls off a cliff after a few hundred kilometres while the satellite declines slowly up to 2,400 km"
        lines={[{ id: sat.id, label: sat.label, points: sat.points, color: BLUE, labelAt: 'start' }, { id: fiber.id, label: fiber.label, points: fiber.points, color: ORANGE, labelAt: 'start' }]} />
      <Method text={c.method} />
    </>
  )
}

function WalkView({ c, frames }: { c: ObsChart; frames: Observatory['walk_frames'] }) {
  const first = frames.steps.findIndex((t) => t >= 10)
  const [i, setI] = useState(frames.steps.length - 1)
  const [playing, setPlaying] = useState(false)
  const timer = useRef<number | null>(null)
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current) }, [])
  const play = () => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setI(frames.steps.length - 1); return }
    if (timer.current) window.clearInterval(timer.current)
    setI(first)
    setPlaying(true)
    timer.current = window.setInterval(() => {
      setI((k) => {
        if (k >= frames.steps.length - 1) { if (timer.current) window.clearInterval(timer.current); setPlaying(false); return k }
        return k + 1
      })
    }, 90)
  }
  const yMax = useMemo(() => Math.max(...frames.quantum.slice(first).flat(), ...frames.classical.slice(first).flat()), [frames, first])
  const t = frames.steps[i]
  const toPts = (row: number[]): Pt[] => frames.positions.map((p, k) => [p, row[k]])
  const [q, cl] = c.series
  return (
    <>
      <Finding chart={c} />
      <div className="row wrap" style={{ gap: 10, margin: '4px 0 2px' }}>
        <button className="btn small" onClick={play} disabled={playing}>{playing ? 'Walking…' : 'Play the walk'}</button>
        <span className="label">Step</span>
        <input type="range" min={first} max={frames.steps.length - 1} value={i} onChange={(e) => setI(Number(e.target.value))} aria-label="Walk step" style={{ flex: 1, minWidth: 140 }} />
        <span className="mono sub" style={{ minWidth: 60 }}>t = {t}</span>
      </div>
      <div className="obs-pair">
        <LineChart xLabel="position, sites" yLabel={`where the walker is after ${t} steps (probability)`} xDomain={[frames.positions[0], frames.positions[frames.positions.length - 1]]}
          yDomain={[0, Math.ceil(yMax * 20) / 20]} fmtY={(v) => v.toFixed(2)} fmtX={(v) => String(v)} labels={false} table={false} height={260}
          aria={`Probability of each position after ${t} steps: the quantum walker has two peaks near the edges, the classical walker one bell curve in the middle`}
          lines={[{ id: 'q', label: 'Quantum walk', points: toPts(frames.quantum[i]), color: BLUE },
            { id: 'c', label: 'Classical random walk', points: toPts(frames.classical[i]), color: ORANGE }]} />
        <LineChart xLabel={c.x_label} yLabel={c.y_label} fmtX={(v) => String(v)} fmtY={(v) => v.toFixed(1)} height={260}
          refs={[{ value: t, label: `t = ${t}`, axis: 'x' }]}
          aria="Spread against steps: the quantum walk grows in a straight line, the classical walk as a square root"
          lines={[{ id: q.id, label: q.label, points: q.points, color: BLUE }, { id: cl.id, label: cl.label, points: cl.points, color: ORANGE }]} />
      </div>
      <Method text={c.method} />
    </>
  )
}

function GroverView({ cases }: { cases: Observatory['grover'] }) {
  const [n, setN] = useState(cases[cases.length - 1].qubits)
  const g = cases.find((x) => x.qubits === n) ?? cases[0]
  const c = g.chart
  const [ideal, noisy, classical] = c.series
  return (
    <>
      <div className="row wrap" style={{ gap: 6, marginBottom: 6 }}>
        <span className="label">Search space</span>
        {cases.map((x) => (
          <button key={x.qubits} className={`chip-btn${x.qubits === n ? ' on' : ''}`} aria-pressed={x.qubits === n} onClick={() => setN(x.qubits)}>
            {x.qubits} qubits · {2 ** x.qubits} items
          </button>
        ))}
      </div>
      <Finding chart={c} />
      <LineChart xLabel={c.x_label} yLabel={c.y_label} yDomain={[0, 1]} fmtY={pct} fmtX={(v) => String(v)}
        aria={`Grover search on ${n} qubits: the ideal curve rises to near 100% and oscillates, today's hardware stays far lower, classical search rises in a straight line`}
        lines={[{ id: ideal.id, label: ideal.label, points: ideal.points, color: NEUTRAL, dash: '6 4' },
          { id: noisy.id, label: noisy.label, points: noisy.points, color: BLUE, markers: true },
          { id: classical.id, label: classical.label, points: classical.points, color: ORANGE }]} labels={false} />
      <Method text={c.method} />
    </>
  )
}

function EntanglementView({ c }: { c: ObsChart }) {
  const [mean, low, high] = c.series
  return (
    <>
      <Finding chart={c} />
      <LineChart xLabel={c.x_label} yLabel={c.y_label} refs={c.references} yDomain={[0, Math.ceil(Math.max(...c.references.map((r) => r.value)) + 0.5)]}
        fmtX={(v) => String(v)} fmtY={(v) => v.toFixed(2)}
        aria="Entanglement between the two halves rises in steps with each layer of random gates and levels off just under Page's limit"
        band={{ low: low.points, high: high.points, color: GOLD }}
        lines={[{ id: mean.id, label: mean.label, points: mean.points, color: GOLD }]} labels={false} />
      <Method text={c.method} />
    </>
  )
}

function WallView({ c }: { c: ObsChart }) {
  const [mem] = c.series
  return (
    <>
      <Finding chart={c} />
      <LineChart yLog yLogStep={3} xLabel={c.x_label} yLabel={c.y_label} refs={c.references} fmtY={bytes} fmtX={(v) => String(v)}
        aria="Memory to store a quantum state against qubits on a log scale: a straight line that passes a laptop at 29 qubits and supercomputer scale at 49"
        lines={[{ id: mem.id, label: mem.label, points: mem.points, color: BLUE }]} labels={false} />
      <Method text={c.method} />
    </>
  )
}

const TABS = [
  { id: 'satellite', label: 'Satellites vs fiber' },
  { id: 'grover', label: 'Grover vs noise' },
  { id: 'walk', label: 'Quantum walk' },
  { id: 'entanglement', label: 'Entanglement growth' },
  { id: 'wall', label: 'The exponential wall' },
  { id: 'ml', label: 'ML verifier' },
] as const

/** Five exact simulations of where quantum technology stands, each with the number that matters spelled out. */
export function ObservatoryPanel() {
  const [data, setData] = useState<Observatory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('satellite')
  useEffect(() => { api.observatory().then(setData).catch((e: Error) => setError(e.message)) }, [])
  return (
    <div className="panel">
      <div className="panel-head"><h2>Simulation observatory</h2><span className="sub">where the technology stands</span></div>
      <div className="obs-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={`chip-btn${tab === t.id ? ' on' : ''}`} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      {error && <div className="notice error">{error}</div>}
      {!data && !error && <div className="sub">Running the simulations…</div>}
      {data && (
        <div role="tabpanel">
          {tab === 'satellite' && <SatelliteView c={data.satellite} />}
          {tab === 'grover' && <GroverView cases={data.grover} />}
          {tab === 'walk' && <WalkView c={data.walk} frames={data.walk_frames} />}
          {tab === 'entanglement' && <EntanglementView c={data.entanglement} />}
          {tab === 'wall' && <WallView c={data.wall} />}
          {tab === 'ml' && <MlVerifierView />}
        </div>
      )}
    </div>
  )
}
