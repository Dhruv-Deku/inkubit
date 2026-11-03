import { useEffect, useState } from 'react'
import { api } from '../api'
import type { DiscoveryHardware, DiscoveryHardwareVariant, HardwareRuns } from '../types'

const range = (xs: number[]) => `${Math.min(...xs).toFixed(3)}–${Math.max(...xs).toFixed(3)}`

/** Counts from a real IBM quantum computer next to Inkubit's predictions. Hidden until a real run exists. */
export function HardwarePanel() {
  const [h, setH] = useState<HardwareRuns | null>(null)
  useEffect(() => { api.hardware().then(setH).catch(() => setH(null)) }, [])
  if (!h || h.rehearsal) return null
  const best = h.runs.filter((r) => r.tvd_twin < Math.min(r.tvd_ideal, r.tvd_generic)).length
  const span = (k: 'tvd_twin' | 'tvd_generic') => range(h.runs.map((r) => r[k]))
  const pessimistic = h.runs.filter((r) => r.tvd_generic > r.tvd_ideal).length
  const cal = h.calibration && h.runs.every((r) => r.tvd_calibrated !== undefined) ? h.calibration : null
  const calBeats = cal ? h.runs.filter((r) => (r.tvd_calibrated ?? 1) < r.tvd_twin).length : 0
  return (
    <div className="panel">
      <div className="panel-head"><h2>Real hardware</h2>
        <span className="sub">{h.runs.length} circuits on {h.device} (IBM Quantum), {h.shots.toLocaleString()} shots, {h.date_utc.slice(0, 10)}, job {h.job_id}</span></div>
      <p className="obs-head" style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
        A real IBM quantum computer ran {h.runs.length} circuits. A digital twin built from the chip's own calibration predicted what it measured more closely than the noiseless odds and the generic preset on <b>{best} of {h.runs.length}</b> (distance {span('tvd_twin')}).
        {pessimistic ? ` Inkubit's generic noise preset was too pessimistic for this chip (${span('tvd_generic')}): on ${pessimistic === h.runs.length ? 'every circuit' : `${pessimistic} of ${h.runs.length}`} it was further off than the noiseless prediction.` : ''}
        {cal ? <> The <b>calibrated preset</b>, Inkubit's own noise model with {cal.device}'s median calibration, came within {range(h.runs.map((r) => r.tvd_calibrated ?? 0))}, closer than the twin on {calBeats} of {h.runs.length}.</> : null}</p>
      <table className="calls">
        <thead><tr><th>Circuit</th><th className="num">2-qubit gates on the chip</th><th className="num">distance to ideal</th>
          <th className="num">to the generic preset</th><th className="num">to the digital twin</th>
          {cal && <><th className="num">to the calibrated preset</th><th className="num">shot noise alone</th></>}</tr></thead>
        <tbody>{h.runs.map((r) => (
          <tr key={r.id}><td>{r.circuit}</td><td className="num">{r.two_qubit_gates}</td><td className="num">{r.tvd_ideal.toFixed(3)}</td>
            <td className="num">{r.tvd_generic.toFixed(3)}</td><td className="num">{r.tvd_twin.toFixed(3)}</td>
            {cal && <><td className="num">{r.tvd_calibrated?.toFixed(3)}</td><td className="num">{r.shot_noise_tvd?.toFixed(3)}</td></>}</tr>
        ))}</tbody>
      </table>
      <p className="sub obs-method">Total variation distance between what the chip measured and each prediction (lower is closer). The digital twin is Qiskit Aer's noise model built from the device's own
        calibration (NoiseModel.from_backend) on the same transpiled circuit; scripts/hardware_check.py reruns it.
        {cal && ` The calibrated preset ("Calibrated" in the run bar) uses medians of a calibration snapshot taken ${cal.taken_utc.slice(0, 16).replace('T', ' ')} UTC, a few hours after the run (scripts/calibration_snapshot.py); "shot noise alone" is the distance a perfect prediction would still show at ${h.shots.toLocaleString()} shots.`}</p>
      <DiscoveryOnHardware />
    </div>
  )
}

