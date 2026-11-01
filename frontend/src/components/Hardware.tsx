import { useEffect, useState } from 'react'
import { api } from '../api'
import type { HardwareRuns } from '../types'

/** Counts from a real IBM quantum computer next to Q-Canvas's predictions. Hidden until a real run exists. */
export function HardwarePanel() {
  const [h, setH] = useState<HardwareRuns | null>(null)
  useEffect(() => { api.hardware().then(setH).catch(() => setH(null)) }, [])
  if (!h || h.rehearsal) return null
  const best = h.runs.filter((r) => r.tvd_twin < Math.min(r.tvd_ideal, r.tvd_generic)).length
  const span = (k: 'tvd_twin' | 'tvd_generic') => `${Math.min(...h.runs.map((r) => r[k])).toFixed(3)}–${Math.max(...h.runs.map((r) => r[k])).toFixed(3)}`
  const pessimistic = h.runs.filter((r) => r.tvd_generic > r.tvd_ideal).length
  return (
    <div className="panel">
      <div className="panel-head"><h2>Real hardware</h2>
        <span className="sub">{h.runs.length} circuits on {h.device} (IBM Quantum), {h.shots.toLocaleString()} shots, {h.date_utc.slice(0, 10)}, job {h.job_id}</span></div>
      <p className="obs-head" style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
        A real IBM quantum computer ran {h.runs.length} circuits. A digital twin built from the chip's own calibration predicted what it measured best on <b>{best} of {h.runs.length}</b> (distance {span('tvd_twin')}).
        {pessimistic ? ` Q-Canvas's generic noise preset was too pessimistic for this chip (${span('tvd_generic')}): on ${pessimistic === h.runs.length ? 'every circuit' : `${pessimistic} of ${h.runs.length}`} it was further off than the noiseless prediction, which is why a calibrated twin matters.` : ''}</p>
      <table className="calls">
        <thead><tr><th>Circuit</th><th className="num">2-qubit gates on the chip</th><th className="num">distance to ideal</th>
          <th className="num">to Q-Canvas's generic preset</th><th className="num">to the device's digital twin</th></tr></thead>
        <tbody>{h.runs.map((r) => (
          <tr key={r.id}><td>{r.circuit}</td><td className="num">{r.two_qubit_gates}</td><td className="num">{r.tvd_ideal.toFixed(3)}</td>
            <td className="num">{r.tvd_generic.toFixed(3)}</td><td className="num">{r.tvd_twin.toFixed(3)}</td></tr>
        ))}</tbody>
      </table>
      <p className="sub obs-method">Total variation distance between what the chip measured and each prediction (lower is closer). The digital twin is Qiskit Aer's noise model built from the device's own
        calibration (NoiseModel.from_backend) on the same transpiled circuit; scripts/hardware_check.py reruns it.</p>
    </div>
  )
}
