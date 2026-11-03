import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Headline, HeadlineChart } from '../types'
import type { Phase, SceneHandle } from './HeroScene'

const CW = 240
const CH = 44

/** The small chart drawn under each opening figure, from the same stored data the figure is computed from. */
function MiniChart({ c }: { c: HeadlineChart }) {
  if (c.kind === 'teleport') {
    const n = c.states.length
    const slot = CW / n
    const y = (v: number) => CH - v * CH
    return (
      <svg className="mini" viewBox={`0 0 ${CW} ${CH}`} role="img" aria-label="Teleportation fidelity per input state, with and without feed-forward">
        {c.states.map((st, i) => (
          <g key={st}>
            <rect className="m-with" x={i * slot + slot * 0.18} y={y(c.with[i])} width={slot * 0.3} height={c.with[i] * CH}>
              <title>{`${st}: ${c.with[i].toFixed(3)} with feed-forward`}</title></rect>
            <rect className="m-without" x={i * slot + slot * 0.52} y={y(c.without[i])} width={slot * 0.3} height={c.without[i] * CH}>
              <title>{`${st}: ${c.without[i].toFixed(3)} without corrections`}</title></rect>
          </g>
        ))}
        <line className="m-limit" x1={0} x2={CW} y1={y(c.limit)} y2={y(c.limit)} />
      </svg>
    )
  }
  if (c.kind === 'missions') {
    const top = Math.max(...c.seconds, 1)
    const slot = CW / c.seconds.length
    return (
      <svg className="mini" viewBox={`0 0 ${CW} ${CH}`} role="img" aria-label="Seconds each benchmark mission took">
        {c.seconds.map((s, i) => (
          <rect key={i} className={c.done[i] ? 'm-pass' : 'm-fail'} x={i * slot + 1} y={CH - (s / top) * CH} width={slot - 2} height={(s / top) * CH}>
            <title>{`mission ${i + 1}: ${s.toFixed(1)} s, ${c.done[i] ? 'finished' : 'did not finish'}`}</title></rect>
        ))}
      </svg>
    )
  }
  if (c.kind === 'proof') {
    const cols = c.circuits.length
    const rows = c.checks.length
    const cw = CW / cols
    const rh = CH / rows
    return (
      <svg className="mini" viewBox={`0 0 ${CW} ${CH}`} role="img" aria-label="Every proof check on every gallery circuit">
        {c.circuits.map((circ, x) => circ.cells.map((cell, yy) => (
          <rect key={`${x}-${yy}`} className={cell === 'pass' ? 'm-pass' : cell === 'fail' ? 'm-fail' : cell === 'note' ? 'm-note' : 'm-skip'}
            x={x * cw + 0.6} y={yy * rh + 0.6} width={cw - 1.2} height={rh - 1.2}>
            <title>{`${circ.title}: ${c.checks[yy]} (${cell})`}</title></rect>
        )))}
      </svg>
    )
  }
  return (
    <ul className="mini mini-models" aria-label="Meta models">
      {c.names.map((n) => <li key={n}>{n}</li>)}
    </ul>
  )
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
    <section className={`hero3d ${failed ? 'flat' : ''}`} aria-label="Inkubit">
      <div className="hero3d-stage" ref={host} aria-hidden="true">
        {failed && sc && <img className="hero3d-still" src={sc.image} alt="" />}
      </div>
      <div className="hero3d-copy">
        <h1>Draw a quantum circuit. Inkubit <span className="ink">proves<svg viewBox="0 0 200 16" preserveAspectRatio="none" aria-hidden="true">
          <path d="M3 9 C 42 4, 96 12, 146 6 S 186 7, 197 5" /><path d="M14 13 C 64 9, 122 14, 188 9" /></svg></span> what it does.</h1>
        <p className="lede">
          Photograph a sketch, type it or say it. Meta's models write the Qiskit code, an exact simulation checks
          every number, and real IBM chips run it.
        </p>
        <div className="hero3d-cta">
          <button className="btn primary big" onClick={onMission}>Launch a mission</button>
          <button className="linkish" onClick={onTour}>or take the 95-second tour</button>
        </div>
        {data && (
          <div className="hero3d-figs">
            {data.stats.map((s) => (
              <figure key={s.source} title={`${s.note} (${s.source})`}>
                {s.chart && <MiniChart c={s.chart} />}
                <figcaption><b>{s.value}</b><span>{s.label}</span></figcaption>
              </figure>
            ))}
          </div>
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
