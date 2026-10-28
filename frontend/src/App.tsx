import { useEffect, useRef, useState } from 'react'
import { ApiError, api, followJob } from './api'
import { AgentLog } from './components/AgentLog'
import { CallBadge } from './components/CallBadge'
import { Histogram } from './components/Histogram'
import { Logo } from './components/Icons'
import { OverlayView } from './components/OverlayView'
import { InsightsSection } from './components/Insights'
import { CircuitResults, NetworkResults } from './components/Results'
import { SpecEditor } from './components/SpecEditor'
import { StartPanel } from './components/StartPanel'
import type {
  AgentEvent, CircuitInsights, CircuitResult, CircuitSpec, Examples, Health, ModelCall, NetworkResult, RunOptions,
  SketchAnalysis, Spec, SpecIssue, Verdict,
} from './types'
import { decodeSpec, encodeSpec, specTitle } from './util'

type Stage = 'start' | 'edit' | 'run'

interface JobState {
  id: string
  spec: Spec
  events: AgentEvent[]
  live: boolean
  status: string
  error: string | null
  result: CircuitResult | NetworkResult | null
}

const DEFAULT_OPTIONS: RunOptions = {
  noise: 'realistic', shots: 4096, demo_mode: false, demo_fault: 'auto', explain: true, diagram: true,
}

