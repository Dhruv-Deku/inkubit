import type { CircuitResult, CircuitSpec, Explanation, ImageOut, ModelCall, NetworkResult, NetworkSpec } from '../types'
import { fmtRate, pct } from '../util'
import { CallBadge, CallsTable } from './CallBadge'
import { CodeViewer } from './CodeViewer'
import { Histogram } from './Histogram'
import { Check, Cross } from './Icons'
import { AskPanel } from './AskPanel'
import { ExportButtons, InsightsSection } from './Insights'
import { NetworkMap } from './NetworkMap'

const LANG_CODES: Record<string, string> = {
  English: 'en', Hindi: 'hi', Spanish: 'es', French: 'fr', German: 'de', Portuguese: 'pt', Japanese: 'ja',
  'Chinese (Simplified)': 'zh-Hans', Arabic: 'ar', Bengali: 'bn', Tamil: 'ta', Indonesian: 'id',
}

export function ExplanationPanel({ explanation }: { explanation?: Explanation }) {
  if (!explanation) return null
  return (
    <div className="panel explain">
      <div className="panel-head"><h2>What happened, in plain words</h2><span className="spacer" /><CallBadge call={explanation.call} /></div>
      {explanation.note && <div className="notice" style={{ marginBottom: 10 }}>{explanation.note}</div>}
      {explanation.text.split(/\n\s*\n/).map((p, i) => <p key={i} lang={LANG_CODES[explanation.language ?? 'English']} dir="auto">{p}</p>)}
    </div>
  )
}

