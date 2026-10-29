import { useRef, useSyncExternalStore } from 'react'

type Vec = [number, number, number]
interface View { yaw: number; pitch: number }

const DEFAULT_VIEW: View = { yaw: (25 * Math.PI) / 180, pitch: (20 * Math.PI) / 180 }

/** One camera for every sphere on the page, so turning one turns them all and they stay comparable. */
let view = DEFAULT_VIEW
const listeners = new Set<() => void>()
const viewStore = {
  get: () => view,
  set: (v: View) => { view = v; listeners.forEach((f) => f()) },
  subscribe: (f: () => void) => { listeners.add(f); return () => { listeners.delete(f) } },
}

const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

/** Camera axes: towards the viewer, screen right, screen up. */
function axes({ yaw, pitch }: View): { cam: Vec; right: Vec; up: Vec } {
  const cp = Math.cos(pitch), sp = Math.sin(pitch), cy = Math.cos(yaw), sy = Math.sin(yaw)
  return { cam: [cp * cy, cp * sy, sp], right: [-sy, cy, 0], up: [-sp * cy, -sp * sy, cp] }
}

const RING = 72

/** A great circle split into the half facing the viewer and the half behind the sphere. */
function ring(point: (t: number) => Vec, proj: (p: Vec) => [number, number, number]): { front: string; back: string } {
  let front = '', back = ''
  let prevSide: 'f' | 'b' | null = null
  let prev = proj(point(0))
  for (let k = 1; k <= RING; k++) {
    const cur = proj(point((k / RING) * 2 * Math.PI))
    const side = (prev[2] + cur[2]) / 2 >= 0 ? 'f' : 'b'
    const seg = `${side === prevSide ? '' : `M${prev[0].toFixed(1)} ${prev[1].toFixed(1)}`}L${cur[0].toFixed(1)} ${cur[1].toFixed(1)}`
    if (side === 'f') front += seg
    else back += seg
    prevSide = side
    prev = cur
  }
  return { front, back }
}

/**
 * One qubit's Bloch sphere in 3D. Drag to turn it (all spheres turn together), double-click to reset.
 * A shorter arrow means the qubit is entangled or noisy; ``trail`` draws its path through the circuit.
 */
export function BlochSphere({ vec, entangled, label, size = 104, trail, caption = true }: {
  vec: Vec; entangled: boolean; label: string; size?: number; trail?: Vec[]; caption?: boolean
}) {
  const v = useSyncExternalStore(viewStore.subscribe, viewStore.get)
  const drag = useRef<{ x: number; y: number; start: View } | null>(null)
  const { cam, right, up } = axes(v)
  const C = size / 2, R = size * 0.36
  const proj = (p: Vec): [number, number, number] => [C + R * dot(p, right), C - R * dot(p, up), dot(p, cam)]
  const rings = [
    ring((t) => [Math.cos(t), Math.sin(t), 0], proj),
    ring((t) => [Math.cos(t), 0, Math.sin(t)], proj),
    ring((t) => [0, Math.cos(t), Math.sin(t)], proj),
  ]
  const [x, y, z] = vec
  const len = Math.hypot(x, y, z)
  const tip = proj(vec)
  const ink = entangled ? 'var(--gold)' : 'var(--primary)'
  const axisEnds: [Vec, string][] = [[[1.22, 0, 0], 'x'], [[0, 1.22, 0], 'y'], [[0, 0, 1.2], '|0⟩'], [[0, 0, -1.2], '|1⟩']]
  const pts = (trail ?? []).map(proj)

  return (
    <figure className="bloch" style={{ margin: 0 }}>
      <svg width={size} height={size + 6} role="img" style={{ cursor: drag.current ? 'grabbing' : 'grab', touchAction: 'none' }}
        aria-label={`${label} Bloch vector x ${x.toFixed(2)}, y ${y.toFixed(2)}, z ${z.toFixed(2)}`}
        onPointerDown={(e) => {
          drag.current = { x: e.clientX, y: e.clientY, start: viewStore.get() }
          e.currentTarget.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          const d = drag.current
          if (!d) return
          const lim = (80 * Math.PI) / 180
          viewStore.set({ yaw: d.start.yaw - (e.clientX - d.x) * 0.012,
                          pitch: Math.max(-lim, Math.min(lim, d.start.pitch + (e.clientY - d.y) * 0.012)) })
        }}
        onPointerUp={() => { drag.current = null }}
        onDoubleClick={() => viewStore.set(DEFAULT_VIEW)}>
        <title>Drag to turn every sphere; double-click to reset the view</title>
        <g transform="translate(0 3)">
          <circle cx={C} cy={C} r={R} fill="var(--panel-2)" stroke="var(--line-2)" />
          {rings.map((r, k) => <path key={`b${k}`} d={r.back} fill="none" stroke="var(--line-2)" strokeDasharray="2 3" opacity={0.7} />)}
          {axisEnds.slice(0, 3).map(([p]) => {  // the x, y and z axes, each drawn end to end
            const a = proj(p), b = proj([-p[0], -p[1], -p[2]] as Vec)
            return <line key={String(p)} x1={b[0]} y1={b[1]} x2={a[0]} y2={a[1]} stroke="var(--line-2)" strokeWidth={0.8} />
          })}
          {pts.length > 1 && (
            <g>
              <polyline points={pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')} fill="none"
                stroke={ink} strokeOpacity={0.45} strokeWidth={1.2} strokeLinejoin="round" />
              {pts.slice(0, -1).map((p, k) => <circle key={k} cx={p[0]} cy={p[1]} r={1.9} fill={ink} fillOpacity={0.55} />)}
            </g>
          )}
          {len > 0.02 && <line x1={C} y1={C} x2={tip[0]} y2={tip[1]} stroke={ink} strokeWidth={2.4} strokeLinecap="round"
            opacity={tip[2] < -0.05 ? 0.6 : 1} />}
          <circle cx={len > 0.02 ? tip[0] : C} cy={len > 0.02 ? tip[1] : C} r={tip[2] < -0.05 ? 3.8 : 4.5} fill={ink}
            stroke="var(--panel)" strokeWidth={1.5} />
          {rings.map((r, k) => <path key={`f${k}`} d={r.front} fill="none" stroke="var(--line-2)" strokeWidth={1} />)}
          {axisEnds.map(([p, t]) => {
            const a = proj(p)
            return (
              <text key={t} x={a[0]} y={a[1] + 3.5} textAnchor="middle" fontSize={t.length > 1 ? 9.5 : 9} fill="var(--muted)"
                fontFamily="var(--mono)" opacity={a[2] < -0.3 ? 0.45 : 1}>{t}</text>
            )
          })}
        </g>
      </svg>
      {caption && (
        <figcaption>
          <span className="mono">{label}</span>
          <span className={entangled ? 'gold' : 'muted'}>{entangled ? `entangled · ${len.toFixed(2)}` : len > 0.999 ? 'pure' : len.toFixed(2)}</span>
        </figcaption>
      )}
    </figure>
  )
}
