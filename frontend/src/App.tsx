import { useEffect, useRef, useState } from 'react'
import { ApiError, api, followJob } from './api'
import { AgentLog } from './components/AgentLog'
import { CallBadge } from './components/CallBadge'
import { ChallengeList, ChallengePanel, loadProgress, saveProgress, type Progress } from './components/Challenge'
import { Histogram } from './components/Histogram'
import { Logo } from './components/Icons'
import { OverlayView } from './components/OverlayView'
import { InsightsSection } from './components/Insights'
import { RepetitionLabPanel, ShorLabPanel } from './components/Labs'
import { QaoaLabPanel } from './components/Qaoa'
import { BugHuntPanel } from './components/BugHunt'
import { ArenaPanel } from './components/Arena'
import { ChemLabPanel, QkdLabPanel } from './components/Science'
import { UseCases, scrollToPanel } from './components/UseCases'
import { CopilotPanel } from './components/Copilot'
import { RosettaPanel } from './components/Rosetta'
import { ObservatoryPanel } from './components/Observatory'
import { MissionPanel } from './components/Mission'
import { RefereePanel } from './components/Referee'
import { PaperPanel } from './components/Paper'
import { CodesPanel } from './components/Codes'
import { LearningPanel } from './components/Learning'
import { DiscoveryPanel } from './components/Discovery'
import { DistributedPanel } from './components/Distributed'
import { EstimatorPanel } from './components/Estimator'
import { LiveBoardPanel } from './components/LiveBoard'
import { GlobePanel } from './components/Globe'
import { ReproducePanel } from './components/Reproduce'
import { DecoderPanel } from './components/Decoder'
import { PulsePanel } from './components/Pulse'
import { HardwarePanel } from './components/Hardware'
import { CircuitResults, NetworkResults } from './components/Results'
import { SpecEditor } from './components/SpecEditor'
import { StartPanel } from './components/StartPanel'
import { ProofBenchPanel, ProofSheetView } from './components/ProofSheet'
import { IbmPanel, IbmRunButton } from './components/Ibm'
import { Tour, type TourSection } from './components/Tour'
import { Hero } from './components/Hero'
import type {
  ProofSheet,
  AgentEvent, ChallengeInfo, CircuitInsights, CircuitResult, CircuitSpec, Examples, Health, JobSummary, ModelCall,
  NetworkResult, NetworkSpec, RecentRun, RunOptions, SketchAnalysis, Spec, SpecIssue, Verdict,
} from './types'
import { clone, decodeSpec, encodeSpec, specTitle } from './util'

type SectionId = 'build' | 'discover' | 'hardware' | 'labs' | 'evidence'
const SECTIONS: { id: SectionId; label: string; hint: string; art: string; panels: string[] }[] = [
  { id: 'build', label: 'Sketch to code', hint: 'photo, words, voice, live board', art: 'sketch', panels: ['Live board', 'Quantum Rosetta', 'What it can do', 'Recent runs', 'Sample sketches'] },
  { id: 'hardware', label: 'Hardware & networks', hint: 'IBM chips, pulses, decoders, satellites', art: 'hardware', panels: ['IBM Quantum', 'Pulse lab', 'ML error-correction decoder', 'Code lab', 'Error-correction lab', 'Distributed quantum computer', 'Satellite planner'] },
  { id: 'evidence', label: 'Proof', hint: 'proof sheet, real chip runs, AI alone', art: 'evidence', panels: ['Proof sheet over the gallery', 'Simulation observatory', 'AI alone vs Inkubit', 'The AI referee'] },
  { id: 'discover', label: 'Discover', hint: 'AI scientist, when quantum wins, papers', art: 'bughunt', panels: ['Discovery lab', 'An AI scientist that learns', 'When does quantum win?', 'Reproduce a paper', 'Reproduce a whole paper'] },
  { id: 'labs', label: 'Labs', hint: 'Shor, QAOA, H₂, BB84, bug hunt, puzzles', art: 'molecule', panels: ["Shor's algorithm lab", 'Split the party', 'Molecule lab', 'Catch the spy', 'Bug hunt', 'Challenges'] },
]

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

