import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { EstimateResult } from '../types'
import { CallBadge } from './CallBadge'
import { LineChart } from './Observatory'
import { VoiceButton } from './VoiceButton'

const YEAR = 3.156e7
export function duration(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return '–'
  if (s < 60) return `${s.toPrecision(3)} s`
  if (s < 3600) return `${(s / 60).toPrecision(3)} min`
  if (s < 2 * 86400) return `${(s / 3600).toPrecision(3)} h`
  if (s < YEAR) return `${(s / 86400).toPrecision(3)} days`
  const y = s / YEAR
  return y < 1e6 ? `${y.toPrecision(3)} years` : `${y.toExponential(1).replace('e+', 'e')} years`
}
const qubits = (x: number) => (!Number.isFinite(x) ? '∞' : x >= 1e6 ? `${(x / 1e6).toPrecision(3)} M` : x.toLocaleString(undefined, { maximumFractionDigits: 0 }))
const VERDICT_CLASS: Record<string, string> = {
  'classical wins': 'warn', 'no known quantum speedup': 'warn', 'classical can still do it exactly': 'warn',
}

/** When does quantum win for my problem? Error-corrected resource estimates against the best classical route, with
 *  the model checked against a published figure. */
export function EstimatorPanel({ live }: { live: boolean }) {
  const [presets, setPresets] = useState<{ id: string; label: string }[]>([])
  const [hardware, setHardware] = useState<{ id: string; label: string }[]>([])
  const [hw, setHw] = useState('superconducting')
  const [text, setText] = useState('')
  const [last, setLast] = useState<{ preset?: string; text?: string }>({ preset: 'rsa2048' })
  const [r, setR] = useState<EstimateResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.estimatePresets().then((p) => { setPresets(p.presets); setHardware(p.hardware) }).catch(() => {}) }, [])
  useEffect(() => {
    let alive = true
    setBusy(true)
    api.estimate({ ...last, hardware: hw }).then((res) => { if (alive) { setR(res); setError(null) } })
      .catch((e) => { if (alive) setError(e instanceof ApiError ? e.message : 'The estimate failed.') })
      .finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [last, hw])
  const q = r?.quantum
  const chart = r && r.curve.length > 0 && (
    r.family === 'simulation'
      ? <LineChart yLog yLogStep={1} xLabel={r.curve_x} yLabel="physical qubits needed" fmtX={(v) => String(v)}
          fmtY={(v) => qubits(v)} height={250} aria="Physical qubits needed against the number of spins"
          lines={[{ id: 'q', label: 'Physical qubits', points: r.curve.map((p) => [p.x, p.physical_qubits]), color: 'var(--primary)' }]} labels={false} />
      : <LineChart yLog xLabel={r.curve_x} yLabel="time to solve, seconds" fmtX={(v) => (r.family === 'search' ? `2^${v}` : String(v))}
          fmtY={(v) => duration(v)} height={260}
          refs={[{ value: YEAR, label: '1 year', axis: 'y' }, ...(r.family === 'search' && r.details.crossover_log2 ? [{ value: Number(r.details.crossover_log2), label: 'crossover', axis: 'x' as const }] : [])]}
          aria={r.family === 'search' ? 'Time to search against problem size: classical grows twice as fast per bit but starts far lower; the quantum line crosses it only at very large sizes'
            : 'Time to factor against key size: classical grows super-polynomially, quantum polynomially'}
          lines={[{ id: 'q', label: 'Error-corrected quantum computer', points: r.curve.map((p) => [p.x, p.quantum_s]), color: 'var(--primary)', labelAt: 'start' },
            { id: 'c', label: r.family === 'search' ? 'Classical cluster' : 'Classical, one core', points: r.curve.map((p) => [p.x, p.classical_s]), color: 'var(--predicted)', labelAt: 'start' }]} />
  )
  return (
    <div className="panel estimator">
      <div className="panel-head">
        <h2>When does quantum win?</h2>
        <span className="sub">describe a real problem: {live ? 'Muse Spark maps it to an algorithm, ' : ''}an error-corrected estimate meets the best classical route, every assumption and source shown</span>
      </div>
      <form className="row wrap" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (text.trim()) setLast({ text: text.trim() }) }}>
        <input type="text" className="copilot-input" style={{ flex: '1 1 280px', minWidth: 0 }} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. break the encryption on my bank's website, design a battery material, crack a 56-bit key…" aria-label="Your problem" disabled={busy} />
        <VoiceButton onText={setText} onDone={(t) => { setText(t); setLast({ text: t }) }} disabled={busy} live={live} />
        <button className="btn primary" type="submit" disabled={busy || !text.trim()}>{busy ? 'Estimating…' : 'Estimate'}</button>
      </form>
      <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
        <span className="label">Try</span>
        {presets.map((p) => <button key={p.id} className={`chip-btn${last.preset === p.id ? ' on' : ''}`} onClick={() => setLast({ preset: p.id })}>{p.label}</button>)}
      </div>
      <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
        <span className="label">Hardware</span>
        {hardware.map((h) => <button key={h.id} className={`chip-btn${hw === h.id ? ' on' : ''}`} onClick={() => setHw(h.id)}>{h.label}</button>)}
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {r && (
        <div className="est-result">
          <div className="row wrap" style={{ gap: 8, alignItems: 'baseline' }}>
            <span className={`est-verdict ${VERDICT_CLASS[r.verdict] ?? 'ok'}`}>{r.verdict}</span>
            <b className="est-title">{r.title}</b>
            {r.read_by === 'muse' && typeof r.mapped.title === 'string' && r.mapped.title && r.family !== 'none' && <span className="sub">modelled from: {r.mapped.title}</span>}
            <span className="sub">{r.read_by === 'muse' ? 'read by Muse Spark' : r.read_by.startsWith('offline') ? r.read_by : ''}</span>
            {r.call && <CallBadge call={r.call} />}
          </div>
          <p className="mission-headline" style={{ marginTop: 8 }}>{r.headline}</p>
          {q && (
            <div className="mini-tiles">
              <span><b>{qubits(q.physical_qubits)}</b> physical qubits</span>
              <span><b>{duration(q.runtime_s)}</b> running</span>
              <span><b>{q.logical_qubits.toLocaleString()}</b> logical qubits</span>
              <span><b>d = {q.code_distance}</b> code distance</span>
              <span><b>{q.t_count.toExponential(2).replace('e+', 'e')}</b> T gates</span>
              <span><b>{q.factories.toLocaleString()}</b> magic-state factories ({qubits(q.factory_qubits)} qubits)</span>
              {r.classical_s !== null && <span><b>{duration(r.classical_s)}</b> classical</span>}
            </div>
          )}
          {q?.note && <div className="notice" style={{ marginTop: 8 }}>{q.note}</div>}
          {r.classical_note && <p className="sub" style={{ margin: '6px 0 0' }}>{r.classical_note}</p>}
          {r.check && <p className="est-check">{r.check}</p>}
          {chart}
          {(r.assumptions.length > 0 || r.sources.length > 0) && (
            <details className="obs-table">
              <summary className="sub">Assumptions and sources</summary>
              <ul className="est-list">{r.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              <ul className="est-list">{r.sources.map((a) => <li key={a}>{a}</li>)}</ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
