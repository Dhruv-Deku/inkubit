import { useEffect, useState } from 'react'
import { api } from '../api'

export interface FigureRow {
  id: string; title: string; qubits: number; gates: number; verdict: 'proven' | 'repaired' | 'mismatch' | 'unread'
  first_try: boolean; attempts: number; detail: string; read_ops: string[]; first_image: string; final_image?: string; seconds: number
}
export interface FigureBench {
  date_utc: string; image_model: string; reader: string[]; max_repairs: number
  totals: { circuits: number; first_try: number; repaired: number; mismatch: number; unread: number }; circuits: FigureRow[]
}

const LABEL = { proven: 'right first time', repaired: 'corrected, then proven', mismatch: 'never matched', unread: 'could not be read' } as const

/** Every figure Muse Image drew of a gallery circuit, read back by SAM 3.1 and Muse Spark and compared exactly. */
export function FigureProofPanel() {
  const [data, setData] = useState<FigureBench | null>(null)
  const [missing, setMissing] = useState(false)
  const [open, setOpen] = useState(false)
  useEffect(() => { api.figureBenchmark().then(setData).catch(() => setMissing(true)) }, [])
  if (missing) return null
  const t = data?.totals
  const rows = data ? [...data.circuits].sort((a, b) => Number(a.first_try) - Number(b.first_try) || a.title.localeCompare(b.title)) : []
  const shown = open ? rows : rows.slice(0, 6)
  return (
    <div className="panel">
      <div className="panel-head"><h2>Proven illustrations</h2><span className="sub">a generated figure is read back before it is shown</span></div>
      {!data ? <p className="sub">Loading…</p> : <>
        <p className="lead" style={{ marginTop: 0 }}>
          Muse Image drew {t!.circuits} gallery circuits without captions. SAM 3.1 and Muse Spark read each figure back, and the
          circuit read back was compared exactly with the real one. <b>{t!.first_try} of {t!.circuits}</b> were right first time;
          {' '}{t!.repaired} {t!.repaired === 1 ? 'was' : 'were'} corrected by Muse Image after the read-back named the mistake;
          {' '}{t!.mismatch + t!.unread} never matched within {data.max_repairs} corrections, so the page shows the exact drawing instead.
        </p>
        <div className="fig-rows">
          {shown.map((r) => (
            <div key={r.id} className={`fig-row f-${r.verdict}`}>
              <a href={r.first_image} target="_blank" rel="noreferrer"><img src={r.first_image} alt={`Muse Image's figure of ${r.title}`} loading="lazy" /></a>
              {r.final_image
                ? <a href={r.final_image} target="_blank" rel="noreferrer"><img src={r.final_image} alt={`What is shown for ${r.title}`} loading="lazy" /></a>
                : <span className="fig-same">shown as drawn</span>}
              <div>
                <b>{r.title}</b> <span className="sub">{r.qubits} qubits · {r.gates} gates</span>
                <p><span className={`fig-verdict f-${r.verdict}`}>{r.verdict === 'proven' || r.verdict === 'repaired' ? '✓' : '✗'} {LABEL[r.verdict]}</span> {r.detail}</p>
              </div>
            </div>
          ))}
        </div>
        {rows.length > 6 && <button className="linkish" onClick={() => setOpen(!open)}>{open ? 'Show fewer' : `Show all ${rows.length}`}</button>}
        <p className="sub">{data.image_model} draws; {data.reader.join(' and ')} read back; scripts/figure_bench.py reruns it ({data.date_utc.slice(0, 10)}).</p>
      </>}
    </div>
  )
}
