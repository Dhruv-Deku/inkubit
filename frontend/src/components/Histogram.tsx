import { useState } from 'react'
import type { Distribution } from '../types'
import { pct } from '../util'

interface Props {
  predicted: Distribution
  measured: Distribution
  ideal: Distribution
  shots: number
}

const H = 230
const PAD = { l: 44, r: 12, t: 14, b: 34 }

/**
 * Predicted (exact, with noise) vs measured, one pair of bars per outcome.
 * Predicted is an outlined bar and measured is solid, so identity never rests
 * on colour alone; a dashed tick marks the noiseless ideal.
 */
export function Histogram({ predicted, measured, ideal, shots }: Props) {
  const [tip, setTip] = useState<{ k: string; x: number; y: number } | null>(null)
  const [showIdeal, setShowIdeal] = useState(true)
  const keys = Array.from(new Set([...Object.keys(predicted), ...Object.keys(measured), ...Object.keys(ideal)]))
    .filter((k) => (predicted[k] ?? 0) > 0.002 || (measured[k] ?? 0) > 0 || (ideal[k] ?? 0) > 0)
    .sort()
  const many = keys.length > 16
  const shown = many ? keys.filter((k) => (ideal[k] ?? 0) > 0 || (measured[k] ?? 0) > 0.01) : keys
  const max = Math.max(0.05, ...shown.map((k) => Math.max(predicted[k] ?? 0, measured[k] ?? 0, ideal[k] ?? 0)))
  const top = Math.min(1, Math.ceil(max * 10) / 10)
  const groupW = Math.max(36, Math.min(84, 620 / Math.max(1, shown.length)))
  const W = PAD.l + PAD.r + groupW * shown.length
  const bw = Math.min(26, (groupW - 14) / 2)
  const yv = (p: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - p / top)
  const ticks = [0, top / 2, top]

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <div className="legend-row" style={{ marginTop: 0 }}>
          <span><i style={{ border: '2px solid var(--predicted)', background: 'rgba(217,89,38,0.18)' }} />Predicted from the spec (exact, with noise)</span>
          <span><i style={{ background: 'var(--measured)' }} />Measured ({shots} shots)</span>
          {showIdeal && <span><i style={{ borderTop: '2px dashed var(--text)', height: 0, marginBottom: 3 }} />Noiseless ideal</span>}
        </div>
        <label className="toggle" style={{ fontSize: 12 }}>
          <input type="checkbox" hidden checked={showIdeal} onChange={(e) => setShowIdeal(e.target.checked)} />
          <span className="sub">{showIdeal ? 'Hide' : 'Show'} ideal</span>
        </label>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <svg width={Math.max(W, 320)} height={H} role="img" aria-label="Predicted versus measured outcome probabilities">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.l} x2={W - PAD.r} y1={yv(t)} y2={yv(t)} stroke="var(--line)" />
              <text x={PAD.l - 8} y={yv(t) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">{Math.round(t * 100)}%</text>
            </g>
          ))}
          {shown.map((k, i) => {
            const gx = PAD.l + i * groupW + groupW / 2
            const p = predicted[k] ?? 0, m = measured[k] ?? 0, id = ideal[k] ?? 0
            const base = yv(0)
            const bar = (x: number, v: number) => {
              const y = yv(v), h = Math.max(0, base - y)
              const r = Math.min(4, h, bw / 2)
              return `M${x} ${base}V${y + r}q0 ${-r} ${r} ${-r}h${bw - 2 * r}q${r} 0 ${r} ${r}V${base}Z`
            }
            return (
              <g key={k}
                onMouseMove={(e) => setTip({ k, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setTip(null)}>
                <rect x={gx - groupW / 2} y={PAD.t} width={groupW} height={H - PAD.t - PAD.b} fill="transparent" />
                {p > 0 && <path d={bar(gx - bw - 1, p)} fill="rgba(217,89,38,0.16)" stroke="var(--predicted)" strokeWidth={1.6} />}
                {m > 0 && <path d={bar(gx + 1, m)} fill="var(--measured)" />}
                {showIdeal && id > 0 && (
                  <line x1={gx - bw - 4} x2={gx + bw + 4} y1={yv(id)} y2={yv(id)} stroke="var(--text)" strokeWidth={1.6} strokeDasharray="4 3" />
                )}
                <text x={gx} y={H - PAD.b + 18} textAnchor="middle" fontSize={12} fill="var(--text-2)" fontFamily="var(--mono)">|{k}⟩</text>
              </g>
            )
          })}
          <line x1={PAD.l} x2={W - PAD.r} y1={yv(0)} y2={yv(0)} stroke="var(--line-2)" />
        </svg>
      </div>
      {many && <div className="sub">Showing the {shown.length} outcomes that matter out of {keys.length}.</div>}
      {tip && (
        <div className="chart-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>
          <div className="mono" style={{ marginBottom: 4 }}>|{tip.k}⟩</div>
          <div className="r"><span><span className="sw" style={{ border: '1.5px solid var(--predicted)' }} />Predicted</span><span>{pct(predicted[tip.k] ?? 0)}</span></div>
          <div className="r"><span><span className="sw" style={{ background: 'var(--measured)' }} />Measured</span><span>{pct(measured[tip.k] ?? 0)}</span></div>
          <div className="r"><span className="muted">Noiseless ideal</span><span>{pct(ideal[tip.k] ?? 0)}</span></div>
        </div>
      )}
    </div>
  )
}
