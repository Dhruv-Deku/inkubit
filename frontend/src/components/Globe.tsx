import { useEffect, useMemo, useRef, useState } from 'react'
import land from 'world-atlas/land-110m.json'
import { api, ApiError } from '../api'
import type { OrbitPlan } from '../types'

type V3 = [number, number, number]
const RAD = Math.PI / 180
const ALT = 500 / 6378.137

/** Natural Earth land (TopoJSON, quantised and delta-encoded arcs) to rings of [lon, lat]. */
function landRings(): [number, number][][] {
  const topo = land as unknown as { transform: { scale: [number, number]; translate: [number, number] }; arcs: [number, number][][]; objects: { land: { geometries: { type: string; arcs: number[][][] | number[][] }[] } } }
  const [sx, sy] = topo.transform.scale, [tx, ty] = topo.transform.translate
  const arcs = topo.arcs.map((arc) => { let x = 0, y = 0; return arc.map(([dx, dy]) => { x += dx; y += dy; return [x * sx + tx, y * sy + ty] as [number, number] }) })
  const ring = (ids: number[]) => ids.flatMap((i, k) => { const a = i >= 0 ? arcs[i] : arcs[~i].slice().reverse(); return k ? a.slice(1) : a })
  const out: [number, number][][] = []
  for (const g of topo.objects.land.geometries) {
    const polys = (g.type === 'MultiPolygon' ? g.arcs : [g.arcs]) as number[][][]
    for (const poly of polys) for (const r of poly) out.push(ring(r))
  }
  return out
}

const toV = (lat: number, lon: number, r = 1): V3 => [r * Math.cos(lat * RAD) * Math.cos(lon * RAD), r * Math.cos(lat * RAD) * Math.sin(lon * RAD), r * Math.sin(lat * RAD)]

/** View rotation: the point (lat0, lon0) faces the viewer. Returns screen-space [x right, y up, z towards viewer]. */
function viewer(lat0: number, lon0: number) {
  const cl = Math.cos(lat0 * RAD), sl = Math.sin(lat0 * RAD), co = Math.cos(lon0 * RAD), so = Math.sin(lon0 * RAD)
  return (v: V3): V3 => {
    const x1 = v[0] * co + v[1] * so, y1 = -v[0] * so + v[1] * co, z1 = v[2]
    return [y1, z1 * cl - x1 * sl, x1 * cl + z1 * sl]
  }
}

