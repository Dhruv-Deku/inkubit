// The opening scene: the bundled GHZ sketch lies on a desk and the pipeline replays on it. SAM 3.1's segments are
// outlined on the paper, the circuit Muse Spark reads rises off the page as solid parts whose shadows fall on their own
// ink, a noisy run fills the histogram beside it and the independent prediction caps each bar. Every position and
// number comes from /api/headline (the stored segmentation, the spec and a seeded run checked by the real verifier).
import * as THREE from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import type { HeadlineScene } from '../types'

export type Phase = 0 | 1 | 2 | 3 | 4 // paper, segmented, read, simulated, verified

export interface SceneHandle {
  dispose(): void
  replay(): void
}

const BLUE = 0x3987e5
const ORANGE = 0xd95926
const GOLD = 0xd9a441
const DESK = 0x17181b
const BG = 0x111214

// timeline, seconds
const T = { sam: 1.1, read: 3.3, sim: 6.0, verify: 9.0, outro: 17.5, loop: 18.4 }
const LIFT = 0.8 // height of the risen circuit above the paper
const BAR_SCALE = 5.4 // world units per unit probability

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const seg = (t: number, a: number, b: number) => clamp01((t - a) / (b - a))
const outCubic = (x: number) => 1 - (1 - x) ** 3
const outBack = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : 1 + 2.2 * (x - 1) ** 3 + 1.2 * (x - 1) ** 2)
const inOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2)

function phaseAt(t: number): Phase {
  if (t >= T.outro) return 0
  if (t >= T.verify) return 4
  if (t >= T.sim) return 3
  if (t >= T.read) return 2
  if (t >= T.sam) return 1
  return 0
}

function labelTexture(draw: (g: CanvasRenderingContext2D, s: number) => void, size = 256): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = c.height = size
  const g = c.getContext('2d')!
  draw(g, size)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  return tex
}

function decal(tex: THREE.Texture, w: number, h: number, y: number): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.6 }))
  m.rotation.x = -Math.PI / 2
  m.position.y = y
  return m
}

function frameShape(w: number, h: number, r: number, t: number): THREE.Shape {
  const rr = (s: THREE.Path, x: number, y: number, ww: number, hh: number, rad: number) => {
    s.moveTo(x + rad, y)
    s.lineTo(x + ww - rad, y); s.quadraticCurveTo(x + ww, y, x + ww, y + rad)
    s.lineTo(x + ww, y + hh - rad); s.quadraticCurveTo(x + ww, y + hh, x + ww - rad, y + hh)
    s.lineTo(x + rad, y + hh); s.quadraticCurveTo(x, y + hh, x, y + hh - rad)
    s.lineTo(x, y + rad); s.quadraticCurveTo(x, y, x + rad, y)
  }
  const outer = new THREE.Shape()
  rr(outer, -w / 2, -h / 2, w, h, r)
  const hole = new THREE.Path()
  rr(hole, -w / 2 + t, -h / 2 + t, w - 2 * t, h - 2 * t, Math.max(0.001, r - t))
  outer.holes.push(hole)
  return outer
}

