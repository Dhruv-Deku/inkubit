import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { BellResult, BellTest, RepetitionLab, Tomography } from '../types'
import { pct } from '../util'

// ---------------------------------------------------------------- Bell test

/** A number line from 0 to the quantum maximum: the classical zone, and where the ideal, noisy and measured values land. */
function BellScale({ t }: { t: BellResult }) {
  const W = 520, H = 52, L = 12, R = 12
  const shot = t.shots_value
  const low = Math.min(t.ideal, t.noisy ?? Infinity, shot !== null && t.shots_error !== null ? shot - 2 * t.shots_error : Infinity)
  const min = Math.max(0, Math.min(1, Math.floor(low * 2) / 2 - 0.25))
  const max = t.quantum_bound * 1.04
  const x = (v: number) => L + ((Math.max(min, v) - min) / (max - min)) * (W - L - R)
  const y = 20
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W, display: 'block' }} role="img"
      aria-label={`${t.kind} value ${t.ideal.toFixed(3)} ideal; classical limit ${t.classical_bound}; quantum maximum ${t.quantum_bound.toFixed(3)}`}>
      <rect x={x(min)} y={y - 7} width={x(t.classical_bound) - x(min)} height={14} rx={4} fill="var(--panel-3)" />
      <rect x={x(t.classical_bound)} y={y - 7} width={x(t.quantum_bound) - x(t.classical_bound)} height={14} rx={4}
        fill="var(--gold)" fillOpacity={0.1} stroke="var(--gold)" strokeOpacity={0.35} />
      <text x={x(t.classical_bound) - 6} y={y + 26} textAnchor="end" fontSize={10.5} fill="var(--muted)">← classical physics can explain</text>
      <text x={x(t.classical_bound) + 6} y={y + 26} fontSize={10.5} fill="var(--gold)" fillOpacity={0.8}>only quantum →</text>
      <line x1={x(t.classical_bound)} x2={x(t.classical_bound)} y1={y - 12} y2={y + 12} stroke="var(--text-2)" />
      <text x={x(t.classical_bound)} y={y - 11} textAnchor="middle" fontSize={10.5} fill="var(--text-2)" fontFamily="var(--mono)">{t.classical_bound}</text>
      <text x={x(t.quantum_bound)} y={y - 11} textAnchor="end" fontSize={10.5} fill="var(--text-2)" fontFamily="var(--mono)">max {t.quantum_bound.toFixed(2)}</text>
      <text x={x(min)} y={y - 11} fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{min}</text>
      {shot !== null && t.shots_error !== null && (
        <g>
          <line x1={x(shot - 2 * t.shots_error)} x2={x(shot + 2 * t.shots_error)} y1={y} y2={y} stroke="var(--gold)" strokeWidth={2} />
          <circle cx={x(shot)} cy={y} r={5} fill="var(--gold)" stroke="var(--panel)" strokeWidth={1.5}><title>{`with shots: ${shot.toFixed(3)} ± ${t.shots_error.toFixed(3)}`}</title></circle>
        </g>
      )}
      {t.noisy !== null && <rect x={x(t.noisy) - 4} y={y - 4} width={8} height={8} transform={`rotate(45 ${x(t.noisy)} ${y})`} fill="var(--text-2)"><title>{`realistic noise, exact: ${t.noisy.toFixed(3)}`}</title></rect>}
      <circle cx={x(t.ideal)} cy={y} r={6} fill="none" stroke="var(--text)" strokeWidth={2}><title>{`ideal: ${t.ideal.toFixed(3)}`}</title></circle>
    </svg>
  )
}

const vec = (v: number[]) => `(${v.map((c) => (Math.abs(c) < 5e-4 ? '0' : c.toFixed(2))).join(', ')})`

