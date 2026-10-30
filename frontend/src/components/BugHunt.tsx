import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { BugGuess, BugRound, BugVerdict, CircuitSpec } from '../types'
import { CallBadge } from './CallBadge'
import { CircuitPreview } from './CircuitPreview'
import { Histogram } from './Histogram'

const LEVELS = [{ id: 1, label: 'Warm-up' }, { id: 2, label: 'Tricky' }, { id: 3, label: 'Hard' }]
const KEY = 'qcanvas.bughunt'

interface Score { you: number; muse: number; rounds: number; streak: number; best: number }
const ZERO: Score = { you: 0, muse: 0, rounds: 0, streak: 0, best: 0 }

function loadScore(): Score {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...ZERO, ...JSON.parse(raw) } : ZERO
  } catch { return ZERO }
}
function saveScore(s: Score) {
  try { localStorage.setItem(KEY, JSON.stringify(s)) } catch { /* private window: the score lasts this visit only */ }
}

const newSeed = () => Math.floor(Math.random() * 1e9)
const secs = (ms: number) => `${(ms / 1000).toFixed(1)} s`

type Muse =
  | { state: 'off' } | { state: 'thinking'; since: number }
  | { state: 'ready'; guess: BugGuess; ms: number } | { state: 'error'; message: string }

/** One gate is wrong: find it from the histogram, against the exact search and (live) Muse Spark. */
export function BugHuntPanel({ live, onOpen }: { live: boolean; onOpen?: (spec: CircuitSpec) => void }) {
  const [level, setLevel] = useState(1)
  const [seed, setSeed] = useState(newSeed)
  const [round, setRound] = useState<BugRound | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [verdict, setVerdict] = useState<BugVerdict | null>(null)
  const [mine, setMine] = useState<{ index: number; ms: number } | null>(null)
  const [muse, setMuse] = useState<Muse>({ state: 'off' })
  const [now, setNow] = useState(0)
  const [score, setScore] = useState<Score>(loadScore)
  const shownAt = useRef(0)
  const next = useRef(newSeed())
  const counted = useRef<string | null>(null)

  // Load the round, then quietly plant the next one so "Next bug" is instant.
  useEffect(() => {
    const ctl = new AbortController()
    setRound(null); setVerdict(null); setMine(null); setError(null)
    api.bugRound(level, seed, ctl.signal).then((r) => {
      setRound(r)
      shownAt.current = performance.now()
      next.current = newSeed()
      api.bugRound(level, next.current).catch(() => { /* a prefetch only */ })
    }).catch((e: Error) => { if (!ctl.signal.aborted) setError(e.message) })
    return () => ctl.abort()
  }, [level, seed])

  // Muse Spark plays the same round in parallel; its pick stays hidden until you have guessed.
  useEffect(() => {
    if (!round || !live) { setMuse({ state: 'off' }); return }
    let gone = false
    const since = performance.now()
    setMuse({ state: 'thinking', since })
    api.bugMuse(round.level, round.seed).then((g) => { if (!gone) setMuse({ state: 'ready', guess: g, ms: performance.now() - since }) })
      .catch((e: Error) => { if (!gone) setMuse({ state: 'error', message: e instanceof ApiError ? e.message : 'Muse Spark could not play.' }) })
    return () => { gone = true }
  }, [round, live])

  useEffect(() => {
    if (!round || verdict) return
    const t = window.setInterval(() => setNow(performance.now()), 100)
    return () => clearInterval(t)
  }, [round, verdict])

  const guess = useCallback((index: number) => {
    if (!round || verdict || mine) return
    const ms = performance.now() - shownAt.current
    setMine({ index, ms })
    api.bugGuess(round.level, round.seed, index).then(setVerdict).catch((e: Error) => { setMine(null); setError(e.message) })
  }, [round, verdict, mine])

  // Score once per round, when both your verdict and (live) Muse Spark's pick are in.
  const museDone = muse.state === 'ready' || muse.state === 'error' || muse.state === 'off'
  useEffect(() => {
    if (!round || !verdict || !museDone || counted.current === round.id) return
    counted.current = round.id
    const museRight = muse.state === 'ready' && verdict.machine.culprits.includes(muse.guess.index)
    setScore((s) => {
      const streak = verdict.correct ? s.streak + 1 : 0
      const out = { you: s.you + (verdict.correct ? 1 : 0), muse: s.muse + (museRight ? 1 : 0), rounds: s.rounds + 1, streak, best: Math.max(s.best, streak) }
      saveScore(out)
      return out
    })
  }, [round, verdict, museDone, muse])

  const playing = !!round && !verdict && !mine
  const elapsed = round ? (mine ? mine.ms : verdict ? 0 : Math.max(0, now - shownAt.current)) : 0
  const giveUp = () => { if (round) guess(round.spec.operations.length) }  // an index past the end: shown, not guessed
  const nextRound = () => setSeed(next.current)

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Bug hunt</h2>
        <span className="sub">{live ? 'one gate is wrong: find it before Muse Spark does' : 'one gate is wrong: find it from the histogram'}</span>
        <span className="spacer" />
        <div className="seg">
          {LEVELS.map((l) => <button key={l.id} className={level === l.id ? 'on' : ''} onClick={() => { setLevel(l.id); setSeed(newSeed()) }}>{l.label}</button>)}
        </div>
      </div>

      <div className="bug-bar">
        <div className="bug-score mono">
          <span>You <b>{score.you}</b></span>
          {live && <span>Muse Spark <b>{score.muse}</b></span>}
          <span className="muted">of {score.rounds} · streak {score.streak} · best {score.best}</span>
        </div>
        <span className="spacer" />
        <span className={`bug-clock mono ${playing ? 'on' : ''}`} aria-label="Your time">{secs(elapsed)}</span>
        <MuseChip muse={muse} live={live} reveal={!!verdict} now={now} />
      </div>

      {error && <div className="notice error">{error}</div>}
      {!round && !error && <div className="sub" style={{ padding: '18px 0' }}>Planting a bug…</div>}
      {round && (
        <>
          <p className="lead" style={{ margin: '10px 0 8px' }}>
            This should be <b style={{ color: 'var(--text)' }}>{round.title}</b>. One gate is wrong. Compare what it should give with what
            it gave, then click the gate you think is broken.
          </p>
          <Histogram predicted={round.intended} ideal={round.intended} measured={Object.fromEntries(Object.entries(round.observed).map(([k, v]) => [k, v / round.shots]))}
            shots={round.shots} predictedLabel="What it should give (exact)" measuredLabel="What the broken one gave" idealMarks={false} />
          <div className={`bug-circuit ${playing ? 'live' : ''}`}>
            <CircuitPreview spec={round.spec as CircuitSpec} highlight={verdict ? `operations[${verdict.planted}]` : null} onPick={() => {}}
              compose={playing ? { tool: 'ERASE', pending: [], onWire: () => {}, onGate: guess } : undefined} />
          </div>
          {playing && (
            <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
              <span className="sub">Click a gate. Any gate whose one-edit fix restores the right odds counts.</span>
              <span className="spacer" />
              <button className="chip-btn" onClick={giveUp}>Show me</button>
            </div>
          )}
          {mine && !verdict && <div className="sub" style={{ marginTop: 8 }}>Checking…</div>}
          {verdict && round && <Reveal round={round} verdict={verdict} mine={mine} muse={muse} onNext={nextRound} onOpen={onOpen} />}
        </>
      )}
    </div>
  )
}