function draw(ctx: CanvasRenderingContext2D, S: number, plan: OrbitPlan, rings: [number, number][][], t: number, lat0: number, lon0: number) {
  const R = S * 0.44, cx = S / 2, cy = S / 2
  const view = viewer(lat0, lon0)
  const px = (p: V3) => [cx + p[0] * R, cy - p[1] * R] as const
  ctx.clearRect(0, 0, S, S)
  // ocean
  ctx.fillStyle = '#16181d'
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, 2 * Math.PI); ctx.fill()
  // land, with hidden points pushed to the limb so fills close cleanly
  ctx.fillStyle = '#2e3138'
  ctx.strokeStyle = '#4a4e57'
  ctx.lineWidth = 0.8
  for (const ring of rings) {
    let any = false
    ctx.beginPath()
    ring.forEach(([lon, lat], i) => {
      let p = view(toV(lat, lon))
      if (p[2] >= 0) any = true
      else { const n = Math.hypot(p[0], p[1]) || 1; p = [p[0] / n, p[1] / n, 0] }
      const [x, y] = px(p)
      if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y)
    })
    if (any) { ctx.closePath(); ctx.fill(); ctx.stroke() }
  }
  // graticule
  ctx.strokeStyle = 'rgba(169,171,178,0.13)'
  ctx.lineWidth = 0.7
  for (let lat = -60; lat <= 60; lat += 30) { ctx.beginPath(); let pen = false; for (let lon = -180; lon <= 180; lon += 3) { const p = view(toV(lat, lon)); if (p[2] < 0) { pen = false; continue } const [x, y] = px(p); if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y); pen = true } ctx.stroke() }
  for (let lon = -180; lon < 180; lon += 30) { ctx.beginPath(); let pen = false; for (let lat = -90; lat <= 90; lat += 3) { const p = view(toV(lat, lon)); if (p[2] < 0) { pen = false; continue } const [x, y] = px(p); if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y); pen = true } ctx.stroke() }
  // night side from the real sub-solar point, with a soft twilight band
  const sun = plan.sun[Math.min(plan.sun.length - 1, Math.floor(t / 10))]
  const sv = view(toV(sun[0], sun[1]))
  const step = Math.max(2, Math.round(S / 220))
  for (let y = -R; y < R; y += step) {
    for (let x = -R; x < R; x += step) {
      const r2 = x * x + y * y
      if (r2 > R * R) continue
      const z = Math.sqrt(R * R - r2)
      const d = (x * sv[0] + -y * sv[1] + z * sv[2]) / R
      if (d > 0.1) continue
      const a = d < -0.1 ? 0.55 : 0.55 * (0.1 - d) / 0.2
      ctx.fillStyle = `rgba(4,5,8,${a.toFixed(3)})`
      ctx.fillRect(cx + x, cy + y, step, step)
    }
  }
  ctx.strokeStyle = '#3a3d45'
  ctx.lineWidth = 1
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, 2 * Math.PI); ctx.stroke()
  // orbit track 50 minutes either side, at altitude; hidden behind the Earth when in its shadow from the viewer
  const k0 = Math.max(0, t - 100), k1 = Math.min(plan.track.length - 1, t + 100)
  const vis = (p: V3) => p[2] > 0 || Math.hypot(p[0], p[1]) > 1
  ctx.lineWidth = 1.4
  let prev: V3 | null = null
  for (let k = k0; k <= k1; k++) {
    const [la, lo] = plan.track[k]
    const p = view(toV(la, lo, 1 + ALT))
    if (prev && vis(p) && vis(prev)) {
      ctx.strokeStyle = k <= t ? 'rgba(169,171,178,0.35)' : 'rgba(57,135,229,0.75)'
      ctx.beginPath(); ctx.moveTo(...px(prev)); ctx.lineTo(...px(p)); ctx.stroke()
    }
    prev = p
  }
  // stations and beams
  const sat = view(toV(plan.track[t][0], plan.track[t][1], 1 + ALT))
  const cities = [{ c: plan.city_a, el: plan.el_a[t], night: plan.night_a[t] }, { c: plan.city_b, el: plan.el_b[t], night: plan.night_b[t] }]
  const both = cities.every((s) => s.el >= 15 && s.night)
  for (const s of cities) {
    const p = view(toV(s.c.lat, s.c.lon))
    if (s.el >= 15 && s.night) {
      ctx.strokeStyle = both ? '#d9a441' : '#3987e5'
      ctx.lineWidth = 2
      ctx.beginPath(); ctx.moveTo(...px(p)); ctx.lineTo(...px(sat)); ctx.stroke()
    }
    if (p[2] < 0) continue
    const [x, y] = px(p)
    ctx.fillStyle = '#ecebe8'; ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.fill()
    ctx.font = `${Math.round(S / 46)}px Inter, system-ui, sans-serif`
    ctx.fillStyle = '#ecebe8'; ctx.fillText(s.c.name, x + 7, y - 6)
  }
  if (vis(sat)) {
    const [x, y] = px(sat)
    ctx.fillStyle = '#1b1c20'; ctx.strokeStyle = '#ecebe8'; ctx.lineWidth = 1.6
    ctx.fillRect(x - 9, y - 2, 6, 4); ctx.fillRect(x + 3, y - 2, 6, 4)
    ctx.strokeRect(x - 9, y - 2, 6, 4); ctx.strokeRect(x + 3, y - 2, 6, 4)
    ctx.beginPath(); ctx.arc(x, y, 3.5, 0, 2 * Math.PI); ctx.fillStyle = '#ecebe8'; ctx.fill()
  }
}