export function mountHeroScene(host: HTMLElement, data: HeadlineScene, onPhase: (p: Phase) => void): SceneHandle {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 0.92
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFShadowMap
  renderer.setClearColor(BG)
  host.appendChild(renderer.domElement)

  const scene = new THREE.Scene()
  scene.background = new THREE.Color(BG)
  scene.fog = new THREE.Fog(BG, 24, 48)
  const pmrem = new THREE.PMREMGenerator(renderer)
  const room = new RoomEnvironment()
  const envTex = pmrem.fromScene(room, 0.04).texture
  room.dispose()
  scene.environment = envTex
  scene.environmentIntensity = 0.42

  const camera = new THREE.PerspectiveCamera(30, 2, 0.5, 120)
  const disposables: { dispose(): void }[] = [renderer, pmrem, envTex]
  const track = <X extends { dispose(): void }>(x: X): X => { disposables.push(x); return x }

  // ---- light
  scene.add(new THREE.HemisphereLight(0xdfe6f0, 0x0d0d0f, 0.4))
  const key = new THREE.DirectionalLight(0xfff4e6, 1.75)
  key.position.set(-2.5, 18, 4.5)
  key.castShadow = true
  key.shadow.mapSize.set(2048, 2048)
  key.shadow.camera.left = -11; key.shadow.camera.right = 16
  key.shadow.camera.top = 8; key.shadow.camera.bottom = -8
  key.shadow.camera.near = 4; key.shadow.camera.far = 40
  key.shadow.bias = -0.0004
  key.shadow.radius = 4
  scene.add(key)
  const rim = new THREE.DirectionalLight(0x9db8e8, 0.5)
  rim.position.set(10, 6, -12)
  scene.add(rim)

  // ---- desk and paper
  const desk = new THREE.Mesh(track(new THREE.PlaneGeometry(220, 220)), track(new THREE.MeshStandardMaterial({ color: DESK, roughness: 0.92 })))
  desk.rotation.x = -Math.PI / 2
  desk.receiveShadow = true
  scene.add(desk)

  const W = data.width / 100
  const H = data.height / 100
  const px = (x: number) => x / 100 - W / 2
  const pz = (y: number) => y / 100 - H / 2

  const paperGroup = new THREE.Group()
  paperGroup.rotation.y = 0.045
  paperGroup.position.set(-1.2, 0, 0.2)
  scene.add(paperGroup)
  const tex = track(new THREE.TextureLoader().load(data.image, () => kick()))
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy()
  const paperMats = [
    ...Array(2).fill(track(new THREE.MeshStandardMaterial({ color: 0xd8d4cc, roughness: 0.95 }))),
    track(new THREE.MeshStandardMaterial({ map: tex, roughness: 0.93, color: 0xe4e1db })),
    ...Array(3).fill(track(new THREE.MeshStandardMaterial({ color: 0xd8d4cc, roughness: 0.95 }))),
  ]
  const paper = new THREE.Mesh(track(new THREE.BoxGeometry(W, 0.03, H)), paperMats)
  paper.position.y = 0.015
  paper.receiveShadow = true
  paper.castShadow = true
  paperGroup.add(paper)
  const top = 0.031

  // ---- SAM 3.1 segments, outlined on the paper
  const frameMat = track(new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: 0, depthWrite: false }))
  const frames = data.segments.map((s) => {
    const [x0, y0, x1, y1] = s.bbox
    const w = (x1 - x0) / 100 + 0.24
    const h = (y1 - y0) / 100 + 0.24
    const m = new THREE.Mesh(track(new THREE.ShapeGeometry(frameShape(w, h, 0.12, 0.045))), frameMat.clone())
    track(m.material as THREE.Material)
    m.rotation.x = -Math.PI / 2
    m.position.set(px((x0 + x1) / 2), top + 0.002, pz((y0 + y1) / 2))
    paperGroup.add(m)
    return m
  })

  // ---- the circuit, read from the spec and placed on the drawn parts
  const centers = (concept: string) => data.segments.filter((s) => s.concept === concept)
    .map((s) => ({ x: px((s.bbox[0] + s.bbox[2]) / 2), z: pz((s.bbox[1] + s.bbox[3]) / 2), w: (s.bbox[2] - s.bbox[0]) / 100, h: (s.bbox[3] - s.bbox[1]) / 100 }))
  const meters = centers('meter').sort((a, b) => a.z - b.z)
  const boxes = centers('gate box')
  const dots = centers('dot')
  const circles = centers('circle')
  const wireZ = meters.map((m) => m.z)
  const wireX0 = px(200)

  const metal = track(new THREE.MeshStandardMaterial({ color: 0x3d4048, metalness: 0.6, roughness: 0.34 }))
  const ceramic = track(new THREE.MeshStandardMaterial({ color: 0x2b2d33, roughness: 0.38, metalness: 0.15 }))
  const blueMat = track(new THREE.MeshStandardMaterial({ color: BLUE, roughness: 0.42, metalness: 0.05 }))
  const meterMat = track(new THREE.MeshStandardMaterial({ color: 0x2b2d33, roughness: 0.55, metalness: 0.1 }))

  const circuit = new THREE.Group()
  circuit.position.y = top
  paperGroup.add(circuit)

  type Part = { obj: THREE.Object3D; at: number; kind: 'rise' | 'wire' }
  const parts: Part[] = []
  const shadowy = (o: THREE.Object3D) => { o.traverse((c) => { if ((c as THREE.Mesh).isMesh) { c.castShadow = true; c.receiveShadow = true } }); return o }

  wireZ.forEach((z, i) => {
    const len = meters[i].x - meters[i].w / 2 - wireX0
    const g = track(new THREE.CylinderGeometry(0.036, 0.036, len, 14))
    g.rotateZ(-Math.PI / 2)
    g.translate(len / 2, 0, 0)
    const m = shadowy(new THREE.Mesh(g, metal))
    m.position.set(wireX0, LIFT, z)
    circuit.add(m)
    parts.push({ obj: m, at: T.read + i * 0.12, kind: 'wire' })
  })

  const hTex = track(labelTexture((g, s) => {
    g.fillStyle = '#fff'
    g.font = `600 ${s * 0.62}px Inter, "Segoe UI", system-ui, sans-serif`
    g.textAlign = 'center'; g.textBaseline = 'middle'
    g.fillText('H', s / 2, s / 2 + s * 0.03)
  }))
  boxes.forEach((b, i) => {
    const grp = new THREE.Group()
    const size = Math.min(b.w, b.h) * 0.98
    grp.add(new THREE.Mesh(track(new RoundedBoxGeometry(size, 0.42, size, 4, 0.09)), blueMat))
    const d = decal(hTex, size * 0.72, size * 0.72, 0.212)
    track(d.geometry); track(d.material as THREE.Material)
    grp.add(d)
    shadowy(grp)
    d.castShadow = false
    grp.position.set(b.x, LIFT, b.z)
    circuit.add(grp)
    parts.push({ obj: grp, at: T.read + 0.5 + i * 0.1, kind: 'rise' })
  })

  dots.forEach((d, i) => {
    const target = circles.reduce((best, c) => (Math.abs(c.x - d.x) < Math.abs(best.x - d.x) ? c : best), circles[0])
    const grp = new THREE.Group()
    const ctl = new THREE.Mesh(track(new THREE.SphereGeometry(0.17, 32, 16)), ceramic)
    grp.add(ctl)
    const dz = target.z - d.z
    const post = new THREE.Mesh(track(new THREE.CylinderGeometry(0.034, 0.034, Math.abs(dz), 12)), ceramic)
    post.rotation.x = Math.PI / 2
    post.position.z = dz / 2
    grp.add(post)
    const ring = new THREE.Mesh(track(new THREE.TorusGeometry(0.36, 0.045, 14, 56)), ceramic)
    ring.rotation.x = Math.PI / 2
    ring.position.z = dz
    grp.add(ring)
    const barGeo = track(new THREE.BoxGeometry(0.72, 0.07, 0.07))
    const a = new THREE.Mesh(barGeo, ceramic); a.position.z = dz
    const b = new THREE.Mesh(barGeo, ceramic); b.position.z = dz; b.rotation.y = Math.PI / 2
    grp.add(a, b)
    shadowy(grp)
    grp.position.set(d.x, LIFT, d.z)
    circuit.add(grp)
    parts.push({ obj: grp, at: T.read + 0.85 + i * 0.3, kind: 'rise' })
  })

  const meterTex = track(labelTexture((g, s) => {
    g.strokeStyle = '#e9e7e2'; g.lineWidth = s * 0.05; g.lineCap = 'round'
    g.beginPath(); g.arc(s / 2, s * 0.68, s * 0.3, Math.PI * 1.08, Math.PI * 1.92); g.stroke()
    g.beginPath(); g.moveTo(s / 2, s * 0.68); g.lineTo(s * 0.7, s * 0.36); g.stroke()
  }))
  meters.forEach((m, i) => {
    const grp = new THREE.Group()
    grp.add(new THREE.Mesh(track(new RoundedBoxGeometry(m.w, 0.38, m.h, 4, 0.08)), meterMat))
    const d = decal(meterTex, Math.min(m.w, m.h) * 0.9, Math.min(m.w, m.h) * 0.9, 0.192)
    track(d.geometry); track(d.material as THREE.Material)
    grp.add(d)
    shadowy(grp)
    d.castShadow = false
    grp.position.set(m.x, LIFT, m.z)
    circuit.add(grp)
    parts.push({ obj: grp, at: T.read + 1.5 + i * 0.1, kind: 'rise' })
  })

  // ---- the noisy run: a bead per wire, then the entanglement the meters share (gold is kept for entanglement)
  const beads = wireZ.map((z) => {
    const b = new THREE.Mesh(track(new THREE.SphereGeometry(0.12, 20, 12)), blueMat)
    b.castShadow = true
    b.position.set(wireX0, LIFT, z)
    b.visible = false
    circuit.add(b)
    return b
  })
  const goldMat = track(new THREE.MeshStandardMaterial({ color: GOLD, metalness: 1, roughness: 0.28 }))
  const threads: THREE.Mesh<THREE.TubeGeometry, THREE.Material>[] = []
  const arc = (a: { x: number; z: number }, b: { x: number; z: number }, lift: number, out: number) => new THREE.CatmullRomCurve3([
    new THREE.Vector3(a.x + 0.25, LIFT + 0.2, a.z),
    new THREE.Vector3((a.x + b.x) / 2 + out, LIFT + lift, (a.z + b.z) / 2),
    new THREE.Vector3(b.x + 0.25, LIFT + 0.2, b.z),
  ])
  const links: [number, number, number, number][] = [[0, 1, 0.75, 0.55], [1, 2, 0.75, 0.55], [0, 2, 1.25, 1.05]]
  for (const [i, j, lift, out] of links) {
    if (!meters[i] || !meters[j]) continue
    const tube = new THREE.Mesh(track(new THREE.TubeGeometry(arc(meters[i], meters[j], lift, out), 96, 0.032, 10)), goldMat)
    tube.castShadow = true
    tube.geometry.setDrawRange(0, 0)
    circuit.add(tube)
    threads.push(tube)
  }

  // ---- histogram beside the paper: measured shots (blue) capped by the independent prediction (orange)
  const hist = new THREE.Group()
  hist.position.set(W / 2 - 2.1, 0, -H / 2 - 1.15)
  hist.rotation.y = -0.12
  scene.add(hist)
  const n = data.outcomes.length
  const pitch = 0.54
  const span = n * pitch
  const plinth = new THREE.Mesh(track(new RoundedBoxGeometry(span + 0.5, 0.12, 1.5, 3, 0.05)), track(new THREE.MeshStandardMaterial({ color: 0x24262b, roughness: 0.7 })))
  plinth.position.set(span / 2, 0.06, 0)
  plinth.receiveShadow = true
  plinth.castShadow = true
  hist.add(plinth)
  const barGeo = track(new THREE.BoxGeometry(0.38, 1, 0.46))
  barGeo.translate(0, 0.5, 0)
  const capGeo = track(new THREE.BoxGeometry(0.46, 0.028, 0.54))
  const capMat = track(new THREE.MeshStandardMaterial({ color: ORANGE, roughness: 0.45 }))
  const bars = data.outcomes.map((o, i) => {
    const bar = new THREE.Mesh(barGeo, blueMat)
    bar.position.set(pitch * (i + 0.5), 0.12, 0)
    bar.scale.y = 0.0001
    bar.castShadow = true
    bar.receiveShadow = true
    const cap = new THREE.Mesh(capGeo, capMat)
    cap.position.set(bar.position.x, 0.12 + Math.max(o.predicted * BAR_SCALE, 0.03), 0)
    cap.scale.setScalar(0.0001)
    cap.castShadow = true
    hist.add(bar, cap)
    return { bar, cap, h: Math.max(o.measured * BAR_SCALE, 0.02) }
  })
  const keyLabel = (txt: string) => track(labelTexture((g, s) => {
    g.fillStyle = '#a9abb2'
    g.font = `500 ${s * 0.32}px "JetBrains Mono", Consolas, monospace`
    g.textAlign = 'center'; g.textBaseline = 'middle'
    g.fillText(txt, s / 2, s / 2)
  }))
  data.outcomes.forEach((o, i) => {
    if (o.measured < 0.2) return // only the outcomes that matter carry a label
    const l = decal(keyLabel(o.key), 1.1, 1.1, 0.125)
    track(l.geometry); track(l.material as THREE.Material)
    l.position.set(bars[i].bar.position.x, 0.125, 0.52)
    hist.add(l)
  })

  // ---- camera: lens shift keeps the scene right of the copy on wide screens
  const target = new THREE.Vector3(1.6, 0.5, 0.2)
  let width = 1, height = 1
  const resize = () => {
    width = Math.max(1, host.clientWidth)
    height = Math.max(1, host.clientHeight)
    renderer.setSize(width, height, false)
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    camera.aspect = width / height
    const shift = width > 900 ? width * (width < 1400 ? 0.225 : 0.19) : 0
    if (shift) camera.setViewOffset(width + 2 * shift, height, 0, 0, width, height)
    else camera.clearViewOffset()
    camera.updateProjectionMatrix()
  }
  const pointer = { x: 0, y: 0, sx: 0, sy: 0 }
  const onMove = (e: PointerEvent) => {
    const r = host.getBoundingClientRect()
    pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1
    pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1
  }
  host.addEventListener('pointermove', onMove)

  const placeCamera = (t: number) => {
    const intro = outCubic(seg(t, 0, 2.0))
    const narrow = width <= 900
    const fit = 2.37 / camera.aspect // the layout was framed at 2.37:1; narrower stages pull the camera back to fit
    const dist = (narrow ? Math.max(17, 19 * fit) : 27 * Math.max(1, fit) ** 2) + (1 - intro) * 4
    target.x = narrow ? 0.2 : 1.6 // without the lens shift the scene is centred on the stage
    const elev = THREE.MathUtils.degToRad(40 + (1 - intro) * 9 - pointer.sy * 2.5)
    const azim = THREE.MathUtils.degToRad(-10 + Math.sin(t * 0.21) * 1.6 + pointer.sx * 4)
    camera.position.set(
      target.x + dist * Math.cos(elev) * Math.sin(azim),
      target.y + dist * Math.sin(elev),
      target.z + dist * Math.cos(elev) * Math.cos(azim),
    )
    camera.lookAt(target)
  }

  // ---- everything is a function of time, so a replay or a still frame is just another t
  let phase: Phase | -1 = -1
  const apply = (t: number) => {
    const out = 1 - inOut(seg(t, T.outro, T.outro + 0.8))
    frames.forEach((f, i) => {
      const k = outCubic(seg(t, T.sam + i * 0.17, T.sam + i * 0.17 + 0.35))
      const fade = 1 - 0.85 * seg(t, T.read + 1.2, T.read + 2.2)
      ;(f.material as THREE.MeshBasicMaterial).opacity = 0.95 * k * fade * out
      f.scale.setScalar(1.18 - 0.18 * k)
    })
    for (const p of parts) {
      if (p.kind === 'wire') {
        p.obj.scale.x = Math.max(0.0001, outCubic(seg(t, p.at, p.at + 0.9)) * out)
        p.obj.visible = t > p.at
      } else {
        const k = outBack(seg(t, p.at, p.at + 0.65))
        const s = Math.max(0.0001, Math.min(k, 1.06) * out)
        p.obj.scale.setScalar(s)
        p.obj.position.y = LIFT * Math.min(1, k) * out
        p.obj.visible = t > p.at
      }
    }
    beads.forEach((b, i) => {
      const k = seg(t, T.sim + i * 0.15, T.sim + 1.6 + i * 0.15)
      b.visible = k > 0 && k < 1
      b.position.x = wireX0 + inOut(k) * (meters[i].x - meters[i].w / 2 - wireX0)
    })
    threads.forEach((th, i) => {
      const k = inOut(seg(t, T.sim + 1.5 + i * 0.25, T.sim + 2.4 + i * 0.25)) * out
      const count = th.geometry.index ? th.geometry.index.count : 0
      th.geometry.setDrawRange(0, Math.floor((count * k) / 6) * 6)
    })
    bars.forEach((b, i) => {
      const k = outCubic(seg(t, T.sim + 1.7 + i * 0.06, T.sim + 2.7 + i * 0.06)) * out
      b.bar.scale.y = Math.max(0.0001, b.h * k)
      const c = outBack(seg(t, T.verify - 0.6 + i * 0.05, T.verify - 0.1 + i * 0.05)) * out
      b.cap.scale.setScalar(Math.max(0.0001, c))
    })
    placeCamera(t)
    const p = phaseAt(t)
    if (p !== phase) { phase = p; onPhase(p) }
  }

  // ---- loop: runs only while the hero is on screen and the tab is visible
  let t = reduced ? T.verify + 1 : 0
  let raf = 0
  let last = 0
  let onScreen = true
  const frame = (now: number) => {
    raf = 0
    const dt = last ? Math.min(0.1, (now - last) / 1000) : 0
    last = now
    if (!reduced) {
      t += dt
      if (t >= T.loop) t = 0.6
    }
    pointer.sx += (pointer.x - pointer.sx) * Math.min(1, dt * 3)
    pointer.sy += (pointer.y - pointer.sy) * Math.min(1, dt * 3)
    apply(t)
    renderer.render(scene, camera)
    if (onScreen && !document.hidden && !reduced) raf = requestAnimationFrame(frame)
  }
  const kick = () => { if (!raf) { last = 0; raf = requestAnimationFrame(frame) } }
  const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; if (onScreen) kick() }, { threshold: 0.05 })
  io.observe(host)
  const onVis = () => { if (!document.hidden) kick() }
  document.addEventListener('visibilitychange', onVis)
  const ro = new ResizeObserver(() => { resize(); kick() })
  ro.observe(host)
  resize()
  kick()

  return {
    replay() { t = reduced ? T.verify + 1 : 0; kick() },
    dispose() {
      cancelAnimationFrame(raf)
      io.disconnect(); ro.disconnect()
      document.removeEventListener('visibilitychange', onVis)
      host.removeEventListener('pointermove', onMove)
      for (const d of disposables) d.dispose()
      renderer.domElement.remove()
    },
  }
}
