import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { LectureClaim, LectureResult, LectureStep, LectureView } from '../types'
import { CallBadge } from './CallBadge'

const SPEAKER_COLOURS = ['#6e9fd8', '#d8d4ca', '#8fc79a', '#e0b27a']
const SAMPLE = '/api/lecture/sample.mp4'

const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`

function speakerColour(r: LectureResult, label: string): string {
  const order = [...new Set(r.turns.map((t) => t.speaker))]
  return SPEAKER_COLOURS[Math.max(0, order.indexOf(label)) % SPEAKER_COLOURS.length]
}

const MARK = { true: '✓', false: '✗', unclear: '–' } as const
const WORD = { true: 'right', false: 'wrong', unclear: 'not checkable' } as const

function Steps({ steps }: { steps: LectureStep[] }) {
  return (
    <ol className="lec-steps">
      {steps.map((s) => (
        <li key={s.id} className={`s-${s.status}`} title={s.detail}>
          <span className="lec-mark">{s.status === 'done' || s.status === 'offline' ? '✓' : s.status === 'failed' ? '✗' : s.status === 'running' ? '' : '·'}</span>
          <span className="lec-step-text">
            <b>{s.label}</b>
            <span>{s.by}{s.status === 'offline' ? ' · offline record' : ''}{s.seconds !== null ? ` · ${s.seconds.toFixed(1)} s` : ''}</span>
            {s.detail && <span className="lec-detail">{s.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** Speech, drawing and claims on one time axis; click a claim or a turn to hear it. */
function Timeline({ r, now, onSeek }: { r: LectureResult; now: number; onSeek: (t: number) => void }) {
  const W = 1000, L = 70, R = 12
  const x = (t: number) => L + (Math.min(t, r.duration) / r.duration) * (W - L - R)
  const seen: Record<number, number> = {}
  return (
    <svg className="lec-timeline" viewBox={`0 0 ${W} 132`} role="img" aria-label="Who spoke, what was drawn and each claim's verdict over time">
      {[['speech', 22], ['drawn', 60], ['claims', 96]].map(([label, y]) => (
        <text key={label} x={0} y={Number(y) + 4} className="lec-lane">{label}</text>
      ))}
      {r.turns.map((t) => (
        <rect key={t.index} x={x(t.start)} y={14} width={Math.max(2, x(t.end) - x(t.start))} height={16} rx={3}
          fill={speakerColour(r, t.speaker)} opacity={now >= t.start && now <= t.end ? 1 : 0.55} className="lec-hit"
          onClick={() => onSeek(t.start)}>
          <title>{`Speaker ${t.speaker}, ${clock(t.start)}: ${t.text}`}</title>
        </rect>
      ))}
      {r.ops.map((o, i) => (
        <g key={o.op} className="lec-hit" onClick={() => onSeek(o.appears)}>
          <line x1={x(o.appears)} x2={x(o.appears)} y1={50} y2={70} className="lec-op" />
          <text x={x(o.appears) + 4} y={i % 2 ? 76 : 58} className="lec-op-label">{o.label}</text>
          <title>{`${o.label} drawn at ${o.appears.toFixed(1)} s (${o.how})`}</title>
        </g>
      ))}
      {r.claims.map((c, i) => {
        const k = seen[c.turn] = (seen[c.turn] ?? -1) + 1
        return (
          <g key={i} className="lec-hit" onClick={() => onSeek(c.time)}>
            <circle cx={x(c.time) + k * 11} cy={96} r={5.5} className={`lec-dot v-${c.verdict}`} />
            <title>{`${WORD[c.verdict]}: “${c.quote}” ${c.detail}`}</title>
          </g>
        )
      })}
      <line x1={x(now)} x2={x(now)} y1={6} y2={108} className="lec-now" />
      {Array.from({ length: Math.floor(r.duration / 10) + 1 }, (_, k) => k * 10).map((t) => (
        <text key={t} x={x(t)} y={126} className="lec-tick">{clock(t)}</text>
      ))}
    </svg>
  )
}

function Claims({ r, now, onSeek }: { r: LectureResult; now: number; onSeek: (t: number) => void }) {
  const [wrongOnly, setWrongOnly] = useState(false)
  const keep = (c: LectureClaim) => !wrongOnly || c.verdict === 'false'
  const byTurn = r.turns.map((t) => ({ t, claims: r.claims.filter((c) => c.turn === t.index && keep(c)) })).filter((g) => g.claims.length)
  return (
    <>
    {r.tally.false > 0 && (
      <div className="seg lec-filter">
        <button className={!wrongOnly ? 'on' : ''} onClick={() => setWrongOnly(false)}>All {r.claims.length}</button>
        <button className={wrongOnly ? 'on' : ''} onClick={() => setWrongOnly(true)}>Wrong {r.tally.false}</button>
      </div>
    )}
    <div className="lec-claims">
      {byTurn.map(({ t, claims }) => (
        <div key={t.index} className={`lec-turn ${now >= t.start && now <= t.end + 0.3 ? 'on' : ''}`}>
          <button className="lec-turn-head" onClick={() => onSeek(t.start)}>
            <i style={{ background: speakerColour(r, t.speaker) }} />Speaker {t.speaker}<span>{clock(t.start)}</span>
          </button>
          {claims.map((c: LectureClaim, i) => (
            <div key={i} className={`lec-claim v-${c.verdict}`}>
              <span className="lec-verdict">{MARK[c.verdict]}</span>
              <div>
                <q>{c.quote}</q>
                <p>{c.detail}</p>
                <span className="sub">against the board with {c.board_ops.join(', ') || 'empty wires'}</span>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
    </>
  )
}

/** The last frame with every part SAM 3.1 followed through the video, stamped with when it first appeared. */
function Tracked({ r }: { r: LectureResult }) {
  const end = Math.max(...r.tracks.map((t) => t.last_s), 0)
  const fs = r.width / 52
  return (
    <div className="lec-frame">
      <img src={r.frame} alt="The board at the end of the lecture" />
      <svg viewBox={`0 0 ${r.width} ${r.height}`} preserveAspectRatio="none" aria-hidden>
        {r.tracks.filter((t) => t.last_s >= end - 1).map((t) => (
          <g key={t.id}>
            <rect x={t.bbox[0]} y={t.bbox[1]} width={t.bbox[2] - t.bbox[0]} height={t.bbox[3] - t.bbox[1]} rx={4}
              fill="none" stroke="#3987e5" strokeWidth={r.width / 420} />
            <rect x={t.bbox[0]} y={t.bbox[1] - fs * 1.25} width={fs * 2.9} height={fs * 1.15} rx={3} fill="#3987e5" />
            <text x={t.bbox[0] + fs * 0.3} y={t.bbox[1] - fs * 0.38} fontSize={fs * 0.82} fill="#fff" fontFamily="IBM Plex Mono, monospace">
              {t.first_s.toFixed(1)} s
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

export function LecturePanel({ live }: { live: boolean }) {
  const [meta, setMeta] = useState<{ title: string; made_by: string; duration: number } | null>(null)
  const [view, setView] = useState<LectureView | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [src, setSrc] = useState(SAMPLE)
  const [now, setNow] = useState(0)
  const video = useRef<HTMLVideoElement>(null)
  const file = useRef<HTMLInputElement>(null)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    api.lectureSample().then(setMeta).catch(() => {})
    return () => { alive.current = false }
  }, [])

  const start = async (upload: File | null) => {
    setError(null); setBusy(true); setView(null); setNow(0)
    setSrc((old) => { if (old.startsWith('blob:')) URL.revokeObjectURL(old); return upload ? URL.createObjectURL(upload) : SAMPLE })
    try {
      const { lecture_id } = await api.startLecture(upload)
      for (;;) {
        const v = await api.lecture(lecture_id)
        if (!alive.current) return
        setView(v)
        if (v.status !== 'running') { if (v.status === 'failed') setError(v.error ?? 'the check failed'); break }
        await new Promise((res) => setTimeout(res, 700))
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      if (alive.current) setBusy(false)
    }
  }

  const seek = (t: number) => {
    const v = video.current
    if (!v) return
    v.currentTime = t
    void v.play().catch(() => {})
  }
  const r = view?.result ?? null

  return (
    <div className="panel lecture">
      <div className="panel-head">
        <h2>Lecture checker</h2><span className="sub">a filmed explanation, every claim checked</span><span className="spacer" />
        <button className="btn" disabled={busy || !live} onClick={() => file.current?.click()}
          title={live ? 'MP4 or MOV with sound, up to 60 seconds' : 'Checking your own video needs the live models'}>Upload a video</button>
        <button className="btn primary" disabled={busy} onClick={() => { void start(null) }}>
          {busy ? 'Checking…' : 'Check the sample lecture'}
        </button>
        <input ref={file} type="file" accept="video/mp4,video/quicktime" hidden
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void start(f) }} />
      </div>

      <div className="lec-top">
        <div className="lec-media">
          <video ref={video} src={src} controls preload="metadata" playsInline onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} />
          {r && <Timeline r={r} now={now} onSeek={seek} />}
        </div>
        <div className="lec-side">
          {!view && (
            <p className="lead">
              {meta ? `${meta.title}: ${Math.round(meta.duration)} seconds, a teacher and a student. ` : ''}
              Muse Voice tells the speakers apart, SAM 3.1 follows each drawn part through the video, Muse Spark writes
              every claim out, and exact simulation judges each one against the board as it was when it was said.
            </p>
          )}
          {view && !r && <Steps steps={view.steps} />}
          {r && <>
            <p className="lec-headline">{r.headline}</p>
            <Claims r={r} now={now} onSeek={seek} />
          </>}
          {error && <div className="notice error">{error}</div>}
        </div>
      </div>

      {r && <>
        <details className="lec-how"><summary>How it was checked</summary><Steps steps={view!.steps} /></details>
        <div className="lec-lower">
          <section>
            <h3>What SAM 3.1 tracked</h3>
            <Tracked r={r} />
            <p className="sub">Each box is stamped with when the part first appeared; the claims are checked against the board as it was at that moment.</p>
          </section>
          <section className="lec-notes">
            <h3>Corrected notes</h3>
            <h4>{r.notes.title}</h4>
            <p>{r.notes.summary}</p>
            {r.notes.corrections.map((c, i) => (
              <div key={i} className="lec-correction">
                <span className="sub">Speaker {c.speaker} said</span> <q>{c.quote}</q>
                <p>{c.correction}</p>
              </div>
            ))}
            {r.notes.sections.map((s, i) => <div key={i} className="lec-section"><b>{s.heading}</b><p>{s.text}</p></div>)}
          </section>
          <section>
            <h3>Clean figure</h3>
            <img className="lec-figure" src={r.figure.image} alt="A clean figure of the lecture's circuit" />
            {r.figure.proof && (
              <p className={`lec-proof p-${r.figure.proof.verdict}`}>
                {r.figure.proof.verdict === 'proven' || r.figure.proof.verdict === 'repaired' ? '✓ ' : '✗ '}{r.figure.proof.detail}
              </p>
            )}
            <p className="sub">{r.figure.caption}</p>
          </section>
        </div>
        <div className="lec-calls">
          {r.calls.map((c, i) => <CallBadge key={i} call={c} />)}
          <span className="sub">{r.seconds.toFixed(0)} s{r.source === 'sample' && r.made_by ? ` · sample made by ${r.made_by}` : ''}</span>
        </div>
      </>}
    </div>
  )
}
