import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { ModelCall } from '../types'
import { CallBadge } from './CallBadge'
import type { EarthCity, EarthHandle, EarthRoute, Pick, SkySat } from './EarthScene'
import { VoiceButton } from './VoiceButton'

type Kind = 'fiber' | 'repeaters' | 'satellite'
export interface QRoute { a: string; b: string; kind: Kind; repeaters: number; satellite: string | null; memory_ms?: number }
export interface QEvalRoute extends QRoute {
  distance_km: number; path: [number, number][]; repeater_points?: [number, number][]; key_rate_bps: number; bits_per_day: number
  bits_tonight?: number | null; limit: string; loss_db?: number; fidelity?: number; qber?: number; span_km?: number
  passes_a?: number; passes_b?: number; satellite_name?: string; error?: string
}
export interface QEval { by: string; rationale: string; routes: QEvalRoute[]; score_bps: number; weakest: { a: string; b: string } }
interface QStep { id: string; label: string; by: string; status: string; detail: string }
export interface QPlanView {
  id: string; status: 'running' | 'done' | 'failed'; error: string | null; steps: QStep[]
  result: { request: string; first?: QEval; second?: QEval; best?: QEval; verdict?: { winner: 'first' | 'second'; text: string }; calls?: ModelCall[]; offline?: boolean }
}

const SAMPLES = ['Connect Delhi, Mumbai and London', 'A quantum-safe link from London to New York',
  'Secure Tokyo, Seoul and Shanghai', 'Link Geneva, Zurich and Munich', 'Sydney to Singapore to Delhi']
const START: QRoute[] = [
  { a: 'london', b: 'paris', kind: 'fiber', repeaters: 0, satellite: null },
  { a: 'london', b: 'new_york', kind: 'satellite', repeaters: 0, satellite: 'speqtre' },
  { a: 'delhi', b: 'london', kind: 'satellite', repeaters: 0, satellite: 'speqtre' },
]
const SPEEDS = [1, 60, 600]
const NONE: QEvalRoute[] = []
const TODAY_MS = 10

