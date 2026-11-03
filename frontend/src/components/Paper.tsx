import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'

interface PClaim { outcome: string; ours: string; claimed: number; ideal: number; noisy: number | null; tolerance: number; verdict: string; ok: boolean }
interface PExperiment { name: string; page: number; quote: string; verdict: string; claims: PClaim[]; hardware: string; shots: number; note: string; bit_order: string; bit_order_inferred: boolean }
export interface PResult { source: string; title: string; experiments: PExperiment[]; reproduced: number; checked: number; claims_ok: number; claims_total: number; headline: string; notes: string; seconds: number; calls: { model: string }[] }

const BADGE: Record<string, string> = { reproduced: 'pass', 'partly reproduced': 'warn', 'not reproduced': 'fail' }

/** A whole paper in (a PDF or an arXiv id): every experiment with a circuit and stated odds re-run exactly. */
export function PaperPanel({ live }: { live: boolean }) {
  const [examples, setExamples] = useState<PResult[]>([])
  const [result, setResult] = useState<PResult | null>(null)
  const [arxiv, setArxiv] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)
  useEffect(() => {
    api.paperExamples().then((r) => { setExamples(r.papers); setResult((x) => x ?? r.papers[0] ?? null) }).catch(() => {})
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [])
  const start = async () => {
    setBusy(true); setError(null)
    try {
      const { paper_id } = await api.startPaper(arxiv, file)
      timer.current = window.setInterval(async () => {
        try {
          const r = await api.paper(paper_id)
          if (r.status !== 'running') {
            if (timer.current) window.clearInterval(timer.current)
            setBusy(false)
            if (r.error) setError(r.error); else setResult(r.result as PResult)
          }
        } catch { /* keep polling */ }
      }, 4000)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The paper could not be read.')
      setBusy(false)
    }
  }
  if (!examples.length && !live) return null
  return (
    <div className="panel paper">
      <div className="panel-head">
        <h2>Reproduce a whole paper</h2>
        <span className="sub">a PDF or an arXiv id, every number checked</span>
      </div>
      <div className="row wrap" style={{ gap: 8 }}>
        {examples.map((x) => <button key={x.source} className={`chip-btn${result?.source === x.source ? ' on' : ''}`} onClick={() => setResult(x)} disabled={busy}>{x.title || x.source}</button>)}
        {live && <>
          <input className="mono" style={{ width: 150 }} value={arxiv} onChange={(e) => setArxiv(e.target.value)} placeholder="arXiv id, e.g. 1804.03719" aria-label="arXiv id" disabled={busy} />
          <label className="btn small" style={{ cursor: 'pointer' }}>{file ? file.name.slice(0, 24) : 'or a PDF'}<input type="file" accept="application/pdf" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={busy} /></label>
          <button className="btn small primary" onClick={() => { void start() }} disabled={busy || (!arxiv.trim() && !file)}>{busy ? 'Reading the paper (1-2 min)…' : 'Reproduce it'}</button>
        </>}
      </div>
      {error && <div className="notice error" style={{ marginTop: 8 }}>{error}</div>}
      {result && (
        <>
          <p className="obs-head" style={{ margin: '12px 0 6px', fontSize: 14, lineHeight: 1.5, color: 'var(--text)', maxWidth: '90ch' }}>
            <b>{result.title || result.source}</b>{result.title.includes(result.source) ? '' : ` (${result.source})`}: {result.headline} Read and checked in {Math.round(result.seconds)} s, live.</p>
          <div className="paper-exps">
            {result.experiments.map((e, i) => (
              <details key={i} className="paper-exp" open={i === 0 || e.claims.length > 0 && i < 3}>
                <summary>
                  <span className={`badge ${BADGE[e.verdict] ?? ''}`}>{e.verdict}</span> <b>{e.name}</b>
                  <span className="sub"> · page {e.page}{e.hardware ? ` · ${e.hardware}` : ''}{e.shots ? ` · ${e.shots.toLocaleString()} shots` : ''}</span>
                </summary>
                {e.quote && <p className="sub paper-quote">“{e.quote}”</p>}
                {e.note && <p className="sub">{e.note}</p>}
                {e.claims.length > 0 && (
                  <table className="calls disc-table">
                    <thead><tr><th>Outcome</th><th className="num">Paper says</th><th className="num">Exact ideal</th><th className="num">Our realistic noise</th><th>Verdict</th></tr></thead>
                    <tbody>{e.claims.map((c, k) => (
                      <tr key={k}><td className="mono">{c.outcome}</td><td className="num">{c.claimed.toFixed(3)}</td><td className="num">{c.ideal.toFixed(3)}</td>
                        <td className="num">{c.noisy !== null ? c.noisy.toFixed(3) : '–'}</td><td><span className={c.ok ? 'good' : 'bad'}>{c.ok ? '✓' : '✗'}</span> {c.verdict}</td></tr>
                    ))}</tbody>
                  </table>
                )}
                {e.claims.length > 0 && <p className="sub">Bit order: {e.bit_order.replace('_', ' ').replace('_', ' ')}{e.bit_order_inferred ? ' (inferred: the paper does not say; the order that fits the ideal odds better is used)' : ''}.</p>}
              </details>
            ))}
          </div>
        </>
      )}
      <p className="sub obs-method">Two passes: Muse Wonder reads the whole PDF (text and an image of every page, up to 50 pages of images) and lists up to eight experiments on different circuits with their pages;
        for each, those pages are cut out and Muse Spark transcribes the circuit as OpenQASM and copies every stated probability, never computing one. The circuit goes through the Rosetta's exact parser;
        each claim is judged like a figure's: inside its shot-noise error bar of the ideal value, or for hardware data between our realistic-noise value and the ideal one (our noise model is not their chip).</p>
    </div>
  )
}
