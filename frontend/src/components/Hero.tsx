import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Headline } from '../types'
import type { Phase, SceneHandle } from './HeroScene'

/** Counts a figure up from zero once, keeping its format ("0.924", "30/30", "299/299", "5"). */
function CountUp({ value }: { value: string }) {
  const m = /^(\d+(?:\.\d+)?)(.*)$/.exec(value)
  const [shown, setShown] = useState(m ? value.replace(m[1], (0).toFixed((m[1].split('.')[1] ?? '').length)) : value)
  useEffect(() => {
    if (!m || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setShown(value); return }
    const end = parseFloat(m[1])
    const dec = (m[1].split('.')[1] ?? '').length
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / 1300)
      const e = 1 - (1 - k) ** 3
      setShown((end * e).toFixed(dec) + m[2])
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])
  return <>{shown}</>
}

function webglOk(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

/** The opening of the start page: the pipeline replayed in 3D on the bundled GHZ sketch, with four stored figures. */
export function Hero({ onMission, onTour }: { onMission: () => void; onTour: () => void }) {
  const [data, setData] = useState<Headline | null>(null)
  const [phase, setPhase] = useState<Phase>(0)
  const [failed, setFailed] = useState(false)
  const host = useRef<HTMLDivElement>(null)
  const handle = useRef<SceneHandle | null>(null)

  useEffect(() => { api.headline().then(setData).catch(() => setFailed(true)) }, [])

  useEffect(() => {
    if (!data || !host.current) return
    if (!webglOk()) { setFailed(true); return }
    let alive = true
    import('./HeroScene').then(({ mountHeroScene }) => {
      if (!alive || !host.current) return
      try {
        handle.current = mountHeroScene(host.current, data.scene, setPhase)
      } catch {
        setFailed(true)
      }
    }).catch(() => setFailed(true))
    return () => { alive = false; handle.current?.dispose(); handle.current = null }
  }, [data])

  const sc = data?.scene
  const gates = sc?.operations.map((o) => o.gate).join(' · ')
  const steps = [
    { model: 'SAM 3.1', text: sc ? `finds ${sc.segments.length} drawn parts` : 'finds the drawn parts' },
    { model: 'Muse Spark', text: gates ? `reads ${gates}` : 'reads the circuit' },
    { model: 'Qiskit Aer', text: sc ? `${sc.shots.toLocaleString('en-US')} noisy shots` : 'a noisy run' },
    { model: 'Verifier', text: sc ? `fidelity ${sc.fidelity.toFixed(4)} to the exact prediction` : 'checks it independently' },
  ]

  return (
    <section className={`hero3d ${failed ? 'flat' : ''}`} aria-label="Q-Canvas">
      <div className="hero3d-stage" ref={host} aria-hidden="true">
        {failed && sc && <img className="hero3d-still" src={sc.image} alt="" />}
      </div>
      <div className="hero3d-copy">
        <p className="eyebrow">Photo&nbsp;→ spec&nbsp;→ Qiskit&nbsp;→ noisy run&nbsp;→ proof</p>
        <h1>From a pencil sketch to <span>verified</span> quantum code.</h1>
        <p className="lede">
          Meta's models read your drawing, plan the work and write the code. Every answer is checked against an
          independent exact simulation, and any circuit can go from the editor to a real IBM chip.
        </p>
        <div className="hero3d-cta">
          <button className="btn primary big" onClick={onMission}>Launch a mission</button>
          <button className="btn big ghost" onClick={onTour}>Take the guided tour</button>
        </div>
        {data && (
          <dl className="hero3d-stats">
            {data.stats.map((s) => (
              <div key={s.source} title={`${s.note} (${s.source})`}>
                <dt><CountUp value={s.value} /></dt>
                <dd>{s.label}<small>{s.note}</small></dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      {!failed && sc && (
        <div className="hero3d-run">
          <ol className="hero3d-steps">
            {steps.map((s, i) => {
              const n = i + 1
              const state = phase === 0 ? '' : n < phase || (n === 4 && phase === 4) ? 'done' : n === phase ? 'on' : ''
              return (
                <li key={s.model} className={state}>
                  <span className="n">{state === 'done' ? '✓' : n}</span>
                  <span><b>{s.model}</b>{s.text}</span>
                </li>
              )
            })}
          </ol>
          <div className="hero3d-legend">
            <span><i className="sw measured" />measured</span>
            <span><i className="sw predicted" />predicted</span>
            <span><i className="sw gold" />entangled</span>
            <button className="linkish" onClick={() => handle.current?.replay()}>Replay</button>
          </div>
        </div>
      )}
    </section>
  )
}
