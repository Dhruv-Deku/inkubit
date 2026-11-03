import { useEffect, useMemo, useRef, useState } from 'react'
import land from 'world-atlas/land-110m.json'
import { api, ApiError } from '../api'
import type { OrbitMeta, OrbitPlan } from '../types'

type V3 = [number, number, number]
const RAD = Math.PI / 180
const R_E = 6378.137
const MIN_EL = 15

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
const norm = (v: V3): V3 => { const n = Math.hypot(...v) || 1; return [v[0] / n, v[1] / n, v[2] / n] }
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

/** The satellite's sub-point as a unit vector at fractional step t (interpolated between the 30 s samples). */
function subAt(plan: OrbitPlan, t: number): V3 {
  const n = plan.track.length - 1
  const k = Math.max(0, Math.min(n, Math.floor(t))), k2 = Math.min(n, k + 1), f = Math.max(0, Math.min(1, t - k))
  const a = toV(...plan.track[k]), b = toV(...plan.track[k2])
  return norm([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f])
}
const altAt = (plan: OrbitPlan, t: number) => plan.alt_km.length ? plan.alt_km[Math.max(0, Math.min(plan.alt_km.length - 1, Math.floor(t / 10)))] : 500

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
  const k = Math.max(0, Math.min(plan.track.length - 1, Math.floor(t)))
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
  const sun = plan.sun[Math.min(plan.sun.length - 1, Math.floor(k / 10))]
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
  const h = altAt(plan, t), rs = 1 + h / R_E
  const c = subAt(plan, t)
  // footprint: where the satellite stands above 15 degrees
  const psi = Math.acos(Math.cos(MIN_EL * RAD) / rs) - MIN_EL * RAD
  const e1 = norm(Math.abs(c[2]) > 0.95 ? cross(c, [1, 0, 0]) : cross(c, [0, 0, 1])), e2 = cross(c, e1)
  ctx.strokeStyle = 'rgba(57,135,229,0.55)'
  ctx.lineWidth = 1
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  let pen = false
  for (let a = 0; a <= 360; a += 5) {
    const ca = Math.cos(a * RAD) * Math.sin(psi), sa = Math.sin(a * RAD) * Math.sin(psi), cp = Math.cos(psi)
    const p = view([c[0] * cp + e1[0] * ca + e2[0] * sa, c[1] * cp + e1[1] * ca + e2[1] * sa, c[2] * cp + e1[2] * ca + e2[2] * sa])
    if (p[2] < 0) { pen = false; continue }
    const [x, y] = px(p)
    if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y)
    pen = true
  }
  ctx.stroke()
  ctx.setLineDash([])
  // orbit track 50 minutes either side, at altitude; hidden behind the Earth when in its shadow from the viewer
  const k0 = Math.max(0, k - 100), k1 = Math.min(plan.track.length - 1, k + 100)
  const vis = (p: V3) => p[2] > 0 || Math.hypot(p[0], p[1]) > 1
  ctx.lineWidth = 1.4
  let prev: V3 | null = null
  for (let j = k0; j <= k1; j++) {
    const [la, lo] = plan.track[j]
    const p = view(toV(la, lo, rs))
    if (prev && vis(p) && vis(prev)) {
      ctx.strokeStyle = j <= t ? 'rgba(169,171,178,0.35)' : 'rgba(57,135,229,0.75)'
      ctx.beginPath(); ctx.moveTo(...px(prev)); ctx.lineTo(...px(p)); ctx.stroke()
    }
    prev = p
  }
  // stations and beams
  const sat = view([c[0] * rs, c[1] * rs, c[2] * rs])
  const cities = [{ c: plan.city_a, el: plan.el_a[k], night: plan.night_a[k] }, { c: plan.city_b, el: plan.el_b[k], night: plan.night_b[k] }]
  const both = plan.satellite.dual && cities.every((s) => s.el >= MIN_EL && s.night)
  ctx.font = `${Math.round(S / 46)}px 'IBM Plex Sans', system-ui, sans-serif`
  const placed: [number, number, number, number][] = []  // label boxes already drawn, to keep labels apart
  for (const s of cities) {
    const p = view(toV(s.c.lat, s.c.lon))
    if (s.el >= MIN_EL && s.night) {
      ctx.strokeStyle = both ? '#d9a441' : '#3987e5'
      ctx.lineWidth = 2
      ctx.beginPath(); ctx.moveTo(...px(p)); ctx.lineTo(...px(sat)); ctx.stroke()
    }
    if (p[2] < 0) continue
    const [x, y] = px(p)
    ctx.fillStyle = '#ecebe8'; ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.fill()
    const w = ctx.measureText(s.c.name).width, fh = S / 46
    let lx = x + 7 + w > S - 4 ? x - 7 - w : x + 7, ly = y - 6
    if (placed.some(([bx, by, bw, bh]) => lx < bx + bw && lx + w > bx && ly - fh < by && ly > by - bh)) { ly = y + fh + 6; lx = Math.min(lx, S - 4 - w) }
    placed.push([lx, ly, w, fh])
    ctx.fillText(s.c.name, lx, ly)
  }
  if (vis(sat)) {
    const [x, y] = px(sat)
    ctx.fillStyle = '#1b1c20'; ctx.strokeStyle = '#ecebe8'; ctx.lineWidth = 1.6
    ctx.fillRect(x - 9, y - 2, 6, 4); ctx.fillRect(x + 3, y - 2, 6, 4)
    ctx.strokeRect(x - 9, y - 2, 6, 4); ctx.strokeRect(x + 3, y - 2, 6, 4)
    ctx.beginPath(); ctx.arc(x, y, 3.5, 0, 2 * Math.PI); ctx.fillStyle = '#ecebe8'; ctx.fill()
    ctx.font = `${Math.round(S / 50)}px 'IBM Plex Sans', system-ui, sans-serif`
    ctx.fillStyle = '#a9abb2'; ctx.fillText(plan.satellite.name, x + 12, y + 4)
  }
}