export function fmtRate(bps: number): string {
  if (!(bps > 0)) return 'no key'
  if (bps >= 1000) return `${(bps / 1000).toFixed(1)} kbit/s`
  if (bps >= 1) return `${bps.toFixed(1)} bit/s`
  return `${Math.round(bps * 86400).toLocaleString('en-US')} bits/day`
}
const KIND: Record<Kind, string> = { fiber: 'fiber', repeaters: 'repeaters', satellite: 'satellite' }
const msLabel = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10000 ? 0 : 1)} s` : `${ms.toFixed(ms < 10 ? 1 : 0)} ms`

function webglOk(): boolean {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')) } catch { return false }
}

export function QuantumEarthPanel({ live }: { live: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const scene = useRef<EarthHandle | null>(null)
  const [cities, setCities] = useState<EarthCity[]>([])
  const [design, setDesign] = useState<QRoute[]>(START)
  const [evalr, setEvalr] = useState<QEval | null>(null)
  const [busyEval, setBusyEval] = useState(false)
  const [plan, setPlan] = useState<QPlanView | null>(null)
  const [showing, setShowing] = useState<'yours' | 'first' | 'second' | 'best'>('yours')
  const [request, setRequest] = useState('')
  const [selRoute, setSelRoute] = useState<number | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [speed, setSpeed] = useState(60)
  const [hover, setHover] = useState<{ text: string; x: number; y: number } | null>(null)
  const [simTime, setSimTime] = useState(Date.now())
  const [error, setError] = useState<string | null>(null)
  const [noGl, setNoGl] = useState(false)
  const [ready, setReady] = useState(false)
  const evalSeq = useRef(0)
  const alive = useRef(true)

  const byId = useMemo(() => Object.fromEntries(cities.map((c) => [c.id, c])), [cities])
  const name = useCallback((id: string) => (byId[id]?.name ?? id).replace(/ \(.*\)$/, ''), [byId])

  // the routes on the globe come from whichever design is shown
  const shown: QEval | null = showing === 'yours' ? evalr : plan?.result[showing] ?? evalr
  const routes: QEvalRoute[] = useMemo(() => shown?.routes ?? NONE, [shown])

  const evaluate = useCallback(async (d: QRoute[]) => {
    const seq = ++evalSeq.current
    setBusyEval(true)
    try {
      const r = await api.qnetEvaluate(d) as QEval
      if (seq === evalSeq.current && alive.current) { setEvalr(r); setError(null) }
    } catch (e) {
      if (seq === evalSeq.current) setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      if (seq === evalSeq.current && alive.current) setBusyEval(false)
    }
  }, [])

  // mount the scene once
  useEffect(() => {
    alive.current = true
    if (!webglOk()) { setNoGl(true); return }
    let disposed = false
    import('./EarthScene').then(({ mountEarth }) => {
      if (disposed || !host.current) return
      scene.current = mountEarth(host.current, {
        onPick: (p: Pick) => pickRef.current(p),
        onHover: (text, x, y) => setHover(text ? { text, x, y } : null),
        onTime: (ms) => { timeRef.current = ms },
      })
      setReady(true)
      api.qnetCities().then((r) => { if (!disposed) { setCities(r.cities); scene.current?.setCities(r.cities) } }).catch(() => {})
      api.qnetSky().then((s) => { if (!disposed) scene.current?.setSky(Date.parse(s.start_utc), s.step_s, s.satellites as SkySat[]) }).catch(() => {})
    }).catch(() => setNoGl(true))
    void evaluate(START)
    const tick = window.setInterval(() => setSimTime(timeRef.current), 500)
    return () => { disposed = true; alive.current = false; window.clearInterval(tick); scene.current?.dispose(); scene.current = null }
  }, [evaluate])
  const timeRef = useRef(Date.now())

  // push routes and selection to the scene
  useEffect(() => {
    const er: EarthRoute[] = routes.map((r, i) => ({ key: String(i), a: r.a, b: r.b, kind: r.kind, satellite: r.satellite, path: r.path,
      repeater_points: r.repeater_points, key_rate_bps: r.key_rate_bps }))
    scene.current?.setRoutes(er)
  }, [routes, ready])
  useEffect(() => {
    const r = selRoute !== null ? routes[selRoute] : null
    scene.current?.setSelection({ route: selRoute !== null ? String(selRoute) : null, city: null, pending })
    void r
  }, [selRoute, pending, routes, ready])
  useEffect(() => { scene.current?.setSpeed(speed) }, [speed, ready])

  // edits always act on a copy you own
  const edit = (next: QRoute[]) => {
    setDesign(next)
    setShowing('yours')
    void evaluate(next)
  }
  const current: QRoute[] = showing === 'yours' ? design
    : (shown?.routes ?? []).map((r) => ({ a: r.a, b: r.b, kind: r.kind, repeaters: r.repeaters, satellite: r.satellite, memory_ms: r.memory_ms ?? TODAY_MS }))

  const pickRef = useRef<(p: Pick) => void>(() => {})
  pickRef.current = (p: Pick) => {
    if (p.type === 'route') { setSelRoute(Number(p.key)); return }
    if (p.type === 'city') {
      if (adding) {
        if (!pending) { setPending(p.id); return }
        if (pending !== p.id) {
          const next = [...current, { a: pending, b: p.id, kind: 'satellite' as Kind, repeaters: 0, satellite: 'speqtre', memory_ms: TODAY_MS }]
          edit(next)
          setSelRoute(next.length - 1)
        }
        setPending(null); setAdding(false)
        return
      }
      const i = routes.findIndex((r) => r.a === p.id || r.b === p.id)
      setSelRoute(i >= 0 ? i : null)
      const c = byId[p.id]
      if (c) scene.current?.focus(c.lat, c.lon)
      return
    }
    setSelRoute(null)
  }

  const runPlan = async (text: string) => {
    const req = text.trim()
    if (!req) return
    setError(null); setPlan(null); setSelRoute(null)
    try {
      const { plan_id } = await api.qnetPlan(req)
      for (;;) {
        const v = await api.qnetPlanStatus(plan_id) as QPlanView
        if (!alive.current) return
        setPlan(v)
        if (v.result.second) setShowing('second')
        else if (v.result.first) setShowing('first')
        if (v.status !== 'running') {
          if (v.status === 'failed') setError(v.error ?? 'the plan failed')
          else {
            const pick = v.result.verdict?.winner === 'second' && v.result.second ? 'second' : 'first'
            setShowing(pick)
            const w = v.result[pick]
            const c = w ? byId[w.weakest.a] : null
            if (c) scene.current?.focus(c.lat, c.lon)
          }
          break
        }
        await new Promise((r) => setTimeout(r, 900))
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    }
  }

  const sel = selRoute !== null ? routes[selRoute] : null
  const selEdit = selRoute !== null ? current[selRoute] : null
  const setSel = (patch: Partial<QRoute>) => {
    if (selRoute === null || !selEdit) return
    const next = current.map((r, i) => (i === selRoute ? { ...r, ...patch } : r))
    edit(next)
  }
  const running = plan?.status === 'running'
  const designs: { key: 'yours' | 'first' | 'second' | 'best'; label: string; ev: QEval | null | undefined }[] = [
    { key: 'first', label: 'Muse Spark', ev: plan?.result.first }, { key: 'second', label: 'Muse Wonder', ev: plan?.result.second },
    { key: 'best', label: 'Best possible', ev: plan?.result.best }, { key: 'yours', label: 'Yours', ev: evalr },
  ]
  const clock = new Date(simTime).toISOString().slice(11, 16)

  return (
    <div className="panel qearth">
      <div className="panel-head"><h2>Quantum internet</h2><span className="sub">a key network on the real Earth: AI designs, physics decides</span></div>
      <div className="qe-stage">
        <div className="qe-globe" ref={host}>
          {noGl && <p className="qe-nogl">This view needs WebGL. The satellite planner below shows the same orbits in 2D.</p>}
          {hover && <div className="qe-tip" style={{ transform: `translate(${hover.x + 14}px, ${hover.y + 12}px)` }}>
            {/^\d+$/.test(hover.text) && routes[Number(hover.text)]
              ? (() => { const r = routes[Number(hover.text)]; return <><b>{name(r.a)}–{name(r.b)}</b> · {KIND[r.kind]} · {fmtRate(r.key_rate_bps)}</> })()
              : hover.text}
          </div>}
        </div>

        <aside className="qe-left">
          <form onSubmit={(e) => { e.preventDefault(); void runPlan(request) }}>
            <label className="label" htmlFor="qe-ask">Ask for a network</label>
            <div className="qe-ask">
              <input id="qe-ask" type="text" value={request} onChange={(e) => setRequest(e.target.value)}
                placeholder="Connect Delhi, Mumbai and London" disabled={running} />
              <VoiceButton live={live} disabled={running} onText={setRequest} onDone={(t) => { setRequest(t); void runPlan(t) }} />
              <button className="btn primary" disabled={running || !request.trim()}>{running ? 'Planning…' : 'Plan it'}</button>
            </div>
          </form>
          <div className="qe-samples">
            {SAMPLES.map((s) => <button key={s} className="linkish" disabled={running} onClick={() => { setRequest(s); void runPlan(s) }}>{s}</button>)}
          </div>
          {plan && (
            <ol className="qe-steps">
              {plan.steps.map((s) => (
                <li key={s.id} className={`s-${s.status}`}>
                  <span className="qe-who">{s.by}</span>
                  <b>{s.label}</b>
                  {s.detail && <p>{s.detail}</p>}
                </li>
              ))}
            </ol>
          )}
          {plan?.result.calls && <div className="qe-calls">{plan.result.calls.map((c, i) => <CallBadge key={i} call={c} />)}</div>}
          {error && <div className="notice error">{error}</div>}
        </aside>

        <aside className="qe-right">
          <div className="seg qe-designs">
            {designs.filter((d) => d.ev).map((d) => (
              <button key={d.key} className={showing === d.key ? 'on' : ''} onClick={() => { setShowing(d.key); setSelRoute(null) }}
                title={d.ev ? `weakest pair: ${fmtRate(d.ev.score_bps)}` : ''}>
                {d.label}<small>{fmtRate(d.ev!.score_bps)}</small>
              </button>
            ))}
          </div>
          {sel && selEdit ? (
            <div className="qe-route">
              <div className="qe-route-head">
                <b>{name(sel.a)} – {name(sel.b)}</b>
                <span className="sub">{Math.round(sel.distance_km).toLocaleString('en-US')} km</span>
                <button className="icon-btn" onClick={() => setSelRoute(null)} aria-label="Close">×</button>
              </div>
              <div className="qe-rate" style={{ color: sel.key_rate_bps > 0 ? undefined : 'var(--fail)' }}>{fmtRate(sel.key_rate_bps)}</div>
              {sel.key_rate_bps > 0 && <div className="sub">{Math.round(sel.bits_per_day).toLocaleString('en-US')} secret bits a day</div>}
              <p className="qe-limit">{sel.limit}</p>
              <div className="seg">
                {(['fiber', 'repeaters', 'satellite'] as Kind[]).map((k) => (
                  <button key={k} className={selEdit.kind === k ? 'on' : ''} disabled={busyEval}
                    onClick={() => setSel({ kind: k, repeaters: k === 'repeaters' ? Math.max(1, selEdit.repeaters || 3) : 0,
                      satellite: k === 'satellite' ? selEdit.satellite ?? 'speqtre' : null })}>{KIND[k]}</button>
                ))}
              </div>
              {selEdit.kind === 'repeaters' && <>
                <label className="qe-slider"><span>{selEdit.repeaters} repeater{selEdit.repeaters > 1 ? 's' : ''}</span>
                  <input type="range" min={1} max={12} value={selEdit.repeaters} onChange={(e) => setSel({ repeaters: Number(e.target.value) })} /></label>
                <label className="qe-slider"><span>memories hold {msLabel(selEdit.memory_ms ?? TODAY_MS)}{(selEdit.memory_ms ?? TODAY_MS) === TODAY_MS ? ' (today)' : ''}</span>
                  <input type="range" min={0} max={5} step={0.05} value={Math.log10(selEdit.memory_ms ?? TODAY_MS)}
                    onChange={(e) => setSel({ memory_ms: Math.round(10 ** Number(e.target.value) * 10) / 10 })} /></label>
              </>}
              {selEdit.kind === 'satellite' && (
                <div className="seg">
                  {[['speqtre', 'SpeQtre'], ['qube2', 'QUBE-II']].map(([id, label]) => (
                    <button key={id} className={selEdit.satellite === id ? 'on' : ''} onClick={() => setSel({ satellite: id })}>{label}</button>
                  ))}
                </div>
              )}
              {sel.kind === 'satellite' && sel.bits_tonight !== undefined && sel.bits_tonight !== null && (
                <p className="sub">Tonight's cloud forecast leaves {Math.round(sel.bits_tonight).toLocaleString('en-US')} bits.</p>
              )}
              <button className="linkish" onClick={() => { const next = current.filter((_, i) => i !== selRoute); setSelRoute(null); if (next.length) edit(next) }}>
                Remove this route</button>
            </div>
          ) : (
            <div className="qe-route qe-hint">
              {shown && <p><b>{shown.by === 'you' ? 'Your network' : shown.by}</b>: the weakest pair, {name(shown.weakest.a)}–{name(shown.weakest.b)}, gets <b>{fmtRate(shown.score_bps)}</b>.</p>}
              {shown?.rationale && shown.by !== 'you' && shown.rationale.length > 30 && <p className="sub">{shown.rationale}</p>}
              <div className="qe-list">
                {routes.map((r, i) => (
                  <button key={i} onClick={() => { setSelRoute(i); const c = byId[r.a]; if (c) scene.current?.focus(c.lat, c.lon) }}>
                    <i style={{ background: r.key_rate_bps > 0 ? (r.key_rate_bps >= 100 ? '#4cc38a' : r.key_rate_bps >= 1 ? '#3987e5' : '#c3c7cf') : '#e5484d' }} />
                    <span>{name(r.a)}–{name(r.b)}</span>
                    <small>{r.kind === 'satellite' ? (r.satellite === 'qube2' ? 'QUBE-II' : 'SpeQtre') : r.kind === 'repeaters' ? `${r.repeaters} repeaters` : 'fiber'}</small>
                    <b>{fmtRate(r.key_rate_bps)}</b>
                  </button>
                ))}
              </div>
              <p className="sub">Drag to spin, scroll to zoom. Click a route to change it and watch the physics; click a city to fly there.</p>
              <button className={`btn small ${adding ? 'primary' : ''}`} onClick={() => { setAdding(!adding); setPending(null) }}>
                {adding ? (pending ? `From ${name(pending)}: click the other city` : 'Click the first city') : '+ Add a route'}</button>
            </div>
          )}
        </aside>

        <div className="qe-bottom">
          <span className="qe-legend">
            <i style={{ background: '#4cc38a' }} />over 100 bit/s<i style={{ background: '#3987e5' }} />1–100 bit/s
            <i style={{ background: '#c3c7cf' }} />bits a day<i style={{ background: '#e5484d' }} />no key
            <i className="dot" style={{ background: '#d9a441' }} />entangled photons
          </span>
          <span className="spacer" />
          <span className="qe-time">{clock} UTC · satellites on today's real orbits
            <span className="seg">{SPEEDS.map((s) => <button key={s} className={speed === s ? 'on' : ''} onClick={() => setSpeed(s)}>{s}×</button>)}</span>
          </span>
        </div>
      </div>
    </div>
  )
}
