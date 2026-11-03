import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ChemLab, CircuitSpec, QkdLab } from '../types'

const mha = (e: number) => `${(e * 1000).toFixed(1)} mHa`

// ---------------------------------------------------------------- chemistry: H2 with VQE

export function EnergyChart({ lab, onPick }: { lab: ChemLab; onPick: (r: number) => void }) {
  const W = 620, H = 290, L = 54, R = 16, T = 14, B = 38
  const pts = lab.curve
  const rMin = 0.3, rMax = 3.0
  const eMin = Math.min(...pts.map((p) => p.exact)) - 0.03
  const eMax = Math.max(...pts.map((p) => Math.min(p.hf, -0.45)))
  const x = (r: number) => L + ((r - rMin) / (rMax - rMin)) * (W - L - R)
  const y = (e: number) => T + ((eMax - Math.min(eMax, e)) / (eMax - eMin)) * (H - T - B)
  const line = (k: 'hf' | 'exact') => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.r).toFixed(1)} ${y(p[k]).toFixed(1)}`).join('')
  const [hover, setHover] = useState<number | null>(null)
  const hp = hover !== null ? pts[hover] : null
  const ticksE = [-1.1, -0.9, -0.7, -0.5].filter((v) => v >= eMin && v <= eMax)
  return (
    <div>
      <div className="sub mono qaoa-readout" aria-live="polite">
        {hp ? `${hp.r.toFixed(2)} Å · exact ${hp.exact.toFixed(4)} · Hartree-Fock ${hp.hf.toFixed(4)} · VQE ${hp.vqe.toFixed(4)} raw, ${hp.mitigated.toFixed(4)} mitigated · click to inspect`
          : 'energy as the bond stretches (Hartree, lower is more stable) · click a bond length'}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block', cursor: 'crosshair' }} role="img"
        aria-label="Energy of H2 against bond length: Hartree-Fock rises too high as the bond breaks; VQE with mitigation follows the exact curve"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect()
          const r = rMin + ((((e.clientX - box.left) / box.width) * W - L) / (W - L - R)) * (rMax - rMin)
          let best = 0
          pts.forEach((p, i) => { if (Math.abs(p.r - r) < Math.abs(pts[best].r - r)) best = i })
          setHover(best)
        }}
        onClick={() => hover !== null && onPick(pts[hover].r)}>
        {ticksE.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--line)" />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{v.toFixed(1)}</text>
          </g>
        ))}
        {[0.5, 1, 1.5, 2, 2.5, 3].map((v) => (
          <text key={v} x={x(v)} y={H - B + 16} textAnchor="middle" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{v}</text>
        ))}
        <text x={W - R} y={H - 4} textAnchor="end" fontSize={11} fill="var(--text-2)">bond length, Å →</text>
        <line x1={x(lab.r)} x2={x(lab.r)} y1={T} y2={H - B} stroke="var(--text-2)" strokeDasharray="2 4" />
        {hp && <line x1={x(hp.r)} x2={x(hp.r)} y1={T} y2={H - B} stroke="var(--line-2)" />}
        <path d={line('hf')} fill="none" stroke="var(--predicted)" strokeWidth={2} strokeDasharray="6 4" />
        <path d={line('exact')} fill="none" stroke="var(--text)" strokeWidth={2} />
        {pts.map((p) => (
          <g key={p.r}>
            <circle cx={x(p.r)} cy={y(p.vqe)} r={3.2} fill="var(--panel)" stroke="var(--text-2)" strokeWidth={1.3} />
            <line x1={x(p.r)} x2={x(p.r)} y1={y(p.mitigated - p.mitigated_err)} y2={y(p.mitigated + p.mitigated_err)} stroke="var(--primary)" strokeWidth={1.5} />
            <circle cx={x(p.r)} cy={y(p.mitigated)} r={3.4} fill="var(--primary)" stroke="var(--panel)" strokeWidth={1} />
          </g>
        ))}
        <text x={x(2.95)} y={y(pts[pts.length - 1].hf) - 8} textAnchor="end" fontSize={11} fill="var(--predicted)">Hartree-Fock</text>
        <text x={x(2.95)} y={y(pts[pts.length - 1].exact) + 18} textAnchor="end" fontSize={11} fill="var(--text)">exact</text>
      </svg>
      <div className="row wrap legend" style={{ gap: 14 }}>
        <span className="sub"><svg width={20} height={10} aria-hidden><line x1={1} x2={19} y1={5} y2={5} stroke="var(--text)" strokeWidth={2} /></svg> exact (full CI)</span>
        <span className="sub"><svg width={20} height={10} aria-hidden><line x1={1} x2={19} y1={5} y2={5} stroke="var(--predicted)" strokeWidth={2} strokeDasharray="5 3" /></svg> Hartree-Fock (classical shortcut)</span>
        <span className="sub"><svg width={10} height={10} aria-hidden><circle cx={5} cy={5} r={3.5} fill="none" stroke="var(--text-2)" strokeWidth={1.3} /></svg> VQE, {lab.noise_label.toLowerCase()} noise</span>
        <span className="sub"><svg width={10} height={10} aria-hidden><circle cx={5} cy={5} r={4} fill="var(--primary)" /></svg> VQE, noise undone (±1σ)</span>
      </div>
    </div>
  )
}

function Molecule({ lab }: { lab: ChemLab }) {
  const W = 260, H = 120
  const sep = Math.min(200, 30 + lab.r * 60)
  const cx = W / 2
  const g = 1 - lab.weight_u
  return (
    <div className="chem-mol">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block', margin: '0 auto' }} role="img"
        aria-label={`Two hydrogen atoms ${lab.r.toFixed(2)} angstrom apart`}>
        <ellipse cx={cx} cy={55} rx={sep / 2 + 26} ry={30} fill="var(--primary)" fillOpacity={0.08 + 0.22 * g} />
        <line x1={cx - sep / 2} x2={cx + sep / 2} y1={55} y2={55} stroke="var(--text-2)" strokeOpacity={0.4 + 0.5 * g} strokeWidth={2} strokeDasharray={g < 0.75 ? '4 4' : undefined} />
        {[-1, 1].map((s) => (
          <g key={s}>
            <circle cx={cx + (s * sep) / 2} cy={55} r={15} fill="var(--panel-3)" stroke="var(--text)" strokeWidth={1.5} />
            <text x={cx + (s * sep) / 2} y={60} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--text)">H</text>
          </g>
        ))}
        <text x={cx} y={108} textAnchor="middle" fontSize={11} fill="var(--text-2)" fontFamily="var(--mono)">{lab.r.toFixed(2)} Å</text>
      </svg>
      <div className="chem-mix" title="The exact state, as a mix of the two configurations">
        <span style={{ width: `${g * 100}%` }} className="g" />
        <span style={{ width: `${lab.weight_u * 100}%` }} className="u" />
      </div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="sub">both electrons bonding {Math.round(g * 100)}%</span>
        <span className="sub">antibonding {Math.round(lab.weight_u * 100)}%</span>
      </div>
    </div>
  )
}

export function ChemLabPanel({ onOpen }: { onOpen?: (spec: CircuitSpec) => void }) {
  const [r, setR] = useState(0.74)
  const [lab, setLab] = useState<ChemLab | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const ctl = new AbortController()
    const t = setTimeout(() => {
      api.chemLab(r, ctl.signal).then((d) => { setLab(d); setError(null) }).catch((e: Error) => { if (!ctl.signal.aborted) setError(e.message) })
    }, 120)
    return () => { clearTimeout(t); ctl.abort() }
  }, [r])
  const acc = lab ? Math.abs(lab.mitigated - lab.exact) < 0.0016 : false
  return (
    <div className="panel" id="uc-chem">
      <div className="panel-head">
        <h2>Molecule lab: H₂</h2>
        <span className="sub">first principles, with VQE</span>
        <span className="spacer" />
        {onOpen && lab && <button className="btn small" onClick={() => onOpen(lab.spec as CircuitSpec)}>Open the VQE circuit</button>}
      </div>
      <div className="row wrap" style={{ gap: 10, marginBottom: 10 }}>
        <span className="label">Bond length</span>
        <input type="range" min={0.3} max={3} step={0.05} value={r} onChange={(e) => setR(Number(e.target.value))} aria-label="Bond length in angstrom" style={{ flex: 1, minWidth: 160 }} />
        <span className="mono sub" style={{ minWidth: 60 }}>{r.toFixed(2)} Å</span>
        <button className="chip-btn" onClick={() => setR(0.74)}>equilibrium</button>
        <button className="chip-btn" onClick={() => setR(2.5)}>pull apart</button>
      </div>
      {error && <div className="notice error">{error}</div>}
      {lab && (
        <>
          <div className="chem-grid">
            <EnergyChart lab={lab} onPick={(v) => setR(v)} />
            <Molecule lab={lab} />
          </div>
          <div className="tiles">
            <div className="tile"><div className="k">Exact energy</div><div className="v">{lab.exact.toFixed(4)}</div><div className="s">Hartree · full CI</div></div>
            <div className="tile"><div className="k">Hartree-Fock</div><div className={`v ${lab.hf - lab.exact > 0.0016 ? 'bad' : ''}`}>+{mha(lab.hf - lab.exact)}</div><div className="s">too high: misses the correlation</div></div>
            <div className="tile"><div className="k">VQE, raw</div><div className="v">{lab.vqe.toFixed(4)}</div><div className="s">± {lab.vqe_err.toFixed(4)} · {mha(lab.vqe - lab.exact)} off</div></div>
            <div className="tile"><div className="k">VQE, noise undone</div><div className={`v ${acc ? 'good' : ''}`}>{lab.mitigated.toFixed(4)}</div>
              <div className="s">± {lab.mitigated_err.toFixed(4)} · {acc ? '✓ chemical accuracy' : `${mha(Math.abs(lab.mitigated - lab.exact))} off`}</div></div>
          </div>
          <p className="lead" style={{ margin: '12px 0 0' }}>{lab.summary}</p>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- security: BB84, catch the spy

export function QberChart({ lab }: { lab: QkdLab }) {
  const W = 380, H = 210, L = 40, R = 12, T = 12, B = 34
  const top = 0.3
  const x = (f: number) => L + f * (W - L - R)
  const y = (q: number) => T + (1 - Math.min(q, top) / top) * (H - T - B)
  const path = lab.curve.map(([f, q], i) => `${i ? 'L' : 'M'}${x(f).toFixed(1)} ${y(q).toFixed(1)}`).join('')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block' }} role="img"
      aria-label={`Error rate ${(lab.qber * 100).toFixed(1)} percent with Eve on ${(lab.eve * 100).toFixed(0)} percent of photons; abort above 11 percent`}>
      {[0, 0.1, 0.2, 0.3].map((v) => (
        <g key={v}>
          <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--line)" />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{v * 100}%</text>
        </g>
      ))}
      <rect x={L} y={y(top)} width={W - L - R} height={y(0.11) - y(top)} fill="var(--fail)" fillOpacity={0.07} />
      <line x1={L} x2={W - R} y1={y(0.11)} y2={y(0.11)} stroke="var(--fail)" strokeDasharray="5 4" />
      <text x={W - R - 4} y={y(0.11) - 6} textAnchor="end" fontSize={10.5} fill="#ff8a8d">abort above 11%</text>
      <path d={path} fill="none" stroke="var(--text-2)" strokeWidth={1.5} strokeDasharray="4 3" />
      {[0, 0.5, 1].map((v) => <text key={v} x={x(v)} y={H - B + 16} textAnchor="middle" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{v * 100}%</text>)}
      <text x={W - R} y={H - 4} textAnchor="end" fontSize={11} fill="var(--text-2)">photons Eve measures →</text>
      <line x1={x(lab.eve)} x2={x(lab.eve)} y1={y(Math.max(0, lab.qber - 2 * lab.qber_err))} y2={y(lab.qber + 2 * lab.qber_err)} stroke="var(--text)" strokeWidth={2} />
      <circle cx={x(lab.eve)} cy={y(lab.qber)} r={6} fill={lab.caught ? 'var(--fail)' : 'var(--pass)'} stroke="var(--panel)" strokeWidth={2} />
    </svg>
  )
}

export function QkdLabPanel({ onOpen }: { onOpen?: (spec: CircuitSpec) => void }) {
  const [eve, setEve] = useState(0)
  const [noise, setNoise] = useState(0.01)
  const [photons, setPhotons] = useState(1000)
  const [seed, setSeed] = useState(7)
  const [lab, setLab] = useState<QkdLab | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const ctl = new AbortController()
    const t = setTimeout(() => {
      api.qkdLab({ photons, eve, noise, seed }, ctl.signal).then((d) => { setLab(d); setError(null) })
        .catch((e: Error) => { if (!ctl.signal.aborted) setError(e.message) })
    }, 60)
    return () => { clearTimeout(t); ctl.abort() }
  }, [eve, noise, photons, seed])
  return (
    <div className="panel" id="uc-qkd">
      <div className="panel-head">
        <h2>Catch the spy</h2>
        <span className="sub">BB84 key distribution</span>
        <span className="spacer" />
        {onOpen && lab && <button className="btn small" onClick={() => onOpen(lab.spec as CircuitSpec)}>Open photon 1 as a circuit</button>}
      </div>
      <div className="qkd-controls">
        <label className="row" style={{ gap: 10 }}><span className="label" style={{ minWidth: 92 }}>Eve listens to</span>
          <input type="range" min={0} max={1} step={0.05} value={eve} onChange={(e) => setEve(Number(e.target.value))} aria-label="Share of photons Eve measures" style={{ flex: 1 }} />
          <span className="mono sub" style={{ minWidth: 44 }}>{Math.round(eve * 100)}%</span></label>
        <label className="row" style={{ gap: 10 }}><span className="label" style={{ minWidth: 92 }}>Channel noise</span>
          <input type="range" min={0} max={0.05} step={0.005} value={noise} onChange={(e) => setNoise(Number(e.target.value))} aria-label="Channel error rate" style={{ flex: 1 }} />
          <span className="mono sub" style={{ minWidth: 44 }}>{(noise * 100).toFixed(1)}%</span></label>
        <div className="row wrap" style={{ gap: 8 }}>
          <div className="seg">{[200, 1000, 10000].map((n) => <button key={n} className={photons === n ? 'on' : ''} onClick={() => setPhotons(n)}>{n.toLocaleString()} photons</button>)}</div>
          <button className="chip-btn" onClick={() => setSeed((s) => s + 1)}>Send again</button>
        </div>
      </div>
      {error && <div className="notice error">{error}</div>}
      {lab && (
        <>
          <div className="qkd-grid">
            <div className="qkd-table-wrap">
              <table className="qkd-table mono" aria-label="The first 20 photons">
                <tbody>
                  <tr><th>Alice bit</th>{lab.shown.map((p, i) => <td key={i} className={p.kept ? 'kept' : ''}>{p.bit}</td>)}</tr>
                  <tr><th>Alice basis</th>{lab.shown.map((p, i) => <td key={i} className={p.kept ? 'kept' : ''}>{p.basis === '+' ? '+' : '×'}</td>)}</tr>
                  <tr className="eve"><th>Eve</th>{lab.shown.map((p, i) => <td key={i} className={p.kept ? 'kept' : ''}>{p.eve ? (p.eve === '+' ? '+' : '×') : '·'}</td>)}</tr>
                  <tr><th>Bob basis</th>{lab.shown.map((p, i) => <td key={i} className={p.kept ? 'kept' : ''}>{p.bob_basis === '+' ? '+' : '×'}</td>)}</tr>
                  <tr><th>Bob bit</th>{lab.shown.map((p, i) => <td key={i} className={`${p.kept ? 'kept' : ''} ${p.error ? 'err' : ''}`}>{p.bob_bit}</td>)}</tr>
                  <tr><th>Key</th>{lab.shown.map((p, i) => <td key={i} className={p.kept ? 'kept' : ''}>{p.kept ? (p.error ? '✗' : '✓') : ''}</td>)}</tr>
                </tbody>
              </table>
              <div className="sub" style={{ marginTop: 6 }}>First 20 photons. Highlighted: bases matched, so the bit is kept. ✗: Bob read the wrong bit. Eve: · lets it pass, + or × measures it.</div>
            </div>
            <QberChart lab={lab} />
          </div>
          <div className="tiles">
            <div className="tile"><div className="k">Kept after comparing bases</div><div className="v">{lab.sifted.toLocaleString()}</div><div className="s">of {lab.photons.toLocaleString()} photons</div></div>
            <div className="tile"><div className="k">Error rate seen</div><div className={`v ${lab.caught ? 'bad' : ''}`}>{(lab.qber * 100).toFixed(1)}%</div>
              <div className="s">± {(lab.qber_err * 100).toFixed(1)}% · from {lab.checked.toLocaleString()} revealed bits</div></div>
            <div className="tile"><div className="k">Verdict</div><div className={`v ${lab.caught ? 'bad' : 'good'}`}>{lab.caught ? 'Spy caught' : 'Key kept'}</div>
              <div className="s">{lab.caught ? 'above 11%: abort' : 'below 11%'}</div></div>
            <div className="tile"><div className="k">Secret key</div><div className="v">{lab.key_bits.toLocaleString()} bits</div>
              <div className="s">{lab.eve > 0 && !lab.caught ? `Eve guessed ${(lab.eve_knows * 100).toFixed(0)}%, erased by privacy amplification` : 'after error correction and privacy amplification'}</div></div>
          </div>
          <p className="lead" style={{ margin: '12px 0 0' }}>{lab.summary}</p>
        </>
      )}
    </div>
  )
}
