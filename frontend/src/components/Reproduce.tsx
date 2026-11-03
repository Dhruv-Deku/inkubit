import { useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { CircuitSpec, Reproduction } from '../types'
import { CallBadge } from './CallBadge'
import { CircuitPreview } from './CircuitPreview'

const SAMPLE = `OPENQASM 2.0; include "qelib1.inc"; qreg q[3]; creg c[3];
h q[0]; cx q[0],q[1]; cx q[1],q[2]; measure q -> c;
Fig. 2: measured on a superconducting processor, 8192 shots: P(000) = 0.47, P(111) = 0.45, P(001) = 0.021`

/** Paper reproducibility checker: a figure, or its caption and OpenQASM; the circuit rebuilt and re-run exactly; each
 *  claimed number judged against its error bar. */
export function ReproducePanel({ live, onOpen }: { live: boolean; onOpen?: (s: CircuitSpec) => void }) {
  const [text, setText] = useState('')
  const [photo, setPhoto] = useState<{ blob: Blob; url: string; name: string } | null>(null)
  const [r, setR] = useState<Reproduction | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const run = async () => {
    setBusy(true); setError(null); setR(null)
    try { setR(await api.reproduce(text, photo?.blob ?? null)) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'The check failed.') }
    finally { setBusy(false) }
  }
  const max = r ? Math.max(0.01, ...r.claims.map((c) => Math.max(c.claimed, c.ideal, c.noisy ?? 0))) : 1
  return (
    <div className="panel reproduce">
      <div className="panel-head">
        <h2>Reproduce a paper</h2>
        <span className="sub">one figure, re-run exactly</span>
      </div>
      <textarea className="mission-goal" rows={3} value={text} onChange={(e) => setText(e.target.value)} disabled={busy}
        placeholder="Paste a caption with the claimed numbers (P(00) = 0.48 …) and, if you have it, the OpenQASM; or add the figure" aria-label="Caption and code" />
      <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) { if (photo) URL.revokeObjectURL(photo.url); setPhoto({ blob: f, url: URL.createObjectURL(f), name: f.name }) }
          e.target.value = ''
        }} />
        <button className="btn" onClick={() => fileRef.current?.click()} disabled={busy || !live} title={live ? '' : 'Reading a figure needs the Meta key'}>{photo ? 'Change figure' : 'Add the figure'}</button>
        <button className="chip-btn" onClick={() => setText(SAMPLE)} disabled={busy}>Sample caption and code</button>
        <span className="spacer" />
        <button className="btn primary" onClick={() => { void run() }} disabled={busy || (!text.trim() && !photo)}>{busy ? 'Checking…' : 'Check the claims'}</button>
      </div>
      {photo && (
        <div className="mission-photo"><img src={photo.url} alt="The figure to check" /><span className="sub">{photo.name}</span>
          <button className="chip-btn" onClick={() => { URL.revokeObjectURL(photo.url); setPhoto(null) }} disabled={busy}>Remove</button></div>
      )}
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {r && (
        <div className="est-result">
          <div className="row wrap" style={{ gap: 8, alignItems: 'baseline' }}>
            <span className={`est-verdict ${r.verdict === 'reproduced' ? 'ok' : 'warn'}`}>{r.verdict}</span>
            <span className="sub">read from: {r.read_from}</span>
            {r.calls.map((c, i) => <CallBadge key={i} call={c} />)}
          </div>
          <p className="mission-headline" style={{ marginTop: 8 }}>{r.headline}</p>
          <div className="mini-tiles">
            <span><b>{r.claims.length}</b> claims</span>
            {r.shots > 0 && <span><b>{r.shots.toLocaleString()}</b> shots</span>}
            {r.hardware && <span><b>{r.hardware}</b></span>}
            <span><b>{r.bit_order === 'q0_leftmost' ? 'q0 on the left' : 'q0 on the right'}</b>{r.bit_order_inferred ? ' (inferred: it fits better)' : ''}</span>
            {r.tvd_to_ideal !== null && <span><b>{r.tvd_to_ideal.toFixed(3)}</b> distance from the ideal odds</span>}
          </div>
          {r.notes && <p className="sub">{r.notes}</p>}
          {r.claims.length > 0 && (
            <div className="repro-grid">
              {r.claims.map((c) => (
                <div key={c.outcome} className="repro-row">
                  <span className="mono">{c.outcome}</span>
                  <svg viewBox="0 0 300 30" width="100%" height={30} preserveAspectRatio="none" aria-label={`${c.outcome}: claimed ${c.claimed}, ideal ${c.ideal}${c.noisy !== null ? `, realistic ${c.noisy}` : ''}`}>
                    <rect x={0} y={4} width={300 * c.claimed / max} height={9} rx={2} fill="var(--text-2)" />
                    <rect x={0} y={16} width={300 * c.ideal / max} height={9} rx={2} fill="var(--primary)" />
                    {c.noisy !== null && <line x1={300 * c.noisy / max} x2={300 * c.noisy / max} y1={14} y2={27} stroke="var(--predicted)" strokeWidth={2.5} />}
                  </svg>
                  <span className={`repro-verdict ${c.ok ? 'ok' : 'bad'}`}>{c.ok ? '✓' : '⚠'} {c.claimed.toFixed(3)} vs {c.ideal.toFixed(3)} · {c.verdict} (±{c.tolerance.toFixed(3)})</span>
                </div>
              ))}
              <div className="row wrap legend" style={{ gap: 14 }}>
                <span className="sub"><svg width={14} height={8} aria-hidden><rect width={14} height={8} rx={2} fill="var(--text-2)" /></svg> claimed in the paper</span>
                <span className="sub"><svg width={14} height={8} aria-hidden><rect width={14} height={8} rx={2} fill="var(--primary)" /></svg> exact re-run, ideal</span>
                <span className="sub"><svg width={4} height={10} aria-hidden><rect width={3} height={10} fill="var(--predicted)" /></svg> exact re-run, realistic noise</span>
              </div>
            </div>
          )}
          <div className="disc-circuit">
            <div className="row" style={{ marginBottom: 6 }}><b>The circuit as rebuilt</b><span className="spacer" />
              {onOpen && <button className="btn small" onClick={() => onOpen(r.spec as unknown as CircuitSpec)}>Open in the editor</button>}</div>
            <CircuitPreview spec={r.spec as unknown as CircuitSpec} highlight={null} onPick={() => {}} />
          </div>
        </div>
      )}
    </div>
  )
}
