import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { CircuitSpec, LiveRead } from '../types'
import { CallBadge } from './CallBadge'

const TICK_MS = 500
const CHANGED = 10 // mean grey-level difference (0-255) from the last read frame that counts as a new drawing
const STILL = 3.5 // difference between consecutive frames below which the picture is still
const STILL_TICKS = 3 // still for this many ticks (1.5 s) before reading

type Phase = 'off' | 'watching' | 'settling' | 'reading'

function grab(video: HTMLVideoElement, small: HTMLCanvasElement): Uint8ClampedArray | null {
  if (!video.videoWidth) return null
  const ctx = small.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(video, 0, 0, small.width, small.height)
  const d = ctx.getImageData(0, 0, small.width, small.height).data
  const g = new Uint8ClampedArray(small.width * small.height)
  for (let i = 0; i < g.length; i++) g[i] = (d[4 * i] * 3 + d[4 * i + 1] * 6 + d[4 * i + 2]) / 10
  return g
}
const diff = (a: Uint8ClampedArray, b: Uint8ClampedArray) => { let s = 0; for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]); return s / a.length }

/** The read frame with SAM's boxes and each qubit's odds pinned to its wire. */
function Annotated({ url, read }: { url: string; read: LiveRead }) {
  const a = read.analysis, r = read.result
  const fs = Math.max(12, a.width / 55)
  return (
    <div className="live-shot">
      <img src={url} alt="The frame that was read" />
      <svg viewBox={`0 0 ${a.width} ${a.height}`} preserveAspectRatio="none" aria-hidden>
        {a.overlay.map((b) => (
          <rect key={b.segment_id} x={b.bbox[0]} y={b.bbox[1]} width={b.bbox[2] - b.bbox[0]} height={b.bbox[3] - b.bbox[1]}
            fill="none" stroke={b.linked_to ? '#3987e5' : '#a9abb2'} strokeWidth={Math.max(2, a.width / 400)} rx={4} />
        ))}
        {r.wires.map((w) => {
          const p1 = r.p1_ideal?.[w.qubit], pn = r.p1_noisy?.[w.qubit]
          if (p1 === undefined) return null
          const tw = fs * 10.5
          const x = Math.min(w.x_right + fs * 0.6, a.width - tw - fs * 0.3)
          return (
            <g key={w.qubit}>
              <line x1={w.x_end} x2={x} y1={w.y} y2={w.y} stroke="#d9a441" strokeWidth={Math.max(1, a.width / 900)} strokeDasharray="4 4" />
              <rect x={x} y={w.y - fs * 0.95} width={tw} height={fs * 1.9} rx={fs * 0.4} fill="#1b1c20" fillOpacity={0.94} stroke="#d9a441" strokeWidth={Math.max(1.5, a.width / 600)} />
              <text x={x + fs * 0.5} y={w.y + fs * 0.35} fontSize={fs} fill="#ecebe8" fontFamily="JetBrains Mono, monospace">
                q{w.qubit} 1: {(p1 * 100).toFixed(0)}%{pn !== undefined ? ` · ${(pn * 100).toFixed(0)}%` : ''}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/** Live board: point a camera at a whiteboard; when the drawing changes and holds still, Inkubit reads it with
 *  SAM 3.1 and Muse Spark, simulates it exactly and pins the odds to the wires. */
export function LiveBoardPanel({ live, onOpen }: { live: boolean; onOpen?: (s: CircuitSpec) => void }) {
  const video = useRef<HTMLVideoElement | null>(null)
  const small = useRef<HTMLCanvasElement | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const lastRead = useRef<Uint8ClampedArray | null>(null)
  const prev = useRef<Uint8ClampedArray | null>(null)
  const still = useRef(0)
  const busy = useRef(false)
  const [phase, setPhase] = useState<Phase>('off')
  const [change, setChange] = useState(0)
  const [read, setRead] = useState<{ url: string; data: LiveRead; at: number } | null>(null)
  const [reads, setReads] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())

  const stop = () => {
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    setPhase('off')
  }
  useEffect(() => () => stream.current?.getTracks().forEach((t) => t.stop()), [])

  const send = async () => {
    const v = video.current
    if (!v || busy.current || !v.videoWidth) return
    busy.current = true
    setPhase('reading')
    const c = document.createElement('canvas')
    const scale = Math.min(1, 1600 / v.videoWidth)
    c.width = Math.round(v.videoWidth * scale); c.height = Math.round(v.videoHeight * scale)
    c.getContext('2d')!.drawImage(v, 0, 0, c.width, c.height)
    const blob: Blob = await new Promise((res) => c.toBlob((b) => res(b!), 'image/jpeg', 0.9))
    lastRead.current = small.current ? grab(v, small.current) : null
    try {
      const data = await api.liveRead(blob)
      setRead((old) => { if (old) URL.revokeObjectURL(old.url); return { url: URL.createObjectURL(blob), data, at: Date.now() } })
      setReads((n) => n + 1)
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The frame could not be read.')
    } finally {
      busy.current = false
      setPhase(stream.current ? 'watching' : 'off')
    }
  }

  useEffect(() => {
    if (phase === 'off') return
    const id = window.setInterval(() => {
      setNow(Date.now())
      const v = video.current, s = small.current
      if (!v || !s || busy.current) return
      const g = grab(v, s)
      if (!g) return
      const moving = prev.current ? diff(g, prev.current) : 99
      prev.current = g
      const changed = lastRead.current ? diff(g, lastRead.current) : 99
      setChange(changed)
      if (changed < CHANGED) { still.current = 0; setPhase('watching'); return }
      if (moving < STILL) {
        still.current += 1
        setPhase('settling')
        if (still.current >= STILL_TICKS) { still.current = 0; void send() }
      } else {
        still.current = 0
        setPhase('watching')
      }
    }, TICK_MS)
    return () => window.clearInterval(id)
  }, [phase === 'off']) // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) { setError('This browser cannot open a camera (it needs https or localhost).'); return }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } } })
      stream.current = s
      if (video.current) { video.current.srcObject = s; await video.current.play() }
      lastRead.current = null; prev.current = null; still.current = 0
      setPhase('watching')
    } catch (e) {
      setError(e instanceof Error ? `The camera did not open: ${e.message}` : 'The camera did not open.')
    }
  }

  const r = read?.data.result
  const ago = read ? Math.round((now - read.at) / 1000) : 0
  const status = phase === 'off' ? 'camera off'
    : phase === 'reading' ? 'reading the board: SAM 3.1 finds the parts, Muse Spark reads them, then exact simulation…'
      : phase === 'settling' ? 'the drawing changed: waiting for it to hold still…'
        : read ? `watching for changes · last read ${ago} s ago` : 'watching: draw a circuit, or point at one'
  return (
    <div className="panel liveboard">
      <div className="panel-head">
        <h2>Live board</h2>
        <span className="sub">point a camera at a whiteboard: when the drawing changes and holds still it is read, simulated and the odds appear on the wires</span>
      </div>
      <div className="row wrap" style={{ gap: 8 }}>
        {phase === 'off'
          ? <button className="btn primary" onClick={() => { void start() }}>Start the camera</button>
          : <button className="btn" onClick={stop}>Stop</button>}
        <button className="btn" onClick={() => { void send() }} disabled={phase === 'off' || phase === 'reading'}>Read now</button>
        <span className={`live-status ${phase}`} aria-live="polite">{status}</span>
        {phase !== 'off' && <span className="sub mono">change {change.toFixed(1)}</span>}
      </div>
      {!live && <p className="sub" style={{ margin: '8px 0 0' }}>Offline only the sample sketches can be read; with the Meta key any drawing works.</p>}
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      <div className="live-grid">
        <div className="live-cam" style={{ display: phase === 'off' ? 'none' : 'block' }}>
          <video ref={video} muted playsInline aria-label="Camera" />
          <canvas ref={small} width={80} height={60} hidden />
        </div>
        {read && r && (
          <div>
            <Annotated url={read.url} read={read.data} />
            <div className="mini-tiles">
              <span><b>{read.data.read_seconds.toFixed(1)} s</b> to read (SAM 3.1 + Muse Spark)</span>
              <span><b>{reads}</b> read{reads === 1 ? '' : 's'}</span>
              {r.qubits !== undefined && <span><b>{r.qubits}</b> qubits, <b>{r.gates}</b> gates</span>}
            </div>
            {r.error && <div className="notice" style={{ marginTop: 8 }}>{r.error}</div>}
            {r.ideal && (
              <div className="live-odds">
                {Object.entries(r.ideal).slice(0, 6).map(([k, p]) => (
                  <div key={k} className="disc-bar-row">
                    <span className="mono">{k}</span>
                    <span className="disc-bar-track"><span className="disc-bar found" style={{ width: `${p * 100}%` }} /></span>
                    <span className="mono disc-bar-val">{(p * 100).toFixed(1)}%{r.noisy ? ` · ${((r.noisy[k] ?? 0) * 100).toFixed(1)}%` : ''}</span>
                  </div>
                ))}
                <div className="sub">outcome odds: perfect qubits · realistic noise (exact simulation)</div>
              </div>
            )}
            {r.network && <div className="mini-tiles"><span><b>{r.network.pairs_per_second.toPrecision(3)}</b> pairs/s</span><span><b>{r.network.fidelity.toFixed(3)}</b> fidelity</span><span><b>{r.network.key_bits_per_second.toPrecision(3)}</b> key bits/s</span></div>}
            <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
              {read.data.analysis.calls.map((c, i) => <CallBadge key={i} call={c} />)}
              {onOpen && read.data.analysis.valid && read.data.analysis.spec.kind === 'circuit' &&
                <button className="btn small" onClick={() => onOpen(read.data.analysis.spec as unknown as CircuitSpec)}>Open in the editor</button>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