function MuseChip({ muse, live, reveal, now }: { muse: Muse; live: boolean; reveal: boolean; now: number }) {
  if (!live) return <span className="sub">Muse Spark joins in live mode</span>
  if (muse.state === 'thinking') return <span className="bug-muse thinking">Muse Spark is thinking… {secs(Math.max(0, now - muse.since))}</span>
  if (muse.state === 'error') return <span className="bug-muse" title={muse.message}>Muse Spark sat this one out</span>
  if (muse.state === 'ready') return <span className="bug-muse ready">{reveal ? `Muse Spark picked #${muse.guess.index}` : 'Muse Spark has answered'} · {secs(muse.ms)}</span>
  return null
}

function Reveal({ round, verdict, mine, muse, onNext, onOpen }: {
  round: BugRound; verdict: BugVerdict; mine: { index: number; ms: number } | null; muse: Muse
  onNext: () => void; onOpen?: (spec: CircuitSpec) => void
}) {
  const gaveUp = !mine || mine.index >= round.spec.operations.length
  const others = verdict.machine.fixes.filter((f) => f.index !== verdict.planted)
  const museRight = muse.state === 'ready' && verdict.machine.culprits.includes(muse.guess.index)
  return (
    <div className="bug-reveal">
      <div className={`bug-verdict ${verdict.correct ? 'ok' : 'no'}`}>
        {gaveUp ? 'Here it is.' : verdict.correct ? `✓ Found it in ${secs(mine!.ms)}` : `✗ Not gate #${verdict.index}.`}
      </div>
      <p className="lead" style={{ margin: '6px 0 10px' }}>
        The bug, gate #{verdict.planted} (outlined above): {verdict.detail} ({verdict.label}).
        {others.length > 0 && <> Also fixable at {others.slice(0, 3).map((f) => `#${f.index} (${f.edit})`).join(', ')}, so those count too.</>}
      </p>
      <div className="tiles">
        <div className="tile"><div className="k">You</div>
          <div className={`v ${gaveUp ? '' : verdict.correct ? 'good' : 'bad'}`}>{gaveUp ? '–' : verdict.correct ? 'Right' : 'Missed'}</div>
          <div className="s">{gaveUp ? 'showed the answer' : `${secs(mine!.ms)} · picked #${mine!.index}`}</div></div>
        <div className="tile"><div className="k">Exact search</div><div className="v">{verdict.machine.culprits.length} gate{verdict.machine.culprits.length === 1 ? '' : 's'}</div>
          <div className="s">tried all {verdict.machine.checked} one-gate edits in {secs(verdict.machine.seconds * 1000)}</div></div>
        <div className="tile"><div className="k">Muse Spark</div>
          {muse.state === 'ready'
            ? <><div className={`v ${museRight ? 'good' : 'bad'}`}>{museRight ? 'Right' : 'Missed'}</div><div className="s">{secs(muse.ms)} · picked #{muse.guess.index}</div></>
            : <><div className="v">–</div><div className="s">{muse.state === 'thinking' ? 'still thinking' : muse.state === 'error' ? 'could not play' : 'live mode only'}</div></>}
        </div>
        <div className="tile"><div className="k">The circuit</div><div className="v">{round.gates} gates</div><div className="s">{round.spec.num_qubits} qubits · {round.level_label.toLowerCase()}</div></div>
      </div>
      {muse.state === 'ready' && (
        <div className="bug-muse-says">
          <CallBadge call={muse.guess.call} />
          <span>“{muse.guess.reason}” <span className="muted">Fix: {muse.guess.fix}.</span></span>
        </div>
      )}
      <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
        <button className="btn primary" onClick={onNext}>Next bug</button>
        {onOpen && <button className="btn" onClick={() => onOpen(verdict.fixed as CircuitSpec)}>Open the fixed circuit in the editor</button>}
      </div>
    </div>
  )
}