const when = (iso: string) => { const d = new Date(iso); return `${d.toUTCString().slice(0, 11)} ${d.toISOString().slice(11, 16)} UTC` }
const bits = (n: number) => Math.round(n).toLocaleString()
const pct = (v: number | null | undefined) => (v === null || v === undefined ? '–' : `${Math.round(v)}%`)

/** A quantum satellite over two cities. SpeQtre and QUBE-II fly their real orbits (today's CelesTrak elements,
 *  SGP4) from now, live, under the cloud forecast; Micius, which re-entered in January 2026, flies a modelled orbit. */
export function GlobePanel() {
  const [meta, setMeta] = useState<OrbitMeta | null>(null)
  const [sat, setSat] = useState('speqtre')
  const [ab, setAb] = useState<[string, string]>(['chilbolton', 'singapore'])
  const [night, setNight] = useState(true)
  const [plan, setPlan] = useState<OrbitPlan | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [live, setLive] = useState(false)
  const [rot, setRot] = useState<[number, number]>([30, 100])
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const box = useRef<HTMLDivElement | null>(null)
  const [S, setS] = useState(520)
  const rings = useMemo(landRings, [])
  useEffect(() => { api.orbitCities().then(setMeta).catch(() => {}) }, [])
  useEffect(() => {
    let alive = true
    setLoading(true)
    api.orbits(ab[0], ab[1], night, sat).then((p) => {
      if (!alive) return
      setPlan(p); setError(null); setPlaying(false)
      if (p.now_index !== null) { setLive(true); setT(p.now_index) } else {
        setLive(false)
        const first = p.passes.find((x) => x.kind === 'both') ?? p.passes[0]
        setT(first ? Math.max(0, Math.round((Date.parse(first.start_utc) - Date.parse(p.start_utc)) / 1000 / p.step_s) - 6) : 0)
      }
      setRot([(p.city_a.lat + p.city_b.lat) / 2, (p.city_a.lon + p.city_b.lon) / 2 + (Math.abs(p.city_a.lon - p.city_b.lon) > 180 ? 180 : 0)])
    }).catch((e) => { if (alive) setError(e instanceof ApiError ? e.message : 'The planner failed.') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [ab, night, sat])
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setS(Math.max(280, Math.min(620, Math.round(e.contentRect.width)))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [plan !== null]) // eslint-disable-line react-hooks/exhaustive-deps
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
    const id = window.setInterval(() => setT((k) => (Math.floor(k) + 1) % plan.track.length), 40)
    return () => window.clearInterval(id)
  }, [playing, plan])
  // live: follow the real clock (the track starts at the plan's start, sampled every step_s seconds)
  useEffect(() => {
    if (!live || !plan || plan.now_index === null) return
    const tick = () => setT(Math.min(plan.track.length - 1, (Date.now() - Date.parse(plan.start_utc)) / 1000 / plan.step_s))
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [live, plan])
  const drag = useRef<{ x: number; y: number; r: [number, number] } | null>(null)
  const real = !!plan?.satellite.real
  const k = plan ? Math.max(0, Math.min(plan.track.length - 1, Math.floor(t))) : 0
  const now = plan ? new Date(Date.parse(plan.start_utc) + t * plan.step_s * 1000).toISOString() : ''
  const jump = (iso: string) => { if (!plan) return; setLive(false); setPlaying(false); setT(Math.max(0, Math.round((Date.parse(iso) - Date.parse(plan.start_utc)) / 1000 / plan.step_s) - 4)) }
  const who = (kind: string) => (kind === 'a' ? plan?.city_a.name : kind === 'b' ? plan?.city_b.name : 'both cities at once')
  const pickSat = (id: string) => {
    if (!meta) return
    setSat(id)
    const own = meta.pairs.find((p) => p.sat === id)
    const cur = meta.pairs.find((p) => p.a === ab[0] && p.b === ab[1])
    if (own && cur && cur.sat && cur.sat !== id) setAb([own.a, own.b])
  }
  const pairs = meta ? meta.pairs.filter((p) => p.sat === null || p.sat === sat) : []
  const here = plan ? subAt(plan, t) : null
  const maxDay = plan ? Math.max(1, ...plan.outlook.map((o) => o.trusted)) : 1
  const el = plan?.satellite.elements
  return (
    <div className="panel globe">
      <div className="panel-head">
        <h2>Satellite planner</h2>
        <span className="sub">real satellites, today's orbits, tonight's clouds</span>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        {meta?.satellites.map((s) => (
          <button key={s.id} className={`chip-btn${sat === s.id ? ' on' : ''}`} onClick={() => pickSat(s.id)}>
            {s.name} <span className="muted">· {s.real ? 'in orbit now' : '2017, modelled'}</span>
          </button>
        ))}
      </div>
      <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
        {pairs.map((p) => (
          <button key={p.a + p.b} className={`chip-btn${ab[0] === p.a && ab[1] === p.b ? ' on' : ''}`} onClick={() => { setAb([p.a, p.b]); if (p.sat && p.sat !== sat) setSat(p.sat) }}>{p.label}</button>
        ))}
      </div>
      <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
        <select value={ab[0]} onChange={(e) => setAb([e.target.value, ab[1]])} aria-label="City A">{meta?.cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select value={ab[1]} onChange={(e) => setAb([ab[0], e.target.value])} aria-label="City B">{meta?.cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <label className="row sub" style={{ gap: 6 }}><input type="checkbox" checked={night} onChange={(e) => setNight(e.target.checked)} /> night only (free-space links need the dark)</label>
        {loading && <span className="row sub" style={{ gap: 6 }}><span className="spin" /> {sat === 'micius' ? 'computing passes' : 'today’s elements from CelesTrak, SGP4 and the cloud forecast'}</span>}
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {plan && (
        <>
          <div className="sat-card">
            <div className="row wrap" style={{ gap: 8 }}>
              <b>{plan.satellite.name}</b>
              <span className={`badge${real ? ' live-badge' : ''}`}>{real ? 'in orbit' : plan.satellite.status}</span>
              <span className="sub">NORAD {plan.satellite.norad} · {plan.satellite.aperture_mm} mm telescope{plan.satellite.dual ? ' (two downlinks)' : ''}{plan.satellite.height_km ? ` · ${plan.satellite.height_km[0].toFixed(0)}–${plan.satellite.height_km[1].toFixed(0)} km up, ${plan.satellite.period_min} min a lap, ${plan.satellite.inclination_deg}°` : ''}</span>
            </div>
            {el && (
              <div className="sub" style={{ marginTop: 4 }}>
                Elements: <b className={el.source === 'CelesTrak' ? '' : 'warn-text'}>{el.source}</b>, epoch {when(el.epoch_utc)} ({el.age_hours.toFixed(1)} h before the window starts), propagated with SGP4{plan.clouds ? `; clouds: ${plan.clouds}` : '; no cloud forecast reachable, so clear sky is assumed'}.
                <details className="tle"><summary>the two-line elements</summary><pre className="mono">{el.line1}{'\n'}{el.line2}</pre></details>
              </div>
            )}
            <p className="sub" style={{ margin: '6px 0 0', maxWidth: '100ch' }}>{plan.satellite.note}</p>
          </div>
          <p className="obs-head" style={{ margin: '12px 0 4px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>{plan.finding}</p>
          <div className="globe-grid">
            <div ref={box}>
              <canvas ref={canvas} style={{ width: S, height: S, maxWidth: '100%', touchAction: 'none', cursor: 'grab', display: 'block' }}
                role="img" aria-label={`Globe at ${when(now)}: ${plan.satellite.name}'s track and footprint, ${plan.city_a.name} and ${plan.city_b.name}, night shaded`}
                onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, r: rot }; (e.target as HTMLElement).setPointerCapture(e.pointerId) }}
                onPointerMove={(e) => { const d = drag.current; if (!d) return; setRot([Math.max(-85, Math.min(85, d.r[0] + (e.clientY - d.y) * 0.4)), d.r[1] - (e.clientX - d.x) * 0.4]) }}
                onPointerUp={() => { drag.current = null }} />
              <div className="row wrap" style={{ gap: 8, marginTop: 6 }}>
                <button className="btn small" onClick={() => { setLive(false); setPlaying((p) => !p) }}>{playing ? 'Pause' : 'Play'}</button>
                {real && <button className={`btn small${live ? ' primary' : ''}`} onClick={() => { setPlaying(false); setLive(true) }} aria-pressed={live}>{live ? 'Live' : 'Now'}</button>}
                <input type="range" min={0} max={plan.track.length - 1} value={k} onChange={(e) => { setLive(false); setT(Number(e.target.value)) }} aria-label="Time" style={{ flex: 1, minWidth: 140 }} />
                <span className="mono sub">{when(now)}</span>
              </div>
              {here && (
                <div className="sub" style={{ marginTop: 4 }}>
                  {live && <span className="live-dot" aria-hidden="true" />}
                  {live ? 'Now: ' : ''}{plan.satellite.name} over {Math.abs(Math.asin(here[2]) / RAD).toFixed(1)}° {here[2] >= 0 ? 'N' : 'S'}, {Math.abs(Math.atan2(here[1], here[0]) / RAD).toFixed(1)}° {here[1] >= 0 ? 'E' : 'W'}, {altAt(plan, t).toFixed(0)} km up
                  {' '}<button className="link-btn" onClick={() => setRot([Math.asin(here[2]) / RAD, Math.atan2(here[1], here[0]) / RAD])}>show it</button>
                  <br />{plan.city_a.name} elevation {plan.el_a[k].toFixed(0)}°{plan.night_a[k] ? ' (night)' : ' (day)'} · {plan.city_b.name} {plan.el_b[k].toFixed(0)}°{plan.night_b[k] ? ' (night)' : ' (day)'} · drag to turn the globe
                </div>
              )}
            </div>
            <div>
              <div className="mini-tiles" style={{ marginTop: 0 }}>
                <span><b>{plan.distance_km.toLocaleString()} km</b> apart</span>
                {plan.satellite.dual && <span><b>{bits(plan.entangled_pairs_per_day)}</b> entangled pairs a day</span>}
                {plan.satellite.dual && <span><b>{bits(plan.shared_key_bits_per_day)}</b> key bits a day, trusting nobody</span>}
                <span><b>{bits(plan.trusted_key_bits_per_day)}</b> key bits {real ? 'in 24 h' : 'a day'}, trusting the satellite{real ? ', clear sky' : ''}</span>
                {plan.expected_trusted_key_bits !== null && <span><b>{bits(plan.expected_trusted_key_bits)}</b> expected under the cloud forecast</span>}
              </div>
              <table className="calls disc-table">
                <thead><tr><th>Pass</th><th>Who sees it</th><th className="num">Minutes</th><th className="num">Max elevation</th>
                  {plan.satellite.dual && <th className="num">Pairs</th>}<th className="num">Key bits{plan.clouds ? ', clear' : ''}</th>
                  {plan.clouds && <th className="num">Cloud</th>}{plan.clouds && <th className="num">Expected</th>}</tr></thead>
                <tbody>
                  {plan.passes.map((p, i) => (
                    <tr key={i} onClick={() => jump(p.start_utc)} style={{ cursor: 'pointer' }} className={p.kind === 'both' ? 'sel' : ''}>
                      <td className="mono">{real ? when(p.start_utc) : when(p.start_utc).slice(12)}</td><td>{who(p.kind)}</td><td className="num">{p.minutes.toFixed(1)}</td>
                      <td className="num">{p.max_el_a.toFixed(0)}°{p.max_el_b !== null ? ` / ${p.max_el_b.toFixed(0)}°` : ''}</td>
                      {plan.satellite.dual && <td className="num">{p.pairs !== null ? bits(p.pairs) : '–'}</td>}<td className="num">{bits(p.key_bits)}</td>
                      {plan.clouds && <td className="num">{p.kind === 'both' ? `${pct(p.cloud_a)} / ${pct(p.cloud_b)}` : pct(p.kind === 'a' ? p.cloud_a : p.cloud_b)}</td>}
                      {plan.clouds && <td className="num">{p.expected_key_bits !== null ? bits(p.expected_key_bits) : '–'}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
              {plan.passes.length === 0 && <p className="sub">No usable pass in this window.</p>}
              {plan.outlook.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <h3 style={{ margin: '0 0 2px' }}>The next {plan.outlook.length} days</h3>
                  <div className="legend-row" style={{ marginTop: 2 }}>
                    <span><i className="sw sw-clear" /> shared key, clear sky</span>
                    {plan.clouds && <span><i className="sw sw-exp" /> expected under the forecast</span>}
                  </div>
                  <table className="calls disc-table outlook">
                    <thead><tr><th>24 h from {plan.outlook[0].from_utc.slice(11, 16)} UTC</th><th className="num">Passes</th><th className="num">Cloud</th><th>Shared key bits</th></tr></thead>
                    <tbody>
                      {plan.outlook.map((o) => {
                        const v = o.expected_trusted ?? o.trusted
                        return (
                          <tr key={o.from_utc}>
                            <td className="mono">{when(o.from_utc).slice(0, 11).replace(',', '')}</td>
                            <td className="num">{o.passes_a} / {o.passes_b}</td>
                            <td className="num" style={{ whiteSpace: 'nowrap' }}>{pct(o.cloud_a)} / {pct(o.cloud_b)}</td>
                            <td><div className="ol-cell">
                              <div className="ol-bar" title={`clear sky ${bits(o.trusted)}${o.expected_trusted !== null ? `, expected ${bits(o.expected_trusted)}` : ''}`}>
                                <span className="ol-clear" style={{ width: `${(o.trusted / maxDay) * 100}%` }} />
                                {o.expected_trusted !== null && <span className="ol-exp" style={{ width: `${(o.expected_trusted / maxDay) * 100}%` }} />}
                              </div>
                              <span className="mono ol-val">{bits(v)}</span>
                            </div></td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  <p className="sub" style={{ marginTop: 4 }}>Passes are {plan.city_a.name} / {plan.city_b.name}; the cloud column is the forecast mean over each station's passes. Forecasts beyond about three days are rough.</p>
                </div>
              )}
              {real ? (
                <p className="sub obs-method">Orbit: SGP4 on CelesTrak's two-line elements, fetched at most every two hours and checksummed, to Earth-fixed coordinates through sidereal time; the frame chain matches Skyfield,
                  an independent implementation, to 0.01° and 0.1 km (tested). Stations on the WGS84 ellipsoid, Sun from the NOAA formula, passes above 15° with the Sun below −12°; the dashed ring is where the satellite stands above 15°.
                  Key: a decoy-state BB84 downlink through the satellite's own {plan.satellite.aperture_mm} mm telescope, the satellite a trusted node; the real payloads' source rates and protocols differ, so key bits are estimates, while pass times,
                  elevations and clouds are real data. Clouds: Open-Meteo hourly total cloud cover at each station; expected key is the clear-sky key times the clear fraction. Coastlines: Natural Earth.</p>
              ) : (
                <p className="sub obs-method">Micius re-entered on 25 January 2026, so its orbit is modelled: 500 km, 97.4° (sun-synchronous), J2 drift and the Earth's rotation, over {plan.start_utc.slice(0, 10)}. Stations on the WGS84 ellipsoid; Sun from the NOAA formula; passes above 15° with the Sun below −12°.
                  Gold beams: both cities see it at once, so entangled pairs can be shared without trusting anyone (network model, real slant ranges). Blue: one city at a time, a decoy-state BB84 downlink with the
                  satellite as a trusted node, as Micius did between China and Austria. Air mass 1/sin(elevation) for the atmosphere. Coastlines: Natural Earth.</p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