export function Figures({ figs }: { figs: (ImageOut | undefined)[] }) {
  const list = figs.filter((f): f is ImageOut => !!f)
  if (!list.length) return null
  return (
    <div className="panel">
      <div className="panel-head"><h2>Diagrams</h2></div>
      <div className="figs" style={list.length === 1 ? { gridTemplateColumns: '1fr' } : undefined}>
        {list.map((f, i) => (
          <figure key={i} className="fig" style={{ margin: 0 }}>
            <img src={`data:${f.mime};base64,${f.image_b64}`} alt={f.caption} />
            <figcaption className="cap"><span>{f.caption}</span>{f.call && <CallBadge call={f.call} />}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  )
}

function Tile({ k, v, s, tone }: { k: string; v: string; s?: string; tone?: 'good' | 'bad' }) {
  return <div className="tile"><div className="k">{k}</div><div className={`v ${tone ?? ''}`}>{v}</div>{s && <div className="s">{s}</div>}</div>
}

export function CircuitResults({ result, sketchCalls, spec, jobId }: {
  result: CircuitResult; sketchCalls: ModelCall[]; spec: CircuitSpec; jobId: string
}) {
  const v = result.verdict
  const repairs = result.attempts.filter((a) => a.fix_summary).length
  const calls = [...sketchCalls, ...result.calls,
    ...(result.explanation ? [result.explanation.call] : []), ...(result.diagram?.call ? [result.diagram.call] : [])]
  return (
    <div className="stack">
      <div className="panel">
        <div className="verdict">
          <div className={`verdict-badge ${result.verified ? 'pass' : 'fail'}`}>
            {result.verified ? <Check /> : <Cross />}{result.verified ? 'Verified' : 'Not verified'}
          </div>
          <div className="sub" style={{ fontSize: 14, color: 'var(--text)', flex: 1 }}>{result.summary}</div>
          <a className="btn small" href={`/api/jobs/${jobId}/report`} download>Download report</a>
        </div>
        {v && (
          <div className="tiles">
            <Tile k="Distance from prediction" v={v.metrics.tvd.toFixed(3)} s={`limit ${v.metrics.tvd_threshold.toFixed(3)} (TVD)`}
              tone={v.metrics.tvd <= v.metrics.tvd_threshold ? 'good' : 'bad'} />
            <Tile k="Match to prediction" v={v.metrics.fidelity.toFixed(4)} s={`needs ≥ ${v.metrics.fidelity_threshold}`}
              tone={v.metrics.fidelity >= v.metrics.fidelity_threshold ? 'good' : 'bad'} />
            <Tile k="Match to noiseless ideal" v={v.metrics.fidelity_vs_ideal.toFixed(3)} s={`noise cost ${pct(1 - v.metrics.fidelity_vs_ideal)}`} />
            <Tile k="Attempts" v={String(result.attempts.length)} s={repairs ? `${repairs} repair${repairs > 1 ? 's' : ''}` : 'no repair needed'} />
          </div>
        )}
      </div>
      {v && (
        <div className="panel">
          <div className="panel-head"><h2>Outcomes</h2><span className="sub">{v.reason}</span></div>
          <Histogram predicted={v.expected} measured={v.measured} ideal={v.ideal} shots={v.metrics.shots} />
        </div>
      )}
      <ExplanationPanel explanation={result.explanation} />
      <AskPanel jobId={jobId} kind="circuit" />
      {result.insights && <InsightsSection spec={spec} ins={result.insights} />}
      <div className="panel">
        <div className="panel-head">
          <h2>Code</h2><span className="sub">standalone Qiskit; runs with <code>python file.py</code></span>
          <span className="spacer" /><span className="sub">Export</span><ExportButtons ins={result.insights} spec={spec} />
        </div>
        <CodeViewer attempts={result.attempts} finalCode={result.final_code} />
      </div>
      <Figures figs={[result.exact_diagram,
        // an offline "illustration" is the same Qiskit drawing; only show a real Muse Image one next to it
        result.diagram?.call?.provider === 'meta' || !result.exact_diagram ? result.diagram : undefined]} />
      <div className="panel">
        <div className="panel-head"><h2>Models used</h2><span className="sub">every result says where it came from</span></div>
        <CallsTable calls={calls} />
      </div>
    </div>
  )
}

function E2E({ title, m, other }: { title: string; m: NetworkResult['before']; other?: NetworkResult['before'] | null }) {
  const e = m.end_to_end
  const better = (a: number, b?: number) => (b === undefined ? undefined : a > b ? 'good' as const : undefined)
  return (
    <div className="panel" style={{ flex: 1 }}>
      <div className="panel-head"><h2>{title}</h2></div>
      <div className="tiles" style={{ gridTemplateColumns: 'repeat(2, 1fr)', marginTop: 0 }}>
        <Tile k="Entangled pairs delivered" v={fmtRate(e.pair_rate_hz, 'pairs/s')} tone={better(e.pair_rate_hz, other?.end_to_end.pair_rate_hz)} />
        <Tile k="End-to-end fidelity" v={e.fidelity.toFixed(3)} tone={better(e.fidelity, other?.end_to_end.fidelity)} />
        <Tile k="Error rate (QBER)" v={pct(e.qber)} s={e.qber > 0.11 ? 'too high for a secret key' : undefined} />
        <Tile k="Secret key rate (BBM92)" v={fmtRate(e.key_rate_bps, 'bit/s')} tone={e.key_rate_bps <= 0 ? 'bad' : better(e.key_rate_bps, other?.end_to_end.key_rate_bps)} />
      </div>
    </div>
  )
}

export function NetworkResults({ result, sketchCalls, jobId, spec }: {
  result: NetworkResult; sketchCalls: ModelCall[]; jobId: string; spec: NetworkSpec
}) {
  const b = result.before, a = result.after
  const weak = b.weakest_link
  const calls = [...sketchCalls, ...(result.explanation ? [result.explanation.call] : []), ...(result.diagram?.call ? [result.diagram.call] : [])]
  return (
    <div className="stack">
      <div className="panel">
        <div className="verdict">
          <div className={`verdict-badge ${result.fix ? 'pass' : 'fail'}`}>{result.fix ? <Check /> : <Cross />}{result.fix ? 'Bottleneck fixed' : 'No better design found'}</div>
          <div className="sub" style={{ fontSize: 14, color: 'var(--text)', flex: 1 }}>{result.summary}</div>
          <a className="btn small" href={`/api/jobs/${jobId}/report`} download>Download report</a>
        </div>
      </div>
      <NetworkMap spec={spec} specAfter={result.spec_after} before={b} after={a} />
      <div className="row" style={{ alignItems: 'stretch', gap: 16 }}>
        <E2E title="Before" m={b} />
        {a && <E2E title="After the fix" m={a} other={b} />}
      </div>
      <div className="panel">
        <div className="panel-head"><h2>Links</h2>{weak && <span className="badge warn">weakest: {weak.from} → {weak.to}</span>}<span className="sub">{weak?.reason}</span></div>
        <table className="data">
          <thead><tr><th>Link</th><th>Medium</th><th className="num">Length</th><th className="num">Loss</th><th className="num">Photon arrives</th><th className="num">Pairs/s on link</th><th className="num">Link fidelity</th></tr></thead>
          <tbody>
            {b.links.map((l) => {
              const isWeak = weak && weak.from === l.from && weak.to === l.to
              return (
                <tr key={`${l.from}-${l.to}`} className={isWeak ? 'weak' : ''}>
                  <td>{l.from} → {l.to} {isWeak && <span className="badge warn">weakest</span>}</td>
                  <td>{l.medium.replace('_', ' ')}</td>
                  <td className="num">{l.length_km.toLocaleString()} km</td>
                  <td className="num">{l.loss_db.toFixed(1)} dB</td>
                  <td className="num">{l.success_prob < 1e-3 ? l.success_prob.toExponential(1) : pct(l.success_prob, 2)}</td>
                  <td className="num">{fmtRate(l.pair_rate_hz, '')}</td>
                  <td className="num">{l.fidelity.toFixed(3)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {result.candidates.length > 0 && (
        <div className="panel">
          <div className="panel-head"><h2>Fixes the agent tried</h2><span className="sub">each one re-simulated; the best one per round is applied</span></div>
          <table className="data">
            <thead><tr><th>Round</th><th>Fix</th><th className="num">Pairs/s</th><th className="num">Fidelity</th><th className="num">Key rate</th></tr></thead>
            <tbody>
              {result.candidates.map((c, i) => (
                <tr key={i} className={c.applied ? 'chosen' : ''}>
                  <td className="muted">{c.round}</td>
                  <td>{c.description} {c.applied && <span className="badge pass">applied</span>}</td>
                  <td className="num">{fmtRate(c.pair_rate_hz, '')}</td>
                  <td className="num">{c.fidelity.toFixed(3)}</td>
                  <td className="num">{fmtRate(c.key_rate_bps, 'bit/s')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ExplanationPanel explanation={result.explanation} />
      <AskPanel jobId={jobId} kind="network" />
      <Figures figs={[result.diagram]} />
      {result.checks.length > 0 && (
        <div className="panel">
          <div className="panel-head"><h2>Sanity checks</h2></div>
          {result.checks.map((c, i) => (
            <div key={i} className="row" style={{ padding: '4px 0' }}>{c.passed ? <Check /> : <Cross />}<span>{c.name}</span><span className="sub">{c.detail}</span></div>
          ))}
        </div>
      )}
      {calls.length > 0 && <div className="panel"><div className="panel-head"><h2>Models used</h2></div><CallsTable calls={calls} /></div>}
    </div>
  )
}