export function BellPanel({ bell }: { bell: BellTest }) {
  return (
    <div className="panel">
      <div className="panel-head"><h2>Bell test</h2><span className="sub">could any classical explanation fake these correlations?</span></div>
      <p className="lead">{bell.summary}</p>
      {bell.tests.map((t) => (
        <div key={`${t.kind}-${t.qubits.join('')}`} className="bell-row">
          <div className="row wrap" style={{ gap: 8, marginBottom: 4 }}>
            <strong>{t.kind}</strong>
            <span className="mono sub">{t.qubits.map((q) => `q${q}`).join(', ')}</span>
            <span className={`badge ${t.violates ? 'gold-badge' : 'mock'}`}>{t.violates ? 'beats classical physics' : 'within classical limits'}</span>
            <span className="spacer" />
            <span className="sub mono">
              ideal {t.ideal.toFixed(3)}
              {t.noisy !== null && <> · noisy {t.noisy.toFixed(3)}</>}
              {t.shots_value !== null && t.shots_error !== null && <> · <span className="gold">{t.shots_value.toFixed(3)} ± {t.shots_error.toFixed(3)}</span></>}
            </span>
          </div>
          <BellScale t={t} />
          <div className="sub" style={{ marginTop: 2 }}>{t.verdict}</div>
          <details className="sub" style={{ marginTop: 4 }}>
            <summary>Measurement settings (Bloch-sphere directions)</summary>
            <div className="mono" style={{ marginTop: 4 }}>
              {t.settings.map((pair, k) => (
                <div key={k}>q{t.qubits[k]}: {vec(pair[0])} or {vec(pair[1])}</div>
              ))}
            </div>
          </details>
        </div>
      ))}
      <div className="row wrap legend" style={{ gap: 14, marginTop: 8 }}>
        <span className="sub"><svg width={14} height={14} aria-hidden><circle cx={7} cy={7} r={5} fill="none" stroke="var(--text)" strokeWidth={2} /></svg> ideal</span>
        <span className="sub"><svg width={14} height={14} aria-hidden><rect x={3} y={3} width={8} height={8} transform="rotate(45 7 7)" fill="var(--text-2)" /></svg> realistic noise, exact</span>
        <span className="sub"><svg width={22} height={14} aria-hidden><line x1={1} x2={21} y1={7} y2={7} stroke="var(--gold)" strokeWidth={2} /><circle cx={11} cy={7} r={4.5} fill="var(--gold)" /></svg> measured: {bell.tests[0]?.shots.toLocaleString() ?? 0} shots per setting, readout error included (bar: ±2 standard errors)</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- tomography

const C30 = Math.cos(Math.PI / 6), S30 = 0.5

/** Isometric 3D bars of a density matrix ("cityscape"): one bar per entry, height = value. */
function Cityscape({ m, n, scale, title }: { m: number[][]; n: number; scale: number; title: string }) {
  const N = m.length
  const c = N <= 2 ? 34 : N <= 4 ? 26 : 19
  const H = 92 / scale
  const w = 0.72, gap = (1 - w) / 2
  const P = (x: number, y: number, z: number): [number, number] => [(x - y) * C30 * c, (x + y) * S30 * c - z * H]
  const pts = (arr: [number, number][]) => arr.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(' ')
  const ox = N * C30 * c + 24, oy = 100
  const width = 2 * N * C30 * c + 48, height = N * c + 140
  const cells: { i: number; j: number; v: number }[] = []
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) cells.push({ i, j, v: m[i][j] })
  cells.sort((a, b) => a.i + a.j - (b.i + b.j))
  const label = (k: number) => k.toString(2).padStart(n, '0')
  return (
    <figure className="city">
      <figcaption className="label">{title}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" style={{ maxWidth: width, display: 'block' }} role="img"
        aria-label={`${title}: largest entries ${cells.filter((x) => Math.abs(x.v) > 0.05).slice(0, 6).map((x) => `|${label(x.i)}⟩⟨${label(x.j)}| ${x.v.toFixed(2)}`).join(', ')}`}>
        <g transform={`translate(${ox},${oy})`}>
          <polygon points={pts([P(0, 0, 0), P(N, 0, 0), P(N, N, 0), P(0, N, 0)])} fill="var(--panel-2)" stroke="var(--line-2)" />
          {Array.from({ length: N - 1 }, (_, k) => (
            <g key={k} stroke="var(--line)">
              <line x1={P(k + 1, 0, 0)[0]} y1={P(k + 1, 0, 0)[1]} x2={P(k + 1, N, 0)[0]} y2={P(k + 1, N, 0)[1]} />
              <line x1={P(0, k + 1, 0)[0]} y1={P(0, k + 1, 0)[1]} x2={P(N, k + 1, 0)[0]} y2={P(N, k + 1, 0)[1]} />
            </g>
          ))}
          {cells.map(({ i, j, v }) => {
            if (Math.abs(v) < 0.004) return null
            const x0 = j + gap, x1 = j + gap + w, y0 = i + gap, y1 = i + gap + w
            const lo = Math.min(0, v), hi = Math.max(0, v)
            const col = v >= 0 ? 'var(--measured)' : 'var(--text-2)'
            return (
              <g key={`${i}-${j}`} className="bar3d">
                <polygon points={pts([P(x0, y1, lo), P(x1, y1, lo), P(x1, y1, hi), P(x0, y1, hi)])} fill={col} fillOpacity={0.55} />
                <polygon points={pts([P(x1, y0, lo), P(x1, y1, lo), P(x1, y1, hi), P(x1, y0, hi)])} fill={col} fillOpacity={0.75} />
                <polygon points={pts([P(x0, y0, hi), P(x1, y0, hi), P(x1, y1, hi), P(x0, y1, hi)])} fill={col} fillOpacity={1} />
                <title>{`⟨${label(i)}|ρ|${label(j)}⟩ = ${v.toFixed(3)}`}</title>
              </g>
            )
          })}
          {Array.from({ length: N }, (_, k) => {
            const [ax, ay] = P(k + 0.5, N, 0), [bx, by] = P(N, k + 0.5, 0)
            return (
              <g key={k} fontSize={N > 4 ? 9 : 10.5} fill="var(--muted)" fontFamily="var(--mono)">
                <text x={ax - 4} y={ay + 14} textAnchor="end">{label(k)}</text>
                <text x={bx + 4} y={by + 14}>{label(k)}</text>
              </g>
            )
          })}
        </g>
      </svg>
    </figure>
  )
}

export function TomographyPanel({ tomo }: { tomo: Tomography }) {
  const [part, setPart] = useState<'re' | 'im'>('re')
  const ideal = part === 're' ? tomo.ideal_re : tomo.ideal_im
  const recon = part === 're' ? tomo.recon_re : tomo.recon_im
  const scale = Math.max(0.25, ...[...tomo.ideal_re, ...tomo.recon_re, ...tomo.ideal_im, ...tomo.recon_im].flat().map(Math.abs))
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>State tomography</h2>
        <span className="sub">the state rebuilt from {(tomo.settings * tomo.shots_per_setting).toLocaleString()} measurement shots</span>
        <span className="spacer" />
        <div className="seg">
          <button className={part === 're' ? 'on' : ''} onClick={() => setPart('re')}>Real part</button>
          <button className={part === 'im' ? 'on' : ''} onClick={() => setPart('im')}>Imaginary part</button>
        </div>
      </div>
      <div className="tiles" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', marginTop: 0, marginBottom: 10 }}>
        <div className="tile"><div className="k">Fidelity with the intended state</div><div className="v">{tomo.fidelity_ideal.toFixed(3)}</div></div>
        <div className="tile"><div className="k">Perfect tomography would find</div><div className="v">{tomo.noisy_fidelity_ideal.toFixed(3)}</div><div className="s">the noise's share of the gap</div></div>
        <div className="tile"><div className="k">Purity</div><div className="v">{tomo.purity.toFixed(3)}</div><div className="s">1 = pure; noise mixes it</div></div>
      </div>
      <div className="city-pair">
        <Cityscape m={ideal} n={tomo.n} scale={scale} title="Intended state |ψ⟩⟨ψ|" />
        <Cityscape m={recon} n={tomo.n} scale={scale} title={`Rebuilt from ${tomo.settings} settings × ${tomo.shots_per_setting.toLocaleString()} shots`} />
      </div>
      <div className="row wrap" style={{ gap: 14, margin: '4px 0 8px' }}>
        <span className="sub"><span className="swatch" style={{ background: 'var(--measured)' }} /> positive entry</span>
        <span className="sub"><span className="swatch" style={{ background: 'var(--text-2)' }} /> negative entry</span>
        <span className="sub">Diagonal: how likely each basis state is. Off-diagonal: the coherence between them, which noise erodes.</span>
      </div>
      <p className="lead" style={{ marginBottom: 0 }}>{tomo.summary}</p>
    </div>
  )
}