const KIND: Record<string, string> = { both: 'both cities at once', a: '', b: '' }
const clock = (iso: string) => iso.slice(11, 16) + ' UTC'

/** A Micius-like satellite over a real day: the globe, every pass over two cities, and the key each pass gives. */
export function GlobePanel() {
  const [cities, setCities] = useState<{ id: string; name: string }[]>([])
  const [pairs, setPairs] = useState<{ a: string; b: string; label: string }[]>([])
  const [ab, setAb] = useState<[string, string]>(['delingha', 'lijiang'])
  const [night, setNight] = useState(true)
  const [plan, setPlan] = useState<OrbitPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [rot, setRot] = useState<[number, number]>([30, 100])
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const box = useRef<HTMLDivElement | null>(null)
  const [S, setS] = useState(520)
  const rings = useMemo(landRings, [])
  useEffect(() => { api.orbitCities().then((r) => { setCities(r.cities); setPairs(r.pairs) }).catch(() => {}) }, [])
  useEffect(() => {
    let live = true
    api.orbits(ab[0], ab[1], night).then((p) => {
      if (!live) return
      setPlan(p); setError(null)
      const first = p.passes.find((x) => x.kind === 'both') ?? p.passes[0]
      setT(first ? Math.max(0, Math.round((Date.parse(first.start_utc) - Date.parse(p.start_utc)) / 1000 / p.step_s) - 6) : 0)
      setRot([(p.city_a.lat + p.city_b.lat) / 2, (p.city_a.lon + p.city_b.lon) / 2 + (Math.abs(p.city_a.lon - p.city_b.lon) > 180 ? 180 : 0)])
    }).catch((e) => { if (live) setError(e instanceof ApiError ? e.message : 'The planner failed.') })
    return () => { live = false }
  }, [ab, night])
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setS(Math.max(280, Math.min(620, Math.round(e.contentRect.width)))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  useEffect(() => {
    const c = canvas.current
    if (!c || !plan) return
    const dpr = window.devicePixelRatio || 1
    c.width = S * dpr; c.height = S * dpr
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    draw(ctx, S, plan, rings, t, rot[0], rot[1])
  }, [plan, t, rot, S, rings])
  useEffect(() => {
    if (!playing || !plan) return
    const id = window.setInterval(() => setT((k) => (k + 1) % plan.track.length), 40)
    return () => window.clearInterval(id)
  }, [playing, plan])
  const drag = useRef<{ x: number; y: number; r: [number, number] } | null>(null)
  const now = plan ? new Date(Date.parse(plan.start_utc) + t * plan.step_s * 1000).toISOString() : ''
  const jump = (iso: string) => plan && setT(Math.max(0, Math.round((Date.parse(iso) - Date.parse(plan.start_utc)) / 1000 / plan.step_s) - 4))
  const name = (k: string) => (k === 'a' ? plan?.city_a.name : k === 'b' ? plan?.city_b.name : KIND[k])
  return (
    <div className="panel globe">
      <div className="panel-head">
        <h2>Satellite planner</h2>
        <span className="sub">a Micius-like satellite over a real day: every pass over two cities, by night, and the key it gives</span>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        {pairs.map((p) => (
          <button key={p.a + p.b} className={`chip-btn${ab[0] === p.a && ab[1] === p.b ? ' on' : ''}`} onClick={() => setAb([p.a, p.b])}>{p.label}</button>
        ))}
      </div>
      <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
        <select value={ab[0]} onChange={(e) => setAb([e.target.value, ab[1]])} aria-label="City A">{cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select value={ab[1]} onChange={(e) => setAb([ab[0], e.target.value])} aria-label="City B">{cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <label className="row sub" style={{ gap: 6 }}><input type="checkbox" checked={night} onChange={(e) => setNight(e.target.checked)} /> night only (as Micius ran)</label>
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {plan && (
        <>
          <p className="obs-head" style={{ margin: '12px 0 4px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>{plan.finding}</p>
          <div className="globe-grid">
            <div ref={box}>
              <canvas ref={canvas} style={{ width: S, height: S, maxWidth: '100%', touchAction: 'none', cursor: 'grab', display: 'block' }}
                role="img" aria-label={`Globe at ${clock(now)}: the satellite's track, ${plan.city_a.name} and ${plan.city_b.name}, night shaded`}
                onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, r: rot }; (e.target as HTMLElement).setPointerCapture(e.pointerId) }}
                onPointerMove={(e) => { const d = drag.current; if (!d) return; setRot([Math.max(-85, Math.min(85, d.r[0] + (e.clientY - d.y) * 0.4)), d.r[1] - (e.clientX - d.x) * 0.4]) }}
                onPointerUp={() => { drag.current = null }} />
              <div className="row wrap" style={{ gap: 8, marginTop: 6 }}>
                <button className="btn small" onClick={() => setPlaying((p) => !p)}>{playing ? 'Pause' : 'Play'}</button>
                <input type="range" min={0} max={plan.track.length - 1} value={t} onChange={(e) => setT(Number(e.target.value))} aria-label="Time of day" style={{ flex: 1, minWidth: 140 }} />
                <span className="mono sub">{clock(now)}</span>
              </div>
              <div className="sub" style={{ marginTop: 4 }}>
                {plan.city_a.name} elevation {plan.el_a[t].toFixed(0)}°{plan.night_a[t] ? ' (night)' : ' (day)'} · {plan.city_b.name} {plan.el_b[t].toFixed(0)}°{plan.night_b[t] ? ' (night)' : ' (day)'} · drag to turn the globe
              </div>
            </div>
            <div>
              <div className="mini-tiles" style={{ marginTop: 0 }}>
                <span><b>{plan.distance_km.toLocaleString()} km</b> apart</span>
                <span><b>{Math.round(plan.entangled_pairs_per_day).toLocaleString()}</b> entangled pairs a day</span>
                <span><b>{Math.round(plan.shared_key_bits_per_day).toLocaleString()}</b> key bits a day, trusting nobody</span>
                <span><b>{Math.round(plan.trusted_key_bits_per_day).toLocaleString()}</b> key bits a day, trusting the satellite</span>
              </div>
              <table className="calls disc-table">
                <thead><tr><th>Pass</th><th>Who sees it</th><th className="num">Minutes</th><th className="num">Max elevation</th><th className="num">Pairs</th><th className="num">Key bits</th></tr></thead>
                <tbody>
                  {plan.passes.map((p, i) => (
                    <tr key={i} onClick={() => jump(p.start_utc)} style={{ cursor: 'pointer' }} className={p.kind === 'both' ? 'sel' : ''}>
                      <td className="mono">{clock(p.start_utc)}</td><td>{name(p.kind)}</td><td className="num">{p.minutes.toFixed(1)}</td>
                      <td className="num">{p.max_el_a.toFixed(0)}°{p.max_el_b !== null ? ` / ${p.max_el_b.toFixed(0)}°` : ''}</td>
                      <td className="num">{p.pairs !== null ? Math.round(p.pairs).toLocaleString() : '–'}</td><td className="num">{Math.round(p.key_bits).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {plan.passes.length === 0 && <p className="sub">No usable pass in this day.</p>}
              <p className="sub obs-method">Orbit like Micius's: 500 km, 97.4° (sun-synchronous), J2 drift and the Earth's rotation; Sun from the NOAA formula; passes above 15° with the Sun below −12°.
                Gold beams: both cities see it at once, so entangled pairs can be shared without trusting anyone (network model, real slant ranges). Blue: one city at a time, a decoy-state BB84 downlink with the
                satellite as a trusted node, as Micius did between China and Austria. Air mass 1/sin(elevation) for the atmosphere. Date: {plan.start_utc.slice(0, 10)}. Coastlines: Natural Earth.</p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
