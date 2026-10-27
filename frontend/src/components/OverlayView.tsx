import type { OverlayBox } from '../types'

interface Props {
  imageUrl: string
  width: number
  height: number
  boxes: OverlayBox[]
  highlight: string | null
  onPick: (linkedTo: string | null) => void
}

/** The photo with every detected part boxed and labelled with what it became. */
export function OverlayView({ imageUrl, width, height, boxes, highlight, onPick }: Props) {
  const fs = Math.max(14, Math.round(width / 70))
  return (
    <div>
      <div className="overlay-wrap">
        <img src={imageUrl} alt="Your sketch" />
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          {boxes.map((b) => {
            const [x1, y1, x2, y2] = b.bbox
            const hl = highlight !== null && b.linked_to === highlight
            const cls = `${b.linked_to ? '' : 'unlinked'} ${hl ? 'hl' : ''}`
            const text = `${b.label || b.concept} · ${Math.round(b.confidence * 100)}%`
            const tw = text.length * fs * 0.56 + 14
            const ty = Math.max(0, y1 - fs - 10)
            return (
              <g key={b.segment_id} onClick={() => onPick(b.linked_to)} onMouseEnter={() => b.linked_to && onPick(b.linked_to)}>
                <rect className={`ov-box ${cls}`} x={x1} y={y1} width={x2 - x1} height={y2 - y1} rx={6}
                  strokeWidth={hl ? 4 : 2.5} vectorEffect="non-scaling-stroke" />
                <g className={`ov-label ${cls}`}>
                  <rect x={x1} y={ty} width={tw} height={fs + 8} rx={5} />
                  <text x={x1 + 7} y={ty + fs + 1} fontSize={fs}>{text}</text>
                </g>
              </g>
            )
          })}
        </svg>
      </div>
      <div className="legend-row">
        <span><i style={{ border: '2px solid var(--primary)' }} />linked to the spec</span>
        <span><i style={{ border: '2px dashed #7d7f86' }} />detected, not used</span>
        <span>{boxes.length} parts found · hover a box to find its line in the spec</span>
      </div>
    </div>
  )
}
