import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Headline } from '../types'
import type { Phase, SceneHandle } from './HeroScene'

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
    <section className={`hero3d ${failed ? 'flat' : ''}`} aria-label="Inkubit">
      <div className="hero3d-stage" ref={host} aria-hidden="true">
        {failed && sc && <img className="hero3d-still" src={sc.image} alt="" />}
      </div>
      <div className="hero3d-copy">
        <h1>Draw a quantum circuit. Inkubit proves what it does.</h1>
        <p className="lede">
          Photograph a sketch, type it or say it. Meta's models write the Qiskit code, an exact simulation checks
          every number, and real IBM chips run it.
        </p>
        <div className="hero3d-cta">
          <button className="btn primary big" onClick={onMission}>Launch a mission</button>
          <button className="linkish" onClick={onTour}>or take the 95-second tour</button>
        </div>
        {data && (
          <dl className="hero3d-record">
            {data.stats.map((s) => (
              <div key={s.source} title={`${s.note} (${s.source})`}>
                <dt>{s.value}</dt>
                <dd>{s.label}</dd>
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
