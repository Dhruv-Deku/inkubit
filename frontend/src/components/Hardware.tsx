import { useEffect, useState } from 'react'
import { api } from '../api'
import type { HardwareRuns } from '../types'

/** Counts from a real IBM quantum computer next to Q-Canvas's predictions. Hidden until a real run exists. */
export function HardwarePanel() {
  const [h, setH] = useState<HardwareRuns | null>(null)
  useEffect(() => { api.hardware().then(setH).catch(() => setH(null)) }, [])
  if (!h || h.rehearsal) return null
  return (
    <div className="panel">
      <div className="panel-head"><h2>Real hardware</h2>
        <span className="sub">{h.runs.length} circuits on {h.device} (IBM Quantum), {h.shots.toLocaleString()} shots, {h.date_utc.slice(0, 10)}, job {h.job_id}</span></div>
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
