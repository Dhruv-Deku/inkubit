import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { PulseReport } from '../types'
import { LineChart } from './Observatory'

const DURATIONS = [4, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 70, 100]
const sci = (v: number) => (v >= 0.01 ? v.toFixed(3) : v.toExponential(1).replace('e-', 'e−'))

/** A gate as the microwave pulse that drives it: a pi pulse on a three-level transmon, Gaussian or DRAG. */
export function PulsePanel() {
  const [di, setDi] = useState(6)
  const [drag, setDrag] = useState(true)
  const [r, setR] = useState<PulseReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const d = DURATIONS[di]
  useEffect(() => {
    let live = true
    setBusy(true)
    api.pulse(d, drag).then((x) => { if (live) { setR(x); setError(null) } })
      .catch((e) => { if (live) setError(e instanceof ApiError ? e.message : 'Failed.') })
      .finally(() => { if (live) setBusy(false) })
    return () => { live = false }
  }, [d, drag])
  const run = r?.run, sw = r?.sweep
  return (
    <div className="panel pulse">
      <div className="panel-head">
        <h2>Pulse lab</h2>
        <span className="sub">from the sketch down to the microwave pulse: an X gate on a superconducting qubit, with the third level it can leak into</span>
      </div>
      <div className="row wrap" style={{ gap: 10 }}>
        <div className="seg">
          <button className={!drag ? 'on' : ''} onClick={() => setDrag(false)}>Gaussian</button>
          <button className={drag ? 'on' : ''} onClick={() => setDrag(true)}>DRAG</button>
        </div>
        <span className="label">Pulse length</span>
        <input type="range" min={0} max={DURATIONS.length - 1} value={di} onChange={(e) => setDi(Number(e.target.value))} aria-label="Pulse length" style={{ flex: 1, minWidth: 160, maxWidth: 360 }} />
        <span className="mono sub">{d} ns</span>
        {busy && <span className="sub">{sw ? 'simulating…' : 'simulating the sweep (about 30 s the first time)…'}</span>}
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {run && sw && (
        <>
          <p className="obs-head" style={{ margin: '10px 0 6px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '88ch' }}>
            A {d} ns {drag ? 'DRAG' : 'Gaussian'} pulse makes an X gate with {(run.fidelity * 100).toFixed(3)}% fidelity and leaves {sci(run.leakage)} of the qubit in |2⟩.
            The best plain Gaussian reaches {sci(sw.best_gaussian[1])} error at {sw.best_gaussian[0]} ns, because faster ones leak; DRAG gets {sci(sw.best_drag[1])} at {sw.best_drag[0]} ns, where only T1 and T2 are left.</p>
          <div className="mini-tiles">
            <span><b>{(run.fidelity * 100).toFixed(3)}%</b> gate fidelity</span>
            <span><b>{sci(run.leakage)}</b> leakage to |2⟩</span>
            <span><b>{(run.fidelity_no_decoherence * 100).toFixed(4)}%</b> without T1/T2</span>
            {run.drag && <span><b>β = {run.beta.toFixed(2)}</b> DRAG, calibrated</span>}
            <span><b>{Math.max(...run.omega_x_mhz).toFixed(1)} MHz</b> peak drive</span>
          </div>
          <div className="dist-grid">
            <LineChart xLabel="time, ns" yLabel="drive envelope, MHz (I in phase, Q quadrature)" fmtX={(v) => String(+v.toFixed(1))} fmtY={(v) => v.toFixed(0)} height={220} table={false}
              aria="The pulse envelope: a Gaussian in phase and, with DRAG, its derivative in quadrature"
              lines={[{ id: 'i', label: 'I (in phase)', points: run.times.map((t, k) => [t, run.omega_x_mhz[k]]), color: 'var(--primary)' },
                ...(run.drag ? [{ id: 'q', label: 'Q (DRAG quadrature)', points: run.times.map((t, k) => [t, run.omega_y_mhz[k]] as [number, number]), color: 'var(--predicted)' }] : [])]} labels={false} />
            <LineChart xLabel="time, ns" yLabel="population of each level" fmtX={(v) => String(+v.toFixed(1))} fmtY={(v) => v.toFixed(2)} yDomain={[0, 1]} height={220} table={false}
              aria="Populations during the pulse: |0> drains into |1>; |2> rises briefly in the middle"
              lines={[{ id: 'p0', label: '|0⟩', points: run.populations.map((p, k) => [k * run.duration_ns / (run.populations.length - 1), p[0]]), color: 'var(--text-2)', dash: '6 4' },
                { id: 'p1', label: '|1⟩', points: run.populations.map((p, k) => [k * run.duration_ns / (run.populations.length - 1), p[1]]), color: 'var(--primary)' },
                { id: 'p2', label: '|2⟩ (leakage)', points: run.populations.map((p, k) => [k * run.duration_ns / (run.populations.length - 1), p[2]]), color: 'var(--predicted)' }]} labels={false} />
          </div>
          <LineChart xLog yLog xLabel="pulse length, ns" yLabel="gate error (1 − average fidelity)" fmtX={(v) => String(v)} fmtY={sci} height={260}
            refs={[{ value: d, label: `${d} ns`, axis: 'x' }]}
            aria="Gate error against pulse length: Gaussian pulses are limited by leakage when short; DRAG pulses follow the T1/T2 limit down to about 15 ns"
            lines={[{ id: 'g', label: 'Gaussian', points: sw.durations.map((x, k) => [x, sw.gaussian_error[k]]), color: 'var(--predicted)', markers: true },
              { id: 'd', label: 'DRAG (β calibrated)', points: sw.durations.map((x, k) => [x, sw.drag_error[k]]), color: 'var(--primary)', markers: true },
              { id: 't', label: 'T1/T2 alone over the same time', points: sw.durations.map((x, k) => [x, sw.decoherence_only[k]]), color: 'var(--text-2)', dash: '6 4' }]} labels={false} />
          <p className="sub obs-method">How it is computed: a transmon truncated to |0⟩, |1⟩, |2⟩ with anharmonicity −300 MHz, in the frame rotating at the qubit frequency; the π pulse is a Gaussian of σ = length/4 scaled to area π;
            DRAG adds the quadrature −β Ω̇/α (Motzoi et al. 2009) with β found by a golden-section search; T1 = 100 µs and T2 = 80 µs as Lindblad terms; 400 exact steps; average gate fidelity of the qubit-subspace channel, leakage counted as error.</p>
        </>
      )}
    </div>
  )
}
