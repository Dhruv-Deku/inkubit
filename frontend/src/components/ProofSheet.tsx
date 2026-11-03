import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ProofBench, ProofSheet } from '../types'

const MARK: Record<string, { sym: string; cls: string; label: string }> = {
  pass: { sym: '✓', cls: 'pass', label: 'passed' },
  fail: { sym: '✗', cls: 'fail', label: 'failed' },
  skipped: { sym: '–', cls: '', label: 'skipped' },
  note: { sym: '!', cls: 'warn', label: 'note' },
}

/** Every independent check on one circuit, grouped by the kind of mistake each one catches. */
export function ProofSheetView({ sheet }: { sheet: ProofSheet }) {
  const kinds = [...new Set(sheet.checks.map((c) => c.category))]
  return (
    <div className="panel proof-sheet" style={{ marginTop: 12 }}>
      <div className="panel-head"><h2>Proof sheet</h2>
        <span className="sub">{sheet.title}: {sheet.num_qubits} qubits, {sheet.gates} gates, {sheet.noise} noise</span></div>
      <p className="mission-headline" style={{ margin: '0 0 8px' }}>
        <span className={`badge ${sheet.failed ? 'fail' : 'pass'}`} style={{ marginRight: 8 }}>{sheet.failed ? `${sheet.failed} failed` : 'all checks passed'}</span>
        {sheet.summary}</p>
      <table className="calls">
        <thead><tr><th style={{ width: 28 }} /><th>Check</th><th>Kind</th><th>Result</th><th className="num">ms</th></tr></thead>
        <tbody>{kinds.flatMap((k) => sheet.checks.filter((c) => c.category === k).map((c) => {
          const m = MARK[c.status]
          return (
            <tr key={c.id} title={`Guards against: ${c.guards}`}>
              <td><span className={`badge ${m.cls}`} aria-label={m.label}>{m.sym}</span></td>
              <td><b>{c.title}</b><div className="sub">guards against {c.guards}</div></td>
              <td className="sub">{c.category}</td>
              <td>{c.detail}</td>
              <td className="num">{c.ms.toFixed(0)}</td>
            </tr>
          )
        }))}</tbody>
      </table>
      <p className="sub obs-method">Each check is independent of the others and of the code that produced the result. Thresholds are floating-point tolerances (1e-9 exact, 1e-6 between the two noisy
        engines); the ML verifier's miss is a note about the model, never about the circuit. qcanvas/proofsheet.py.</p>
    </div>
  )
}

/** The proof sheet run over the whole gallery (scripts/proofsheet_bench.py). */
export function ProofBenchPanel() {
  const [b, setB] = useState<ProofBench | null>(null)
  useEffect(() => { api.proofBench().then(setB).catch(() => setB(null)) }, [])
  if (!b) return null
  const t = b.totals
  const cats = [...new Set(b.rows.map((r) => r.category))]
  return (
    <div className="panel">
      <div className="panel-head"><h2>Proof sheet over the gallery</h2>
        <span className="sub">{b.checks_per_circuit} checks of {b.kinds} kinds on each of {b.circuits} algorithms in {b.categories} categories, {b.date_utc.slice(0, 10)}</span></div>
      <p className="obs-head" style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
        <b>{t.passed ?? 0} checks passed and {t.failed ?? 0} failed</b> across the gallery; {t.skipped ?? 0} were skipped with the reason and {t.notes ?? 0} left a note
        (the ML verifier's interval missed the exact value: it grades the fast model, not the circuit). Press <b>Proof sheet</b> under the editor to run them on any circuit.</p>
      <table className="calls">
        <thead><tr><th>Check</th><th>Kind</th><th>Guards against</th><th className="num">passed</th><th className="num">failed</th><th className="num">skipped</th><th className="num">notes</th></tr></thead>
        <tbody>{Object.entries(b.per_check).map(([id, c]) => (
          <tr key={id}><td>{c.title}</td><td className="sub">{c.category}</td><td className="sub">{c.guards}</td>
            <td className="num">{c.pass ?? 0}</td><td className="num">{c.fail ?? 0}</td><td className="num">{c.skipped ?? 0}</td><td className="num">{c.note ?? 0}</td></tr>
        ))}</tbody>
      </table>
      <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
        {cats.map((cat) => {
          const rows = b.rows.filter((r) => r.category === cat)
          return <span key={cat} className="chip-btn" title={rows.map((r) => r.title).join(', ')}>{cat}: {rows.length} · {rows.reduce((s, r) => s + r.failed, 0) ? 'failures' : 'all passed'}</span>
        })}
      </div>
    </div>
  )
}
