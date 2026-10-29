import { useState } from 'react'
import type { LinkMetrics, NetNode, NetworkMetrics, NetworkSpec } from '../types'
import { fmtRate, pct } from '../util'

const W = 900, PADX = 70, SKY = 52

function nodeGlyph(type: NetNode['type'], x: number, y: number) {
  if (type === 'satellite') {
    return (
      <g>
        <rect x={x - 22} y={y - 5} width={14} height={10} rx={1.5} fill="var(--panel-3)" stroke="var(--text-2)" />
        <rect x={x + 8} y={y - 5} width={14} height={10} rx={1.5} fill="var(--panel-3)" stroke="var(--text-2)" />
        <path d={`M${x - 8} ${y}h16`} stroke="var(--text-2)" />
        <rect x={x - 7} y={y - 8} width={14} height={16} rx={3} fill="var(--panel-2)" stroke="var(--text)" strokeWidth={1.4} />
      </g>
    )
  }
  if (type === 'repeater') {
    return (
      <g>
        <rect x={x - 11} y={y - 11} width={22} height={22} rx={6} fill="var(--panel-2)" stroke="var(--text)" strokeWidth={1.4} />
        <path d={`M${x - 5} ${y + 4}v-8l5 5 5-5v8`} fill="none" stroke="var(--text-2)" strokeWidth={1.4} strokeLinejoin="round" />
      </g>
    )
  }
  return (
    <g>
      <path d={`M${x - 13} ${y - 6}a13 13 0 0026 0z`} fill="var(--panel-2)" stroke="var(--text)" strokeWidth={1.4} />
      <path d={`M${x} ${y + 1}v10M${x - 8} ${y + 11}h16`} stroke="var(--text-2)" strokeWidth={1.4} />
    </g>
  )
}

/** Entangled photon pairs flying out from each link's source; more dots for a faster link. */
function Photons({ x1, y1, x2, y2, rate, fromSky }: { x1: number; y1: number; x2: number; y2: number; rate: number; fromSky: 'a' | 'b' | null }) {
  if (rate < 1e-3) return null
  const count = Math.max(1, Math.min(5, Math.round(1 + Math.log10(rate + 1))))
  // a satellite carries the pair source; on fiber the source sits mid-span and sends one photon each way
  const sx = fromSky === 'a' ? x1 : fromSky === 'b' ? x2 : (x1 + x2) / 2
  const sy = fromSky === 'a' ? y1 : fromSky === 'b' ? y2 : (y1 + y2) / 2
  const ends = fromSky === 'a' ? [[x2, y2]] : fromSky === 'b' ? [[x1, y1]] : [[x1, y1], [x2, y2]]
  const dur = 2.4
  return (
    <g pointerEvents="none">
      {Array.from({ length: count }, (_, k) => ends.map(([ex, ey], e) => (
        <circle key={`${k}-${e}`} r={3} fill="var(--gold)" opacity={0}>
          <animate attributeName="cx" from={sx} to={ex} dur={`${dur}s`} begin={`${(k * dur) / count}s`} repeatCount="indefinite" />
          <animate attributeName="cy" from={sy} to={ey} dur={`${dur}s`} begin={`${(k * dur) / count}s`} repeatCount="indefinite" />
          <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.1;0.8;1" dur={`${dur}s`} begin={`${(k * dur) / count}s`} repeatCount="indefinite" />
        </circle>
      )))}
    </g>
  )
}