/** While a run is live: the newest verified attempt's histogram, so a failure is visible at once. */
function LivePreview({ events, live }: { events: AgentEvent[]; live: boolean }) {
  const last = [...events].reverse().find((e) => e.step === 'verify' && e.details.verdict)
  if (!last) return <div className="panel empty">{live ? 'Results appear here as soon as the first attempt is checked.' : 'No result.'}</div>
  const v = last.details.verdict as Verdict
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Attempt {last.attempt}</h2>
        <span className={`badge ${v.passed ? 'pass' : 'fail'}`}>{v.passed ? 'matches the spec' : 'does not match the spec'}</span>
        <span className="spacer" />
        {live && <span className="sub">agent still working…</span>}
      </div>
      <Histogram predicted={v.expected} measured={v.measured} ideal={v.ideal} shots={v.metrics.shots} />
      <div className="sub" style={{ marginTop: 8 }}>{v.reason}</div>
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [examples, setExamples] = useState<Examples | null>(null)
  const [backendError, setBackendError] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>('start')
  const [sketch, setSketch] = useState<{ url: string; analysis: SketchAnalysis } | null>(null)
  const [spec, setSpec] = useState<Spec | null>(null)
  const [issues, setIssues] = useState<SpecIssue[]>([])
  const [checking, setChecking] = useState(false)
  const [options, setOptions] = useState<RunOptions>(DEFAULT_OPTIONS)
  const [job, setJob] = useState<JobState | null>(null)
  const [highlight, setHighlight] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [fromText, setFromText] = useState<{ text: string; notes: string; call: ModelCall } | null>(null)
  const [shared, setShared] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ ins: CircuitInsights | null; loading: boolean; error: string | null } | null>(null)

  useEffect(() => { setPreview(null) }, [spec, options.noise])

  const stepThrough = async () => {
    if (!spec || spec.kind !== 'circuit') return
    setPreview({ ins: null, loading: true, error: null })
    try {
      setPreview({ ins: await api.insights(spec, options.noise), loading: false, error: null })
    } catch (e) {
      setPreview({ ins: null, loading: false, error: (e as Error).message })
    }
  }
  const stopRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    Promise.all([api.health(), api.examples()])
      .then(([h, ex]) => { setHealth(h); setExamples(ex) })
      .catch((e: Error) => setBackendError(e.message))
    // a share link carries the whole spec in the URL hash
    const m = window.location.hash.match(/^#s=(.+)$/)
    if (m) {
      decodeSpec(m[1])
        .then((s) => { setSketch(null); setFromText(null); setSpec(s); setStage('edit') })
        .catch(() => setStartError('That share link is damaged: the spec in it could not be read.'))
        .finally(() => history.replaceState(null, '', window.location.pathname))
    }
  }, [])

  const shareLink = async () => {
    if (!spec) return
    const url = `${window.location.origin}${window.location.pathname}#s=${await encodeSpec(spec)}`
    try {
      await navigator.clipboard.writeText(url)
      setShared('Link copied')
    } catch {
      window.prompt('Copy this link', url)
    }
    setTimeout(() => setShared(null), 1600)
  }

  useEffect(() => {
    if (!spec) return
    setChecking(true)
    const t = setTimeout(() => {
      api.validate(spec)
        .then((r) => setIssues(r.issues))
        .catch((e: Error) => setIssues([{ path: '', message: e.message }]))
        .finally(() => setChecking(false))
    }, 250)
    return () => clearTimeout(t)
  }, [spec])

  const onImage = async (file: Blob, name: string) => {
    setBusy(true)
    setStartError(null)
    try {
      const analysis = await api.analyzeImage(file, name)
      setFromText(null)
      setSketch({ url: URL.createObjectURL(file), analysis })
      setSpec(analysis.spec)
      setStage('edit')
    } catch (e) {
      setStartError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const onSpec = (s: Spec) => {
    setSketch(null)
    setFromText(null)
    setSpec(s)
    setStage('edit')
  }

  const onText = async (text: string) => {
    setBusy(true)
    setStartError(null)
    try {
      const draft = await api.fromText(text)
      setSketch(null)
      setFromText({ text, notes: draft.notes, call: draft.call })
      setSpec(draft.spec)
      setStage('edit')
    } catch (e) {
      setStartError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const run = async () => {
    if (!spec) return
    stopRef.current?.()
    try {
      const { job_id } = await api.startJob(spec, options)
      setJob({ id: job_id, spec, events: [], live: true, status: 'running', error: null, result: null })
      setStage('run')
      stopRef.current = followJob(
        job_id,
        (ev) => {
          setJob((j) => (j && j.id === job_id ? { ...j, events: [...j.events, ev] } : j))
          if ((ev.step === 'explain' || ev.step === 'diagram') && ev.status === 'running') {
            // the result is stored before these start: show it while the explanation and diagram finish
            api.job(job_id).then((s) => setJob((j) => (j && j.id === job_id && s.result ? { ...j, result: s.result } : j))).catch(() => {})
          }
        },
        async (status, error) => {
          const summary = await api.job(job_id).catch(() => null)
          setJob((j) => (j && j.id === job_id
            ? { ...j, live: false, status: summary?.status ?? status, error: summary?.error ?? error, result: summary?.result ?? null }
            : j))
        },
      )
    } catch (e) {
      if (e instanceof ApiError && e.issues.length) setIssues(e.issues)
      else setStartError((e as Error).message)
    }
  }

  const valid = !!spec && issues.length === 0 && !checking
  const sketchCalls = sketch?.analysis.calls ?? []

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <Logo />
          <div><h1>Q-Canvas</h1><p>sketch → verified quantum simulation</p></div>
        </div>
        <nav className="steps" aria-label="Steps">
          <button className={`step ${stage === 'start' ? 'active' : 'done'}`} onClick={() => setStage('start')}><span className="n">1</span>Sketch</button>
          <button className={`step ${stage === 'edit' ? 'active' : spec ? 'done' : ''}`} disabled={!spec} onClick={() => setStage('edit')}><span className="n">2</span>Check the spec</button>
          <button className={`step ${stage === 'run' ? 'active' : job?.result ? 'done' : ''}`} disabled={!job} onClick={() => setStage('run')}><span className="n">3</span>Run &amp; verify</button>
        </nav>
        <span className="spacer" />
        <label className={`toggle ${options.demo_mode ? 'on' : ''}`} title="Break the first attempt on purpose so the repair loop is visible">
          <input type="checkbox" hidden checked={options.demo_mode} onChange={(e) => setOptions({ ...options, demo_mode: e.target.checked })} />
          <span className="track" />Demo mode
        </label>
        {health && (
          <span className={`badge ${health.mode === 'meta' ? 'meta' : health.provider === 'meta' ? 'fallback' : 'mock'}`}
            title={Object.entries(health.models).map(([k, v]) => `${k}: ${v}`).join('\n')}>
            <span className="dot" />{health.mode_label}
          </span>
        )}
      </header>

      {backendError && <div className="notice error" style={{ marginBottom: 16 }}>{backendError} Start it with <code>scripts/dev.sh</code>.</div>}

      {stage === 'start' && (
        <StartPanel examples={examples} busy={busy} error={startError} onImage={onImage} onSpec={onSpec} onText={onText}
          live={health?.mode === 'meta'} />
      )}

      {stage === 'edit' && spec && (
        <div className="stack">
          {fromText && (
            <div className="notice row wrap" style={{ gap: 8 }}>
              <span>Built from your words: <em>“{fromText.text}”</em></span><CallBadge call={fromText.call} />
              {fromText.notes && <span className="sub">{fromText.notes}</span>}
            </div>
          )}
          <div className={sketch ? 'edit-grid' : ''}>
            {sketch && (
              <div className="panel">
                <div className="panel-head"><h2>What we read from your sketch</h2></div>
                <div className="row wrap" style={{ marginBottom: 12, gap: 6 }}>
                  <span className="sub">Read by</span>
                  {sketchCalls.filter((c, i) => sketchCalls.findIndex((d) => d.model === c.model && d.provider === c.provider) === i)
                    .map((c, i) => <CallBadge key={i} call={c} />)}
                </div>
                <OverlayView imageUrl={sketch.url} width={sketch.analysis.width} height={sketch.analysis.height}
                  boxes={sketch.analysis.overlay} highlight={highlight} onPick={setHighlight} />
                {sketch.analysis.notes && <div className="notice" style={{ marginTop: 12 }}>{sketch.analysis.notes}</div>}
                {!sketch.analysis.valid && sketch.analysis.issues.length > 0 && (
                  <div className="notice warn" style={{ marginTop: 12 }}>The reading needs a fix before it can run; see the spec on the right.</div>
                )}
              </div>
            )}
            <SpecEditor spec={spec} issues={issues} highlight={highlight} onPick={setHighlight} onChange={setSpec} />
          </div>
          <div className="panel run-bar">
            {spec.kind === 'circuit' && (
              <>
                <span className="label">Noise</span>
                <div className="seg">
                  {(examples?.noise_presets ?? []).map((p) => (
                    <button key={p.name} className={options.noise === p.name ? 'on' : ''} onClick={() => setOptions({ ...options, noise: p.name })}>{p.label}</button>
                  ))}
                </div>
                <span className="label">Shots</span>
                <select value={options.shots} onChange={(e) => setOptions({ ...options, shots: Number(e.target.value) })}>
                  {[1024, 4096, 8192].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                {options.demo_mode && (
                  <>
                    <span className="label">Planted fault</span>
                    <select value={options.demo_fault} onChange={(e) => setOptions({ ...options, demo_fault: e.target.value })}>
                      <option value="auto">Auto (most telling)</option>
                      {examples?.faults.map((f) => <option key={f.name} value={f.name}>{f.label}</option>)}
                    </select>
                  </>
                )}
              </>
            )}
            {spec.kind === 'network' && <span className="sub">The agent models every link, finds the bottleneck, tries fixes and re-simulates.</span>}
            <span className="grow" />
            {startError && <span className="badge fail">{startError}</span>}
            <button className="btn big ghost" onClick={shareLink} title="Copy a link that opens this spec">{shared ?? 'Share link'}</button>
            {spec.kind === 'circuit' && (
              <button className="btn big" disabled={!valid || preview?.loading} onClick={stepThrough}
                title="See the exact state after every gate, the entanglement and the noise budget, without running">
                {preview?.loading ? 'Analysing…' : 'Step through'}
              </button>
            )}
            <button className="btn primary big" disabled={!valid} onClick={run}>
              {checking ? 'Checking…' : issues.length ? 'Fix the spec to run' : `Run ${specTitle(spec)}`}
            </button>
          </div>
          {preview?.error && <div className="notice error">{preview.error}</div>}
          {preview?.ins && spec.kind === 'circuit' && <InsightsSection spec={spec} ins={preview.ins} wide />}
        </div>
      )}

      {stage === 'run' && job && (
        <div className="run-grid">
          <div className="panel" style={{ position: 'sticky', top: 12 }}>
            <div className="panel-head">
              <h2>Live agent log</h2>
              {job.live ? <span className="badge"><span className="spin" style={{ width: 10, height: 10 }} />running</span>
                : job.result && 'verified' in job.result
                  ? <span className={`badge ${job.result.verified ? 'pass' : 'fail'}`}>{job.result.verified ? 'verified' : 'not verified'}</span>
                  : <span className={`badge ${job.status === 'done' ? 'pass' : 'fail'}`}>{job.status}</span>}
              <span className="spacer" />
              <button className="btn small ghost" onClick={() => setStage('edit')}>Edit spec</button>
              <button className="btn small" disabled={job.live} onClick={run}>Run again</button>
            </div>
            <AgentLog events={job.events} live={job.live} />
          </div>
          <div>
            {job.error && <div className="notice error" style={{ marginBottom: 12 }}>{job.error}</div>}
            {!job.result && <LivePreview events={job.events} live={job.live} />}
            {job.result && 'verified' in job.result && <CircuitResults result={job.result} sketchCalls={sketchCalls} spec={job.spec as CircuitSpec} />}
            {job.result && 'before' in job.result && <NetworkResults result={job.result} sketchCalls={sketchCalls} />}
          </div>
        </div>
      )}
    </div>
  )
}