function outcomeOf(s: JobSummary | null): string {
  if (!s || s.status === 'failed' || !s.result) return 'error'
  if ('verified' in s.result) return s.result.verified ? 'verified' : 'not verified'
  return s.result.fix ? 'improved' : 'no better design'
}

const DEFAULT_OPTIONS: RunOptions = {
  noise: 'realistic', shots: 4096, demo_mode: false, demo_fault: 'auto', explain: true, diagram: true, language: 'English',
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
  const [assistant, setAssistant] = useState<'mission' | 'ask'>('mission')
  const [tab, setTab] = useState<SectionId>(() => {
    const h = new URLSearchParams(window.location.hash.slice(1)).get('tab')
    return (SECTIONS.find((t) => t.id === h)?.id ?? 'build') as SectionId
  })
  const [touring, setTouring] = useState(() => window.location.hash.includes('tour'))
  const [seen, setSeen] = useState<Set<SectionId>>(() => new Set([tab]))  // opened sections stay mounted, hidden
  const goTab = (id: SectionId) => {
    setTab(id)
    setSeen((v) => (v.has(id) ? v : new Set(v).add(id)))
    if (window.location.hash.startsWith('#s=')) return  // a shared circuit link: leave it intact
    const params = new URLSearchParams(window.location.hash.slice(1))
    params.set('tab', id)
    window.history.replaceState(null, '', `#${params.toString()}`)
  }
  useEffect(() => {
    const onGoto = (e: Event) => {
      const title = (e as CustomEvent<string>).detail
      const hit = SECTIONS.find((t) => t.panels.some((p) => p.startsWith(title) || title.startsWith(p)))
      if (!hit) return
      goTab(hit.id)
      window.setTimeout(() => scrollToPanel(title, true), 150)
      window.setTimeout(() => scrollToPanel(title, true), 1100)  // again once the panels above have loaded
    }
    window.addEventListener('inkubit:goto', onGoto)
    return () => window.removeEventListener('inkubit:goto', onGoto)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const [sketch, setSketch] = useState<{ url: string; analysis: SketchAnalysis } | null>(null)
  const [spec, setSpec] = useState<Spec | null>(null)
  const [issues, setIssues] = useState<SpecIssue[]>([])
  const [checking, setChecking] = useState(false)
  const [options, setOptions] = useState<RunOptions>(DEFAULT_OPTIONS)
  const [job, setJob] = useState<JobState | null>(null)
  const [highlight, setHighlight] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [fromText, setFromText] = useState<{ text: string; notes: string; call: ModelCall; voice?: ModelCall } | null>(null)
  const [shared, setShared] = useState<string | null>(null)
  const [recent, setRecent] = useState<RecentRun[]>([])
  const [preview, setPreview] = useState<{ ins: CircuitInsights | null; loading: boolean; error: string | null } | null>(null)
  const [proof, setProof] = useState<{ sheet: ProofSheet | null; loading: boolean; error: string | null } | null>(null)
  const [challenges, setChallenges] = useState<ChallengeInfo[]>([])
  const [challenge, setChallenge] = useState<ChallengeInfo | null>(null)
  const [progress, setProgress] = useState<Progress>(loadProgress)

  const startChallenge = (c: ChallengeInfo) => {
    stopRef.current?.()
    setSketch(null)
    setFromText(null)
    setChallenge(c)
    setSpec(clone(c.starter))
    setStage('edit')
    window.scrollTo({ top: 0 })
  }
  const score = (id: string, stars: number) => setProgress((p) => {
    if ((p[id] ?? 0) >= stars) return p
    const next = { ...p, [id]: stars }
    saveProgress(next)
    return next
  })
  const nextChallenge = challenge ? challenges[challenges.findIndex((c) => c.id === challenge.id) + 1] : undefined

  useEffect(() => { setPreview(null); setProof(null) }, [spec, options.noise])

  const runProofSheet = async () => {
    if (!spec || spec.kind !== 'circuit') return
    setProof({ sheet: null, loading: true, error: null })
    try {
      setProof({ sheet: await api.proofsheet(spec, options.noise), loading: false, error: null })
    } catch (e) {
      setProof({ sheet: null, loading: false, error: (e as Error).message })
    }
  }
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
    api.challenges().then((r) => setChallenges(r.challenges)).catch(() => { /* the board just stays hidden */ })
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
      if (analysis.spec.kind !== 'circuit') setChallenge(null)  // a network cannot answer a circuit puzzle
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
    setChallenge(null)
    setSpec(s)
    setStage('edit')
  }

  const code = examples?.specs.find((e) => e.id === 'bit_flip_code')
  const tryCode = code ? () => onSpec(clone(code.spec)) : undefined

  const onText = async (text: string, voice?: ModelCall) => {
    setBusy(true)
    setStartError(null)
    try {
      const draft = await api.fromText(text)
      setSketch(null)
      setFromText({ text, notes: draft.notes, call: draft.call, voice })
      if (draft.spec.kind !== 'circuit') setChallenge(null)
      setSpec(draft.spec)
      setStage('edit')
    } catch (e) {
      setStartError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  /** Stream a job's log (replayed from the start) into state, and note its outcome in the recent list. */
  const follow = (jobId: string) => {
    stopRef.current = followJob(
      jobId,
      (ev) => {
        setJob((j) => (j && j.id === jobId ? { ...j, events: [...j.events, ev] } : j))
        if ((ev.step === 'explain' || ev.step === 'diagram') && ev.status === 'running') {
          // the result is stored before these start: show it while the explanation and diagram finish
          api.job(jobId).then((s) => setJob((j) => (j && j.id === jobId && s.result ? { ...j, result: s.result } : j))).catch(() => {})
        }
      },
      async (status, error) => {
        const summary = await api.job(jobId).catch(() => null)
        setJob((j) => (j && j.id === jobId
          ? { ...j, live: false, status: summary?.status ?? status, error: summary?.error ?? error, result: summary?.result ?? null }
          : j))
        setRecent((r) => r.map((x) => (x.id === jobId ? { ...x, outcome: outcomeOf(summary) } : x)))
      },
    )
  }

  const openJob = async (jobId: string) => {
    stopRef.current?.()
    try {
      const s = await api.job(jobId)
      setSketch(null)
      setFromText(null)
      setChallenge(null)
      setSpec(s.spec)
      setJob({ id: jobId, spec: s.spec, events: [], live: s.status === 'running' || s.status === 'queued',
               status: s.status, error: s.error, result: s.result })
      setStage('run')
      follow(jobId)
    } catch (e) {
      setRecent((r) => r.filter((x) => x.id !== jobId))
      setStartError(`That run is no longer available (${(e as Error).message}).`)
    }
  }

  const run = async () => {
    if (!spec) return
    stopRef.current?.()
    try {
      const { job_id } = await api.startJob(spec, options)
      setJob({ id: job_id, spec, events: [], live: true, status: 'running', error: null, result: null })
      setStage('run')
      setRecent((r) => [{ id: job_id, title: specTitle(spec), kind: spec.kind, started: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), outcome: null }, ...r].slice(0, 8))
      follow(job_id)
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
          <div><h1>Inkubit</h1><p>sketch → proven quantum results</p></div>
        </div>
        <nav className="steps" aria-label="Steps">
          <button className={`step ${stage === 'start' ? 'active' : 'done'}`} onClick={() => setStage('start')}><span className="n">1</span>Sketch</button>
          <button className={`step ${stage === 'edit' ? 'active' : spec ? 'done' : ''}`} disabled={!spec} onClick={() => setStage('edit')}><span className="n">2</span>Check the spec</button>
          <button className={`step ${stage === 'run' ? 'active' : job?.result ? 'done' : ''}`} disabled={!job} onClick={() => setStage('run')}><span className="n">3</span>Run &amp; verify</button>
        </nav>
        <span className="spacer" />
        <button className="btn small primary" onClick={() => { setStage('start'); setTouring(true) }} title="Under two minutes: the best of Inkubit, step by step">Guided tour</button>
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
        <>
          {touring && (
            <Tour onClose={() => setTouring(false)} onGo={(section: TourSection, panel: string) => {
              if (section === null) setAssistant('mission')
              else goTab(section)
              window.setTimeout(() => scrollToPanel(panel, true), 250)
              window.setTimeout(() => scrollToPanel(panel, true), 1300)
            }} />
          )}
          {challenge && (
            <div className="notice row wrap" style={{ gap: 10, marginBottom: 16 }}>
              <span>Challenge in progress: <strong>{challenge.title}</strong>. Draw your answer on paper and photograph it,
                or describe it in words: the result is scored as soon as it reaches the editor.</span>
              <span className="spacer" />
              <button className="btn small" onClick={() => setStage('edit')} disabled={!spec}>Back to the challenge</button>
            </div>
          )}
          <Hero onTour={() => setTouring(true)} onMission={() => {
            setAssistant('mission')
            const panel = document.querySelector<HTMLElement>('.panel.mission')
            panel?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            window.setTimeout(() => panel?.querySelector<HTMLTextAreaElement>('.mission-goal')?.focus({ preventScroll: true }), 450)
          }} />
          <div className="hero-switch" role="tablist" aria-label="Assistant">
            <button role="tab" aria-selected={assistant === 'mission'} className={assistant === 'mission' ? 'on' : ''} onClick={() => setAssistant('mission')}>
              <b>Mission control</b><span>a whole problem: planned, run in parallel, verified</span></button>
            <button role="tab" aria-selected={assistant === 'ask'} className={assistant === 'ask' ? 'on' : ''} onClick={() => setAssistant('ask')}>
              <b>Quick question</b><span>one answer from the exact tools</span></button>
          </div>
          <div style={{ display: assistant === 'mission' ? 'block' : 'none' }}>
            <MissionPanel live={health?.mode === 'meta'} examples={examples} onOpen={(s) => onSpec(clone(s))} />
          </div>
          <div style={{ display: assistant === 'ask' ? 'block' : 'none' }}>
            <CopilotPanel live={health?.mode === 'meta'} onOpen={(s) => onSpec(clone(s))} />
          </div>
          <nav className="section-tabs" role="tablist" aria-label="Sections">
            {SECTIONS.map((t) => (
              <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''} onClick={() => goTab(t.id)}>
                <img src={`/usecases/${t.art}.webp`} alt="" width={48} height={48} />
                <span className="tab-text">{t.label}<span>{t.hint}</span></span>
              </button>
            ))}
          </nav>
          {seen.has('build') && (
            <div hidden={tab !== 'build'}>
            <StartPanel examples={examples} busy={busy} error={startError} onImage={onImage} onSpec={onSpec} onText={onText}
              live={health?.mode === 'meta'} recent={recent} onOpen={openJob}
              extra={<>
                <LiveBoardPanel live={health?.mode === 'meta'} onOpen={(s) => onSpec(clone(s))} />
                <RosettaPanel live={health?.mode === 'meta'} onOpen={(s) => onSpec(clone(s))} />
                <UseCases examples={examples} onImage={onImage} onSpec={onSpec} busy={busy} />
              </>} />
            </div>
          )}
          {seen.has('discover') && (
            <div hidden={tab !== 'discover'}>
            <div className="stack section-body">
              <DiscoveryPanel live={health?.mode === 'meta'} onOpen={(s) => onSpec(clone(s))} />
              <LearningPanel live={health?.mode === 'meta'} />
              <EstimatorPanel live={health?.mode === 'meta'} />
              <ReproducePanel live={health?.mode === 'meta'} onOpen={(s) => onSpec(clone(s))} />
              <PaperPanel live={health?.mode === 'meta'} />
            </div>
            </div>
          )}
          {seen.has('hardware') && (
            <div hidden={tab !== 'hardware'}>
            <div className="stack section-body">
              <IbmPanel spec={spec && spec.kind === 'circuit' ? spec : null} />
              <PulsePanel />
              <DecoderPanel />
              <CodesPanel />
              <RepetitionLabPanel onTry={tryCode} />
              <DistributedPanel examples={examples} onOpen={(s) => onSpec(clone(s))} />
              <GlobePanel />
            </div>
            </div>
          )}
          {seen.has('labs') && (
            <div hidden={tab !== 'labs'}>
            <div className="stack section-body">
              <ShorLabPanel onOpen={(s) => onSpec(clone(s))} />
              <QaoaLabPanel onOpen={(s) => onSpec(clone(s))} />
              <ChemLabPanel onOpen={(s) => onSpec(clone(s))} />
              <QkdLabPanel onOpen={(s) => onSpec(clone(s))} />
              <BugHuntPanel live={health?.mode === 'meta'} onOpen={(s) => onSpec(clone(s))} />
              <ChallengeList list={challenges} progress={progress} onStart={startChallenge} />
            </div>
            </div>
          )}
          {seen.has('evidence') && (
            <div hidden={tab !== 'evidence'}>
            <div className="stack section-body">
              <HardwarePanel />
              <ProofBenchPanel />
              <ObservatoryPanel />
              <ArenaPanel />
              <RefereePanel live={health?.mode === 'meta'} />
            </div>
            </div>
          )}
        </>
      )}

      {stage === 'edit' && spec && (
        <div className="stack">
          {challenge && spec.kind === 'circuit' && (
            <ChallengePanel ch={challenge} spec={spec} best={progress[challenge.id] ?? 0}
              onScore={(n) => score(challenge.id, n)} hasNext={!!nextChallenge}
              onNext={() => nextChallenge && startChallenge(nextChallenge)}
              onExit={() => { setChallenge(null); setStage('start') }} />
          )}
          {fromText && (
            <div className="notice row wrap" style={{ gap: 8 }}>
              <span>{fromText.voice ? 'Built from what you said' : 'Built from your words'}: <em>“{fromText.text}”</em></span>
              {fromText.voice && <CallBadge call={fromText.voice} />}<CallBadge call={fromText.call} />
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
            <SpecEditor spec={spec} issues={issues} highlight={highlight} onPick={setHighlight} onChange={setSpec}
              allowed={challenge?.allowed} valid={issues.length === 0 && !checking} optimizer={!challenge} />
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
            <span className="label">Explain in</span>
            <select value={options.language} onChange={(e) => setOptions({ ...options, language: e.target.value })} aria-label="Explanation language">
              {(examples?.languages ?? ['English']).map((l) => <option key={l}>{l}</option>)}
            </select>
            <div className="run-actions">
              {startError && <span className="badge fail">{startError}</span>}
              <button className="btn big ghost" onClick={shareLink} title="Copy a link that opens this spec">{shared ?? 'Share link'}</button>
              {spec.kind === 'circuit' && (
                <button className="btn big" disabled={!valid || preview?.loading} onClick={stepThrough}
                  title="See the exact state after every gate, the entanglement and the noise budget, without running">
                  {preview?.loading ? 'Analysing…' : 'Step through'}
                </button>
              )}
              {spec.kind === 'circuit' && (
                <button className="btn big" disabled={!valid || proof?.loading} onClick={runProofSheet}
                  title="Run every independent check on this circuit: two simulators of each kind, physics, the compiler, exports, statistics, the generated code, metamorphic tests">
                  {proof?.loading ? 'Proving…' : 'Proof sheet'}
                </button>
              )}
              {spec.kind === 'circuit' && <IbmRunButton spec={spec} valid={valid} />}
              <button className="btn primary big" disabled={!valid} onClick={run}>
                {checking ? 'Checking…' : issues.length ? 'Fix the spec to run' : `Run ${specTitle(spec)}`}
              </button>
            </div>
          </div>
          {preview?.error && <div className="notice error">{preview.error}</div>}
          {proof?.error && <div className="notice error">{proof.error}</div>}
          {proof?.sheet && spec.kind === 'circuit' && <ProofSheetView sheet={proof.sheet} />}
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
            {job.result && 'verified' in job.result && <CircuitResults result={job.result} sketchCalls={sketchCalls} spec={job.spec as CircuitSpec} jobId={job.id} />}
            {job.result && 'before' in job.result && (
              <NetworkResults result={job.result} sketchCalls={sketchCalls} jobId={job.id} spec={job.spec as NetworkSpec} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
