import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { landRings } from './Globe'

/** The quantum internet on a 3D Earth: land from Natural Earth, lit by the real Sun, cities, routes coloured by key
 *  rate, entangled photon pairs travelling along them, and the operating key satellites on their real orbits. */

export interface EarthCity { id: string; name: string; lat: number; lon: number }
export interface EarthRoute {
  key: string; a: string; b: string; kind: 'fiber' | 'repeaters' | 'satellite'; satellite?: string | null
  path: [number, number][]; repeater_points?: [number, number][]; key_rate_bps: number
}
export interface SkySat { id: string; name: string; track: [number, number, number][] }
export type Pick = { type: 'city'; id: string } | { type: 'route'; key: string } | { type: 'none' }
export interface EarthHandle {
  setCities(c: EarthCity[]): void
  setRoutes(r: EarthRoute[]): void
  setSky(startMs: number, stepS: number, sats: SkySat[]): void
  setSpeed(x: number): void
  setSelection(sel: { city?: string | null; route?: string | null; pending?: string | null }): void
  focus(lat: number, lon: number): void
  dispose(): void
}

const D = Math.PI / 180
const R = 1
const BG = 0x111214
const GOLD = 0xd9a441 // reserved for entanglement: the photon pairs and the satellite beams
const HIT = 0.022

/** Colour of a route by what it delivers: no key, a trickle (bits a day), a usable rate, a fast link. */
export function rateColour(bps: number): string {
  if (!(bps > 0)) return '#e5484d'
  if (bps < 1) return '#c3c7cf'
  if (bps < 100) return '#3987e5'
  return '#4cc38a'
}

export const toVec = (lat: number, lon: number, r = R) =>
  new THREE.Vector3(r * Math.cos(lat * D) * Math.cos(lon * D), r * Math.sin(lat * D), -r * Math.cos(lat * D) * Math.sin(lon * D))

/** Sub-solar point (degrees) for a time, from the low-precision solar coordinates of the Astronomical Almanac. */
export function subsolar(ms: number): [number, number] {
  const d = ms / 86400000 - 10957.5
  const g = (357.529 + 0.98560028 * d) * D
  const q = 280.459 + 0.98564736 * d
  const L = (q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * D
  const e = (23.439 - 0.00000036 * d) * D
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L))
  const dec = Math.asin(Math.sin(e) * Math.sin(L))
  const gmst = (((18.697374558 + 24.06570982441908 * d) % 24) + 24) % 24 * 15 * D
  const lon = ((((ra - gmst) / D) % 360) + 540) % 360 - 180
  return [dec / D, lon]
}

function landTexture(maxAniso: number): THREE.CanvasTexture {
  const W = 4096, H = 2048
  const c = document.createElement('canvas')
  c.width = W; c.height = H
  const g = c.getContext('2d')!
  g.fillStyle = '#1b2230'
  g.fillRect(0, 0, W, H)
  g.strokeStyle = 'rgba(255,255,255,0.06)'
  g.lineWidth = 2
  for (let lon = -180; lon <= 180; lon += 30) { const x = (lon + 180) / 360 * W; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke() }
  for (let lat = -60; lat <= 60; lat += 30) { const y = (90 - lat) / 180 * H; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke() }
  const rings = landRings()
  const trace = (ring: [number, number][]) => {
    g.beginPath()
    ring.forEach(([lon, lat], i) => {
      const x = (lon + 180) / 360 * W, y = (90 - lat) / 180 * H
      if (i === 0) g.moveTo(x, y); else g.lineTo(x, y)
    })
    g.closePath()
  }
  g.fillStyle = '#4a4f59'
  for (const ring of rings) { trace(ring); g.fill() }
  g.strokeStyle = '#b4b9c2'
  g.lineWidth = 2.6
  for (const ring of rings) { trace(ring); g.stroke() }
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = maxAniso
  return tex
}

function dotTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const g = c.getContext('2d')!
  g.fillStyle = '#fff'
  g.beginPath(); g.arc(32, 32, 26, 0, Math.PI * 2); g.fill()
  return new THREE.CanvasTexture(c)
}