// ---------------------------------------------------------------- error-correction lab

const labScale = (k: number) => (k <= 0 ? 0 : Math.pow(10, (k - 80) / 40))
const labScaleText = (s: number) => (s === 0 ? 'perfect gates' : Math.abs(s - 1) < 0.02 ? "today's gates" : s < 1 ? `gates ${(1 / s).toFixed(s > 0.1 ? 1 : 0)}x better` : `gates ${s.toFixed(1)}x worse`)

/** Bit-flip code against a bare qubit on log-log axes, with the break-even point. */
export function RepetitionLabPanel({ onTry }: { onTry?: () => void }) {
  const [k, setK] = useState(80)
  const [kind, setKind] = useState<'bit' | 'phase'>('bit')
  const [lab, setLab] = useState<RepetitionLab | null>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const scale = labScale(k)
  useEffect(() => {
    const ctl = new AbortController()
    const t = setTimeout(() => {
      api.repetitionLab(scale, ctl.signal).then((r) => { setLab(r); setError(null) })
        .catch((e: Error) => { if (!ctl.signal.aborted) setError(e.message) })
    }, 60)
    return () => { clearTimeout(t); ctl.abort() }
  }, [scale])
  const W = 640, Hh = 270, L = 52, R = 18, T = 14, B = 40
  const lx = (p: number) => L + ((Math.log10(p) + 4) / (Math.log10(0.5) + 4)) * (W - L - R)
  const yMin = 1e-8
  const ly = (v: number) => T + (-Math.log10(Math.max(v, yMin)) / 8) * (Hh - T - B)
  const curves = lab ? lab[kind] : null
  const path = (ys: number[]) => (lab ? ys.map((v, i) => `${i ? 'L' : 'M'}${lx(lab.p[i]).toFixed(1)} ${ly(v).toFixed(1)}`).join('') : '')
  const be = curves?.break_even ?? null
  const i = hover ?? (lab ? lab.p.findIndex((p) => p >= 0.01) : 0)
  const readout = useMemo(() => {
    if (!lab || !curves || i < 0) return null
    return { p: lab.p[i], perfect: curves.perfect[i], real: curves.realistic[i] }
  }, [lab, curves, i])
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Error-correction lab</h2>
        <span className="sub">protect one qubit with two copies: when does it pay off?</span>
        <span className="spacer" />
        <div className="seg">
          <button className={kind === 'bit' ? 'on' : ''} onClick={() => setKind('bit')}>Bit flips</button>
          <button className={kind === 'phase' ? 'on' : ''} onClick={() => setKind('phase')}>Phase flips</button>
        </div>
      </div>
      <div className="row wrap" style={{ gap: 10, marginBottom: 8 }}>
        <span className="label">Gate quality</span>
        <input type="range" min={0} max={120} value={k} onChange={(e) => setK(Number(e.target.value))} aria-label="Gate quality" style={{ flex: 1, minWidth: 160 }} />
        <span className="mono sub" style={{ minWidth: 150 }}>{labScaleText(scale)}</span>
        {onTry && <button className="btn small" onClick={onTry}>Try the code in the editor</button>}
      </div>
      {error && <div className="notice error">{error}</div>}
      {lab && curves && (
        <>
          <svg viewBox={`0 0 ${W} ${Hh}`} width="100%" style={{ maxWidth: W, display: 'block' }} role="img"
            aria-label={`Logical error against the physical ${kind}-flip rate. ${be ? `Break-even at ${pct(be, 2)}.` : 'The code never beats a bare qubit here.'}`}
            onMouseLeave={() => setHover(null)}
            onMouseMove={(e) => {
              const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
              const px = ((e.clientX - box.left) / box.width) * W
              let best = 0
              lab.p.forEach((p, j) => { if (Math.abs(lx(p) - px) < Math.abs(lx(lab.p[best]) - px)) best = j })
              setHover(best)
            }}>
            {[1, 1e-2, 1e-4, 1e-6, 1e-8].map((v) => (
              <g key={v}>
                <line x1={L} x2={W - R} y1={ly(v)} y2={ly(v)} stroke="var(--line)" />
                <text x={L - 6} y={ly(v) + 4} textAnchor="end" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{v >= 0.01 ? pct(v, 0) : v.toExponential(0)}</text>
              </g>
            ))}
            {[1e-4, 1e-3, 1e-2, 1e-1, 0.5].map((p) => (
              <text key={p} x={lx(p)} y={Hh - B + 16} textAnchor="middle" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">{p >= 0.01 ? pct(p, 0) : pct(p, p >= 0.001 ? 1 : 2)}</text>
            ))}
            <text x={(L + W - R) / 2} y={Hh - 4} textAnchor="middle" fontSize={11} fill="var(--muted)">chance each qubit gets a {kind} flip</text>
            {be && be > 1.0001e-4 && <rect x={lx(be)} y={T} width={W - R - lx(be)} height={Hh - T - B} fill="var(--pass)" fillOpacity={0.05} />}
            <path d={path(lab.bare)} fill="none" stroke="var(--text-2)" strokeWidth={1.6} strokeDasharray="5 4" />
            <path d={path(curves.perfect)} fill="none" stroke="var(--text)" strokeWidth={1.4} strokeOpacity={0.7} />
            <path d={path(curves.realistic)} fill="none" stroke="var(--measured)" strokeWidth={2.4} />
            {be && be > 1.0001e-4 && (
              <g>
                <line x1={lx(be)} x2={lx(be)} y1={T} y2={Hh - B} stroke="var(--pass)" strokeOpacity={0.6} strokeDasharray="2 3" />
                <circle cx={lx(be)} cy={ly(be)} r={4.5} fill="var(--pass)" />
                <text x={lx(be) > (L + W) / 2 ? lx(be) - 6 : lx(be) + 6} y={T + 12} fontSize={11} fill="var(--pass)"
                  textAnchor={lx(be) > (L + W) / 2 ? 'end' : 'start'}>break-even {pct(be, be < 0.01 ? 2 : 1)}{lx(be) > (L + W) / 2 ? ' · the code helps to the right →' : ' · the code helps to the right'}</text>
              </g>
            )}
            {hover !== null && <line x1={lx(lab.p[hover])} x2={lx(lab.p[hover])} y1={T} y2={Hh - B} stroke="var(--text-2)" strokeOpacity={0.5} />}
          </svg>
          <div className="row wrap legend" style={{ gap: 14 }}>
            <span className="sub"><svg width={22} height={10} aria-hidden><line x1={1} x2={21} y1={5} y2={5} stroke="var(--text-2)" strokeWidth={1.6} strokeDasharray="5 4" /></svg> one bare qubit</span>
            <span className="sub"><svg width={22} height={10} aria-hidden><line x1={1} x2={21} y1={5} y2={5} stroke="var(--text)" strokeOpacity={0.7} strokeWidth={1.4} /></svg> the code, perfect gates</span>
            <span className="sub"><svg width={22} height={10} aria-hidden><line x1={1} x2={21} y1={5} y2={5} stroke="var(--measured)" strokeWidth={2.4} /></svg> the code, {labScaleText(scale)}</span>
          </div>
          {readout && (
            <div className="mono sub" style={{ marginTop: 6 }}>
              at {pct(readout.p, readout.p < 0.01 ? 2 : 1)} per qubit: bare {pct(readout.p, 2)} · perfect gates {pct(readout.perfect, 3)} · {labScaleText(scale)} {pct(readout.real, 2)}
            </div>
          )}
          <p className="lead" style={{ margin: '10px 0 0' }}>{lab.summary}</p>
        </>
      )}
    </div>
  )
}