/** The network as a picture: the path, each link's length, rate and fidelity, the bottleneck, and pairs in flight. */
export function NetworkMap({ spec, specAfter, before, after }: {
  spec: NetworkSpec; specAfter: NetworkSpec | null; before: NetworkMetrics; after: NetworkMetrics | null
}) {
  const [which, setWhich] = useState<'before' | 'after'>(after ? 'after' : 'before')
  const m = which === 'after' && after ? after : before
  const s = which === 'after' && specAfter ? specAfter : spec
  const nodes = new Map([...spec.nodes, ...(specAfter?.nodes ?? [])].map((n) => [n.id, n]))
  for (const n of s.nodes) nodes.set(n.id, n)
  const path = m.path.length ? m.path : [s.source, s.destination]
  const sky = path.some((id) => nodes.get(id)?.type === 'satellite')
  const H = sky ? 236 : 150, GROUND = sky ? 168 : 82  // no satellite: no sky to draw
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const xs = (i: number) => (path.length === 1 ? W / 2 : PADX + (i * (W - 2 * PADX)) / (path.length - 1))
  const ys = (id: string) => (nodes.get(id)?.type === 'satellite' ? SKY : GROUND)
  const link = (a: string, b: string): LinkMetrics | undefined =>
    m.links.find((l) => (l.from === a && l.to === b) || (l.from === b && l.to === a))
  const rates = m.links.map((l) => l.pair_rate_hz).filter((r) => r > 0)
  const lo = Math.log10(Math.max(1e-3, Math.min(...rates, 1))), hi = Math.log10(Math.max(10, ...rates))
  const widthFor = (r: number) => (r <= 1e-3 ? 1 : 1.4 + 3.6 * ((Math.log10(r) - lo) / Math.max(1e-6, hi - lo)))
  const weak = m.weakest_link
  const e = m.end_to_end
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Network map</h2>
        <span className="sub">pairs in flight; thicker links deliver more pairs per second</span>
        <span className="spacer" />
        {after && (
          <div className="seg">
            <button className={which === 'before' ? 'on' : ''} onClick={() => setWhich('before')}>Before</button>
            <button className={which === 'after' ? 'on' : ''} onClick={() => setWhich('after')}>After the fix</button>
          </div>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', maxWidth: 1000 }} role="img"
        aria-label={`Network path ${path.join(' to ')}: ${fmtRate(e.pair_rate_hz, 'pairs per second')}, fidelity ${e.fidelity.toFixed(3)}`}>
        <line x1={20} x2={W - 20} y1={GROUND + 26} y2={GROUND + 26} stroke="var(--line)" />
        {path.slice(1).map((b, i) => {
          const a = path[i]
          const l = link(a, b)
          const x1 = xs(i), y1 = ys(a), x2 = xs(i + 1), y2 = ys(b)
          const isWeak = !!weak && ((weak.from === a && weak.to === b) || (weak.from === b && weak.to === a))
          const space = l?.medium === 'free_space'
          const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
          const rate = l?.pair_rate_hz ?? 0
          const fromSky = nodes.get(a)?.type === 'satellite' ? 'a' : nodes.get(b)?.type === 'satellite' ? 'b' : null
          return (
            <g key={`${a}-${b}`}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={isWeak ? 'var(--text)' : 'var(--text-2)'} strokeOpacity={isWeak ? 0.95 : 0.5}
                strokeWidth={widthFor(rate)} strokeDasharray={space ? '6 5' : undefined} strokeLinecap="round" />
              {!reduced && <Photons x1={x1} y1={y1} x2={x2} y2={y2} rate={rate} fromSky={fromSky} />}
              {l && (
                <g>
                  <rect x={mx - (isWeak ? 84 : 66)} y={my - (y1 === y2 ? 36 : 12)} width={isWeak ? 168 : 132} height={28} rx={6} fill="var(--panel)" opacity={0.92} />
                  <text x={mx} y={my - (y1 === y2 ? 24 : 0)} textAnchor="middle" fontSize={11} fill={isWeak ? 'var(--warn)' : 'var(--text)'} fontFamily="var(--mono)">
                    {isWeak ? 'weakest · ' : ''}{l.length_km.toLocaleString()} km {space ? 'free space' : 'fiber'}
                  </text>
                  <text x={mx} y={my - (y1 === y2 ? 12 : -12)} textAnchor="middle" fontSize={10.5} fill="var(--text-2)" fontFamily="var(--mono)">
                    {fmtRate(rate, '/s')} · F {l.fidelity.toFixed(3)}
                  </text>
                </g>
              )}
            </g>
          )
        })}
        {path.map((id, i) => {
          const n = nodes.get(id)
          const x = xs(i), y = ys(id)
          return (
            <g key={id}>
              {nodeGlyph(n?.type ?? 'ground_station', x, y)}
              <text x={x} y={y + (n?.type === 'satellite' ? -18 : 40)} textAnchor="middle" fontSize={12} fill="var(--text)">{n?.label || id}</text>
              {n?.type === 'repeater' && n.memory_t2_ms != null && (
                <text x={x} y={y + 54} textAnchor="middle" fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">T2 {n.memory_t2_ms} ms</text>
              )}
            </g>
          )
        })}
      </svg>
      <div className="row wrap" style={{ gap: 16, marginTop: 6 }}>
        <span className="sub">End to end: <strong className="mono">{fmtRate(e.pair_rate_hz, 'pairs/s')}</strong></span>
        <span className="sub">fidelity <strong className="mono">{e.fidelity.toFixed(3)}</strong></span>
        <span className="sub">error rate <strong className="mono">{pct(e.qber)}</strong></span>
        <span className="sub">key <strong className="mono">{fmtRate(e.key_rate_bps, 'bit/s')}</strong></span>
        {weak && <span className="sub" style={{ color: 'var(--warn)' }}>weakest: {weak.from} → {weak.to}</span>}
        {(s.purification_rounds ?? 0) > 0 && <span className="sub">{s.purification_rounds} purification round{s.purification_rounds === 1 ? '' : 's'} per segment</span>}
      </div>
    </div>
  )
}