const isBaseline = (v: DiscoveryHardwareVariant) => v.source === 'textbook' || v.source === 'compiler'
/** Won, tied or lost against the best baseline, by the margin in standard errors of shot noise. */
export const verdict = (z: number) => (z > 2 ? 'won' : z < -2 ? 'lost' : 'tied')
const pm = (x: number, se?: number) => `${x.toFixed(3)}${se ? ` ± ${se.toFixed(3)}` : ''}`

/** The discovery lab's proven circuits, run on the chip next to the baselines they beat. Hidden until a real run exists. */
export function DiscoveryOnHardware() {
  const [d, setD] = useState<DiscoveryHardware | null>(null)
  useEffect(() => { api.discoveryHardware().then(setD).catch(() => setD(null)) }, [])
  if (!d || d.rehearsal) return null
  const tally = (w: string) => d.goals.filter((g) => g.comparison && verdict(g.comparison.z) === w).length
  const [won, tied, lost] = [tally('won'), tally('tied'), tally('lost')]
  return (
    <div className="disc-hw" style={{ marginTop: 18 }}>
      <h3 style={{ margin: '0 0 4px' }}>AI-discovered circuits on the same kind of chip</h3>
      <p className="sub" style={{ margin: '0 0 8px', maxWidth: '90ch' }}>{d.circuits} circuits on {d.device}, {d.shots.toLocaleString()} shots each, {d.date_utc.slice(0, 10)}, job {d.job_id}.
        Against the best baseline, the discovery lab's proven circuit <b>won on {won} of {d.goals.length}</b> goals by more than two standard errors of shot noise{tied ? `, tied within shot noise on ${tied}` : ''}{lost ? `, lost on ${lost}` : ''}. Raw counts, no readout correction, the same for every circuit.</p>
      {d.goals.map((g) => {
        const ghz = g.variants.some((v) => v.ghz)
        return (
          <div key={g.id} style={{ marginBottom: 12 }}>
            <div className="row wrap" style={{ gap: 8, alignItems: 'baseline' }}><b>{g.title}</b>
              {g.comparison && <span className="sub">{verdict(g.comparison.z)} ({g.comparison.margin >= 0 ? '+' : ''}{g.comparison.margin.toFixed(3)} {g.comparison.metric}, {g.comparison.z.toFixed(1)} standard errors)</span>}
              <span className="sub">{g.patch ? `physical qubits ${g.patch.join(', ')}, wired like a 7-qubit Falcon chip; every circuit compiled onto them` : 'each circuit compiled by Qiskit at level 3 for the chip'}</span></div>
            <table className="calls">
              <thead><tr><th>Circuit</th><th className="num">CNOTs in the lab</th><th className="num">2-qubit gates on the chip</th>
                {ghz && <th className="num">GHZ fidelity, chip (twin)</th>}<th className="num">outcome fidelity, chip (twin)</th></tr></thead>
              <tbody>{g.variants.map((v) => (
                <tr key={v.label}><td>{isBaseline(v) ? v.label : <b>{v.label}</b>}</td><td className="num">{v.cx_logical}</td><td className="num">{v.two_qubit_gates}</td>
                  {ghz && <td className="num">{v.ghz ? `${pm(v.ghz.fidelity, v.ghz.se)} (${v.twin_ghz?.fidelity.toFixed(3)})` : '–'}</td>}
                  <td className="num">{pm(v.outcome_fidelity, v.outcome_se)} ({v.twin_outcome_fidelity.toFixed(3)})</td></tr>
              ))}</tbody>
            </table>
          </div>
        )
      })}
      <p className="sub obs-method">GHZ fidelity = (P(0…0) + P(1…1))/2 + |coherence|, the coherence measured from a parity oscillation over 8 phases; above 0.5 certifies genuine multi-qubit entanglement.
        Outcome fidelity is the Hellinger fidelity of the measured odds with the ideal ones; computational-basis odds cannot see phase errors, much of what fewer two-qubit gates save.
        ± is one standard error of shot noise. scripts/discovery_hardware.py reruns the search and the comparison.</p>
    </div>
  )
}