interface Built {
  route: EarthRoute
  group: THREE.Group
  curve: THREE.Curve<THREE.Vector3>
  sources: number[] // curve parameters where pairs are made
  hit: THREE.Object3D
  colour: THREE.Color
}

interface Photon { r: Built; t: number; dir: number; speed: number; end: number; alive: boolean }

export function mountEarth(host: HTMLElement, opts: {
  onPick(p: Pick): void
  onHover(text: string | null, x: number, y: number): void
  onTime?(ms: number): void
}): EarthHandle {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearColor(BG)
  host.appendChild(renderer.domElement)
  const gl = renderer.getContext()
  const info = gl.getExtension('WEBGL_debug_renderer_info')
  const gpu = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : ''
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const still = reduced || /swiftshader|llvmpipe|softpipe|software|basic render/i.test(gpu)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 50)
  camera.position.copy(toVec(25, 40, 3.3))
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.enablePan = false
  controls.minDistance = 1.35
  controls.maxDistance = 6
  controls.rotateSpeed = 0.55
  controls.zoomSpeed = 0.7
  controls.autoRotate = !still
  controls.autoRotateSpeed = 0.35
  controls.addEventListener('start', () => { controls.autoRotate = false; flight = null })

  const disposables: { dispose(): void }[] = [renderer, controls]
  const track = <X extends { dispose(): void }>(x: X): X => { disposables.push(x); return x }

  const earthTex = track(landTexture(renderer.capabilities.getMaxAnisotropy()))
  const earth = new THREE.Mesh(track(new THREE.SphereGeometry(R, 160, 80)),
    track(new THREE.MeshStandardMaterial({ map: earthTex, roughness: 0.95, metalness: 0 })))
  scene.add(earth)
  const sun = new THREE.DirectionalLight(0xfff6ea, 3.2)
  scene.add(sun)
  scene.add(new THREE.AmbientLight(0x8d9bb8, 0.3))

  const cityLayer = new THREE.Group()
  const routeLayer = new THREE.Group()
  const satLayer = new THREE.Group()
  scene.add(cityLayer, routeLayer, satLayer)

  // HTML labels over the canvas
  const labels = document.createElement('div')
  labels.className = 'earth-labels'
  host.appendChild(labels)
  const labelFor = new Map<string, HTMLDivElement>()
  const label = (key: string, text: string, cls: string) => {
    let el = labelFor.get(key)
    if (!el) { el = document.createElement('div'); labels.appendChild(el); labelFor.set(key, el) }
    const c = `earth-label ${cls}`
    if (el.className !== c) el.className = c
    if (el.textContent !== text) el.textContent = text
    return el
  }

  let cities: EarthCity[] = []
  const cityPos = new Map<string, THREE.Vector3>()
  const cityHits: THREE.Mesh[] = []
  const dotGeo = track(new THREE.SphereGeometry(1, 12, 8))
  const hitGeo = track(new THREE.SphereGeometry(HIT, 8, 6))
  const hitMat = track(new THREE.MeshBasicMaterial({ visible: false }))
  const cityMat = track(new THREE.MeshBasicMaterial({ color: 0xa9abb2 }))
  const usedMat = track(new THREE.MeshBasicMaterial({ color: 0xf2f1ee }))
  const pendMat = track(new THREE.MeshBasicMaterial({ color: 0x3987e5 }))
  let used = new Set<string>()
  let sel: { city?: string | null; route?: string | null; pending?: string | null } = {}
  const cityDots = new Map<string, THREE.Mesh>()

  function drawCities() {
    for (const m of cityDots.values()) cityLayer.remove(m)
    for (const h of cityHits) cityLayer.remove(h)
    cityDots.clear(); cityHits.length = 0
    for (const c of cities) {
      const p = toVec(c.lat, c.lon, R * 1.001)
      cityPos.set(c.id, p)
      const on = used.has(c.id) || sel.city === c.id || sel.pending === c.id
      const dot = new THREE.Mesh(dotGeo, sel.pending === c.id ? pendMat : on ? usedMat : cityMat)
      dot.scale.setScalar(on ? 0.0105 : 0.0058)
      dot.position.copy(p)
      cityLayer.add(dot)
      cityDots.set(c.id, dot)
      const hit = new THREE.Mesh(hitGeo, hitMat)
      hit.position.copy(p)
      hit.userData = { city: c.id }
      cityLayer.add(hit)
      cityHits.push(hit)
    }
  }

  // ---------- routes ----------
  let built: Built[] = []
  const routeDisposables: { dispose(): void }[] = []
  function clearRoutes() {
    for (const b of built) routeLayer.remove(b.group)
    for (const d of routeDisposables) d.dispose()
    routeDisposables.length = 0
    built = []
    photons.length = 0
  }

  function buildRoute(r: EarthRoute): Built {
    const colour = new THREE.Color(rateColour(r.key_rate_bps))
    const group = new THREE.Group()
    const n = r.path.length
    const span = Math.min(1, (r.path.length > 1 ? toVec(...r.path[0]).angleTo(toVec(...r.path[n - 1])) : 0) / 0.6)
    const pts = r.path.map(([lat, lon], i) => {
      const t = i / (n - 1)
      const lift = r.kind === 'satellite' ? 0.012 + 0.2 * Math.sin(Math.PI * t) * (0.35 + 0.65 * span) : 0.0035
      return toVec(lat, lon, R + lift)
    })
    const curve = new THREE.CatmullRomCurve3(pts)
    let hit: THREE.Object3D
    if (r.kind === 'satellite') {
      const geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(160))
      const mat = new THREE.LineDashedMaterial({ color: colour, dashSize: 0.018, gapSize: 0.012, transparent: true, opacity: 0.95 })
      routeDisposables.push(geo, mat)
      const line = new THREE.Line(geo, mat)
      line.computeLineDistances()
      group.add(line)
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 80, 0.012, 5), hitMat)
      routeDisposables.push(tube.geometry)
      group.add(tube)
      hit = tube
    } else {
      const geo = new THREE.TubeGeometry(curve, Math.max(24, n * 3), 0.0034, 6)
      const mat = new THREE.MeshBasicMaterial({ color: colour })
      routeDisposables.push(geo, mat)
      const tube = new THREE.Mesh(geo, mat)
      group.add(tube)
      const fat = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.max(24, n * 3), 0.014, 5), hitMat)
      routeDisposables.push(fat.geometry)
      group.add(fat)
      hit = fat
      for (const [lat, lon] of r.repeater_points ?? []) {
        const box = new THREE.Mesh(new THREE.BoxGeometry(0.016, 0.016, 0.016), usedMat)
        routeDisposables.push(box.geometry)
        box.position.copy(toVec(lat, lon, R + 0.006))
        box.lookAt(0, 0, 0)
        group.add(box)
      }
    }
    hit.userData = { route: r.key }
    const k = (r.repeater_points?.length ?? 0)
    const sources = r.kind === 'repeaters' ? Array.from({ length: k + 1 }, (_, i) => (i + 0.5) / (k + 1)) : [0.5]
    return { route: r, group, curve, sources, hit, colour }
  }

  // ---------- photons: entangled pairs leave each source in opposite directions ----------
  const MAX_PHOTONS = 900
  const photons: Photon[] = []
  const pGeo = track(new THREE.BufferGeometry())
  const pPos = new Float32Array(MAX_PHOTONS * 3)
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3))
  const pMat = track(new THREE.PointsMaterial({ color: GOLD, size: 0.034, map: track(dotTexture()), alphaTest: 0.5,
    sizeAttenuation: true, transparent: true }))
  const points = new THREE.Points(pGeo, pMat)
  points.frustumCulled = false
  scene.add(points)
  const spawnClock = new Map<string, number>()

  function spawn(b: Built, dt: number) {
    const bps = b.route.key_rate_bps
    const perDay = Math.max(0, bps) * 86400
    const pairsPerS = 0.6 + 2.6 * Math.min(1, Math.log10(1 + perDay) / 8)
    const acc = (spawnClock.get(b.route.key) ?? 0) + dt * pairsPerS * b.sources.length
    let n = Math.floor(acc)
    spawnClock.set(b.route.key, acc - n)
    while (n-- > 0 && photons.length < MAX_PHOTONS - 2) {
      const s = b.sources[Math.floor(Math.random() * b.sources.length)]
      const half = 0.5 / b.sources.length
      // with no key the pairs are lost on the way: they fade out before reaching the ends
      const lost = !(bps > 0)
      const reach = lost ? 0.15 + Math.random() * 0.55 : 1
      const speed = 0.16 / Math.max(0.25, b.curve.getLength())
      photons.push({ r: b, t: s, dir: 1, speed, end: Math.min(1, s + half * reach), alive: true })
      photons.push({ r: b, t: s, dir: -1, speed, end: Math.max(0, s - half * reach), alive: true })
    }
  }

  // ---------- satellites on their real orbits ----------
  interface Sat { id: string; name: string; pos: THREE.Vector3[]; mesh: THREE.Group; orbit: THREE.Line; beams: THREE.LineSegments }
  let sats: Sat[] = []
  let skyStart = Date.now(), skyStep = 20, simMs = Date.now(), speed = 60
  const satMat = track(new THREE.MeshStandardMaterial({ color: 0xd8dbe2, roughness: 0.5, metalness: 0.3 }))
  const panelMat = track(new THREE.MeshStandardMaterial({ color: 0x6f95d6, emissive: 0x1d2c48, roughness: 0.4, metalness: 0.4, side: THREE.DoubleSide }))
  const beamMat = track(new THREE.LineBasicMaterial({ color: GOLD, transparent: true, opacity: 0.85 }))
  const orbitMat = track(new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.18 }))

  function satMesh(): THREE.Group {
    const g = new THREE.Group()
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.026, 0.026, 0.038), satMat)
    const p1 = new THREE.Mesh(new THREE.PlaneGeometry(0.08, 0.026), panelMat)
    const p2 = p1.clone()
    p1.position.x = 0.058; p2.position.x = -0.058
    g.add(body, p1, p2)
    return g
  }

  function clearSats() {
    for (const s of sats) { satLayer.remove(s.mesh, s.orbit, s.beams); s.orbit.geometry.dispose(); s.beams.geometry.dispose() }
    sats = []
  }

  function satIndex(): number {
    const total = sats[0]?.pos.length ?? 1
    const i = (simMs - skyStart) / 1000 / skyStep
    return ((i % total) + total) % total
  }

  // ---------- picking and hover ----------
  const ray = new THREE.Raycaster()
  const ndc = new THREE.Vector2()
  let down: { x: number; y: number } | null = null
  const toNdc = (e: PointerEvent) => {
    const r = renderer.domElement.getBoundingClientRect()
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
  }
  function pickAt(): Pick {
    ray.setFromCamera(ndc, camera)
    const earthHit = ray.intersectObject(earth)[0]
    const near = earthHit ? earthHit.distance + 0.02 : Infinity
    const c = ray.intersectObjects(cityHits)[0]
    if (c && c.distance < near) return { type: 'city', id: c.object.userData.city }
    const r = ray.intersectObjects(built.map((b) => b.hit))[0]
    if (r && r.distance < near + 0.25) return { type: 'route', key: r.object.userData.route }
    return { type: 'none' }
  }
  const onDown = (e: PointerEvent) => { down = { x: e.clientX, y: e.clientY } }
  const onUp = (e: PointerEvent) => {
    if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) { down = null; return }
    down = null
    toNdc(e)
    opts.onPick(pickAt())
  }
  const onMove = (e: PointerEvent) => {
    toNdc(e)
    const p = pickAt()
    const r = renderer.domElement.getBoundingClientRect()
    renderer.domElement.style.cursor = p.type === 'none' ? 'grab' : 'pointer'
    if (p.type === 'city') opts.onHover(cities.find((c) => c.id === p.id)?.name ?? null, e.clientX - r.left, e.clientY - r.top)
    else if (p.type === 'route') {
      const b = built.find((x) => x.route.key === p.key)
      opts.onHover(b ? b.route.key : null, e.clientX - r.left, e.clientY - r.top)
    } else opts.onHover(null, 0, 0)
    kick()
  }
  renderer.domElement.addEventListener('pointerdown', onDown)
  renderer.domElement.addEventListener('pointerup', onUp)
  renderer.domElement.addEventListener('pointermove', onMove)
  renderer.domElement.addEventListener('pointerleave', () => opts.onHover(null, 0, 0))

  // ---------- camera flights ----------
  let flight: { from: THREE.Vector3; to: THREE.Vector3; t: number } | null = null

  // ---------- frame ----------
  let raf = 0, last = 0, onScreen = true
  const size = { w: 1, h: 1 }
  const camDir = new THREE.Vector3()
  const tmp = new THREE.Vector3()
  function placeLabel(el: HTMLDivElement, p: THREE.Vector3, surface: boolean) {
    camDir.copy(camera.position).normalize()
    const along = p.dot(camDir)
    // a surface point faces the camera; a point in orbit is hidden while the Earth's disc is in front of it
    const facing = surface ? p.clone().normalize().dot(camDir) : (along >= 0 || p.clone().addScaledVector(camDir, -along).length() > R ? 1 : -1)
    tmp.copy(p).project(camera)
    const w = size.w, h = size.h  // cached: reading the layout here every frame would force a reflow per label
    const visible = facing > 0.12 && tmp.z < 1
    const disp = visible ? '' : 'none'
    if (el.style.display !== disp) el.style.display = disp
    if (visible) {
      const tr = `translate(${Math.round(((tmp.x + 1) / 2) * w)}px, ${Math.round(((1 - tmp.y) / 2) * h)}px)`
      if (el.style.transform !== tr) el.style.transform = tr
    }
  }

  function frame(now: number) {
    raf = 0
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 0.016
    last = now
    if (!still) simMs += dt * 1000 * speed
    opts.onTime?.(simMs)
    const [slat, slon] = subsolar(simMs)
    sun.position.copy(toVec(slat, slon, 10))

    if (flight) {
      flight.t = Math.min(1, flight.t + dt / 1.3)
      const e = flight.t < 0.5 ? 2 * flight.t * flight.t : 1 - (-2 * flight.t + 2) ** 2 / 2
      const dist = camera.position.length()
      camera.position.copy(flight.from.clone().normalize().lerp(flight.to.clone().normalize(), e).normalize().multiplyScalar(dist))
      if (flight.t >= 1) flight = null
    }
    controls.update()

    // photons
    if (!still) {
      for (const b of built) spawn(b, dt)
      let k = 0
      for (let i = photons.length - 1; i >= 0; i--) {
        const ph = photons[i]
        ph.t += ph.dir * ph.speed * dt
        if ((ph.dir > 0 && ph.t >= ph.end) || (ph.dir < 0 && ph.t <= ph.end)) { photons.splice(i, 1); continue }
      }
      for (const ph of photons) {
        if (k >= MAX_PHOTONS) break
        ph.r.curve.getPointAt(Math.min(1, Math.max(0, ph.t)), tmp)
        pPos[k * 3] = tmp.x; pPos[k * 3 + 1] = tmp.y; pPos[k * 3 + 2] = tmp.z
        k++
      }
      pGeo.setDrawRange(0, k)
      pGeo.attributes.position.needsUpdate = true
    } else pGeo.setDrawRange(0, 0)

    // satellites and their beams
    if (sats.length) {
      const idx = satIndex()
      for (const s of sats) {
        const i0 = Math.floor(idx) % s.pos.length, i1 = (i0 + 1) % s.pos.length
        const p = s.pos[i0].clone().lerp(s.pos[i1], idx - Math.floor(idx))
        s.mesh.position.copy(p)
        s.mesh.lookAt(s.pos[i1])
        // the next 100 minutes of orbit
        const n = Math.min(s.pos.length, Math.round(6000 / skyStep))
        const arr = (s.orbit.geometry.attributes.position as THREE.BufferAttribute)
        for (let j = 0; j < n; j++) { const q = s.pos[(i0 + j) % s.pos.length]; arr.setXYZ(j, q.x, q.y, q.z) }
        arr.needsUpdate = true
        s.orbit.geometry.setDrawRange(0, n)
        // a beam to each route city that sees the satellite above 15 degrees
        const ends: THREE.Vector3[] = []
        for (const b of built) {
          if (b.route.kind !== 'satellite' || b.route.satellite !== s.id) continue
          for (const cid of [b.route.a, b.route.b]) {
            const c = cityPos.get(cid)
            if (!c) continue
            const up = c.clone().normalize()
            const v = p.clone().sub(c).normalize()
            if (v.dot(up) > Math.sin(15 * D)) ends.push(p, c)
          }
        }
        const ba = s.beams.geometry.attributes.position as THREE.BufferAttribute
        ends.forEach((v, j) => ba.setXYZ(j, v.x, v.y, v.z))
        ba.needsUpdate = true
        s.beams.geometry.setDrawRange(0, ends.length)
        placeLabel(label(`sat-${s.id}`, s.name, 'sat'), p, false)
      }
    }

    // labels
    for (const c of cities) {
      const show = used.has(c.id) || sel.city === c.id || sel.pending === c.id
      const el = labelFor.get(`city-${c.id}`)
      if (!show) { if (el) el.style.display = 'none'; continue }
      placeLabel(label(`city-${c.id}`, c.name.replace(/ \(.*\)$/, ''), sel.city === c.id || sel.pending === c.id ? 'city on' : 'city'), cityPos.get(c.id)!, true)
    }
    for (const b of built) b.group.children.forEach((m) => {
      const mat = (m as THREE.Mesh).material as THREE.MeshBasicMaterial
      if (mat && mat !== hitMat && 'color' in mat && mat !== usedMat) {
        mat.color.copy(b.colour)
        if (sel.route && sel.route !== b.route.key) mat.color.multiplyScalar(0.45)
      }
    })

    renderer.render(scene, camera)
    // controls.update() above may already have asked for the next frame through its change event: never two
    if (!raf && onScreen && !document.hidden && (!still || flight || controls.autoRotate)) raf = requestAnimationFrame(frame)
  }
  const kick = () => { if (!raf) { last = 0; raf = requestAnimationFrame(frame) } }
  controls.addEventListener('change', kick)
  const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; if (onScreen) kick() }, { threshold: 0.05 })
  io.observe(host)
  const onVis = () => { if (!document.hidden) kick() }
  document.addEventListener('visibilitychange', onVis)
  function resize() {
    const w = host.clientWidth, h = host.clientHeight
    size.w = w; size.h = h
    renderer.setSize(w, h, false)
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    camera.aspect = w / Math.max(1, h)
    camera.updateProjectionMatrix()
  }
  const ro = new ResizeObserver(() => { resize(); kick() })
  ro.observe(host)
  resize()
  kick()

  return {
    setCities(c) { cities = c; drawCities(); kick() },
    setRoutes(rs) {
      clearRoutes()
      used = new Set(rs.flatMap((r) => [r.a, r.b]))
      for (const r of rs) { const b = buildRoute(r); routeLayer.add(b.group); built.push(b) }
      drawCities()
      kick()
    },
    setSky(startMs, stepS, list) {
      clearSats()
      skyStart = startMs; skyStep = stepS; simMs = Date.now()
      for (const s of list) {
        if (!s.track.length) continue
        const pos = s.track.map(([lat, lon, h]) => toVec(lat, lon, R + h / 6371))
        const mesh = satMesh()
        const og = new THREE.BufferGeometry()
        og.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos.length * 3), 3))
        const orbit = new THREE.Line(og, orbitMat)
        orbit.frustumCulled = false
        const bg = new THREE.BufferGeometry()
        bg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(12 * 3), 3))
        const beams = new THREE.LineSegments(bg, beamMat)
        beams.frustumCulled = false
        satLayer.add(mesh, orbit, beams)
        sats.push({ id: s.id, name: s.name, pos, mesh, orbit, beams })
      }
      kick()
    },
    setSpeed(x) { speed = x; kick() },
    setSelection(s) { sel = s; drawCities(); kick() },
    focus(lat, lon) {
      controls.autoRotate = false
      flight = { from: camera.position.clone(), to: toVec(lat, lon, 1), t: 0 }
      kick()
    },
    dispose() {
      cancelAnimationFrame(raf)
      io.disconnect(); ro.disconnect()
      document.removeEventListener('visibilitychange', onVis)
      clearRoutes(); clearSats()
      for (const d of disposables) d.dispose()
      labels.remove()
      renderer.domElement.remove()
    },
  }
}
