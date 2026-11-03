import type { LBench } from './components/Learning'
import type { RBench } from './components/Referee'
import type { PResult } from './components/Paper'
import type { CodesLab } from './components/Codes'
import type {
  AgentEvent, ArenaBenchmark, ChemLab, DiscoveryGoal, DistributedResult, EstimateResult, LiveRead, OrbitMeta, OrbitPlan, Reproduction, DecoderReport, PulseReport, HardwareRuns, DiscoveryHardware, ProofSheet, ProofBench, IbmStatus, IbmSnapshot, IbmAdvice, IbmRun, IbmExperiments, MlReport, Observatory, CopilotReply, NotationRead, RosettaEntry, RosettaResult, QkdLab, ArenaResult, BugGuess, BugRound, BugVerdict, ChallengeCheck, ChallengeInfo, CircuitInsights, Examples, Explanation, Health, JobSummary, LiveState, OptimizeResult, QaoaLab, RepetitionLab, ShorLab, RunOptions, Transcript,
  SketchAnalysis, Spec, SpecIssue, TextDraft, Headline,
} from './types'

export class ApiError extends Error {
  status: number
  issues: SpecIssue[]
  constructor(message: string, status: number, issues: SpecIssue[] = []) {
    super(message)
    this.status = status
    this.issues = issues
  }
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  let resp: Response
  try {
    resp = await fetch(url, init)
  } catch {
    throw new ApiError('Cannot reach the Inkubit backend. Is it running on port 8000?', 0)
  }
  if (!resp.ok) {
    let detail: unknown = resp.statusText
    try {
      detail = (await resp.json()).detail
    } catch { /* not JSON */ }
    if (detail && typeof detail === 'object' && 'issues' in (detail as object)) {
      const d = detail as { message: string; issues: SpecIssue[] }
      throw new ApiError(d.message, resp.status, d.issues)
    }
    throw new ApiError(String(detail), resp.status)
  }
  return resp.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => call<Health>('/api/health'),
  headline: () => call<Headline>('/api/headline'),
  examples: () => call<Examples>('/api/examples'),
  validate: (spec: unknown) =>
    call<{ valid: boolean; issues: SpecIssue[]; spec?: Spec }>('/api/spec/validate', json({ spec })),
  analyzeImage: (file: Blob, name = 'sketch.png') => {
    const form = new FormData()
    form.append('file', file, name)
    return call<SketchAnalysis>('/api/jobs/image', { method: 'POST', body: form })
  },
  startJob: (spec: Spec, options: RunOptions) =>
    call<{ job_id: string; kind: string }>('/api/jobs/spec', json({ spec, options })),
  job: (id: string) => call<JobSummary>(`/api/jobs/${id}`),
  ask: (jobId: string, question: string) => call<Explanation>(`/api/jobs/${jobId}/ask`, json({ question })),
  fromText: (text: string) => call<TextDraft>('/api/jobs/text', json({ text })),
  transcribe: (audio: Blob) => {
    const form = new FormData()
    form.append('audio', audio, 'speech.wav')
    return call<Transcript>('/api/transcribe', { method: 'POST', body: form })
  },
  insights: (spec: Spec, noise: string) => call<CircuitInsights>('/api/insights', json({ spec, noise })),
  state: (spec: Spec, noise: string, scale?: number, signal?: AbortSignal) =>
    call<LiveState>('/api/state', { ...json({ spec, noise, scale }), signal }),
  repetitionLab: (scale: number, signal?: AbortSignal) =>
    call<RepetitionLab>(`/api/lab/repetition?scale=${scale.toPrecision(3)}`, { signal }),
  copilot: (message: string, history: { role: string; content: string }[], deep = false) =>
    call<CopilotReply>('/api/copilot', json({ message, history, deep })),
  rosetta: (text: string) => call<RosettaResult>('/api/rosetta', json({ text })),
  rosettaDictionary: () => call<{ entries: RosettaEntry[] }>('/api/rosetta/dictionary'),
  rosettaPhoto: (file: Blob) => {
    const form = new FormData()
    form.append('file', file, 'notation.jpg')
    return call<NotationRead>('/api/rosetta/photo', { method: 'POST', body: form })
  },
  observatory: () => call<Observatory>('/api/observatory'),
  startMission: (goal: string, opts: { image?: Blob | null; transcript?: string; deep?: boolean }) => {
    const form = new FormData()
    form.append('goal', goal)
    form.append('transcript', opts.transcript ?? '')
    form.append('deep', opts.deep ? 'true' : 'false')
    if (opts.image) form.append('image', opts.image, 'photo.png')
    return call<{ mission_id: string; events_url: string }>('/api/missions', { method: 'POST', body: form })
  },
  mlReport: () => call<MlReport>('/api/mlverify/report'),
  discoveryGoals: () => call<{ goals: DiscoveryGoal[] }>('/api/discovery/goals'),
  distributed: (spec: Spec, medium: string, km: number) => call<DistributedResult>('/api/distributed', json({ spec, medium, km })),
  liveRead: (frame: Blob) => {
    const form = new FormData()
    form.append('file', frame, 'frame.jpg')
    return call<LiveRead>('/api/live/read', { method: 'POST', body: form })
  },
  orbitCities: () => call<OrbitMeta>('/api/orbits/cities'),
  orbits: (a: string, b: string, night: boolean, sat: string) => call<OrbitPlan>(`/api/orbits?a=${a}&b=${b}&night=${night}&sat=${sat}`),
  reproduce: (text: string, image: Blob | null) => {
    const form = new FormData()
    form.append('text', text)
    if (image) form.append('image', image, 'figure.png')
    return call<Reproduction>('/api/reproduce', { method: 'POST', body: form })
  },
  decoder: (p: number, seed: number, d = 3) => call<DecoderReport>(`/api/decoder?p=${p}&seed=${seed}&d=${d}`),
  pulse: (duration: number, drag: boolean) => call<PulseReport>(`/api/pulse?duration=${duration}&drag=${drag}`),
  hardware: () => call<HardwareRuns>('/api/hardware'),
  discoveryHardware: () => call<DiscoveryHardware>('/api/hardware/discovery'),
  proofsheet: (spec: unknown, noise: string) => call<ProofSheet>('/api/proofsheet', json({ spec, noise })),
  proofBench: () => call<ProofBench>('/api/proofsheet/benchmark'),
  ibmStatus: (live = false) => call<IbmStatus>(`/api/ibm/status${live ? '?live=true' : ''}`),
  ibmDevice: (name: string) => call<IbmSnapshot>(`/api/ibm/device/${encodeURIComponent(name)}`),
  ibmAdvise: (spec: unknown) => call<{ advice: IbmAdvice[] }>('/api/ibm/advise', json({ spec })),
  ibmRun: (spec: unknown, shots: number) => call<IbmRun>('/api/ibm/run', json({ spec, shots })),
  ibmRunStatus: (id: string) => call<IbmRun>(`/api/ibm/run/${encodeURIComponent(id)}`),
  ibmExperiments: () => call<IbmExperiments>('/api/ibm/experiments'),
  estimatePresets: () => call<{ presets: { id: string; label: string }[]; hardware: { id: string; label: string }[] }>('/api/estimate/presets'),
  estimate: (q: { preset?: string; text?: string; hardware: string }) => call<EstimateResult>('/api/estimate', json(q)),
  startDiscovery: (what: { goal?: string; ket?: string }, deep: boolean) =>
    call<{ discovery_id: string; events_url: string }>('/api/discovery', json({ ...what, deep })),
  chemLab: (r: number, signal?: AbortSignal) => call<ChemLab>(`/api/lab/chem?r=${r.toFixed(2)}`, { signal }),
  qkdLab: (q: { photons: number; eve: number; noise: number; seed: number }, signal?: AbortSignal) =>
    call<QkdLab>(`/api/lab/qkd?photons=${q.photons}&eve=${q.eve}&noise=${q.noise}&seed=${q.seed}`, { signal }),
  arena: (spec: Spec) => call<ArenaResult>('/api/arena', json({ spec })),
  learningBenchmark: () => call<LBench>('/api/learning/benchmark'),
  refereeBenchmark: () => call<RBench>('/api/referee/benchmark'),
  startReferee: (index: number) => call<{ referee_id: string }>('/api/referee', json({ index })),
  referee: (id: string) => call<{ status: string; error: string | null; result: unknown }>(`/api/referee/${id}`),
  paperExamples: () => call<{ papers: PResult[] }>('/api/paper/examples'),
  startPaper: (arxiv: string, pdf: File | null) => {
    const form = new FormData()
    form.append('arxiv', arxiv)
    if (pdf) form.append('pdf', pdf, pdf.name)
    return call<{ paper_id: string }>('/api/paper', { method: 'POST', body: form })
  },
  paper: (id: string) => call<{ status: string; error: string | null; result: unknown }>(`/api/paper/${id}`),
  codesLab: () => call<CodesLab>('/api/codes'),
  analyseCode: (generators: string[]) => call<{ generators: string[]; valid: boolean; note: string; n: number; k: number; d: number | null; dx: number | null; dz: number | null; css: boolean; logical: string | null }>('/api/codes/analyse', json({ generators })),
  startLearning: (goal: string) => call<{ learning_id: string; events_url: string }>('/api/learning', json({ goal })),
  arenaBenchmark: (model = 'spark') => call<ArenaBenchmark>(`/api/arena/benchmark?model=${model}`),
  bugRound: (level: number, seed: number, signal?: AbortSignal) =>
    call<BugRound>(`/api/bughunt/round?level=${level}&seed=${seed}`, { signal }),
  bugGuess: (level: number, seed: number, index: number) => call<BugVerdict>('/api/bughunt/guess', json({ level, seed, index })),
  bugMuse: (level: number, seed: number) => call<BugGuess>('/api/bughunt/muse', json({ level, seed })),
  qaoaLab: (graph: { n: number; edges: [number, number][]; labels?: string[] }, signal?: AbortSignal) =>
    call<QaoaLab>('/api/lab/qaoa', { ...json(graph), signal }),
  shorLab: (a: number, signal?: AbortSignal) => call<ShorLab>(`/api/lab/shor?a=${a}`, { signal }),
  optimize: (spec: Spec, ai = true) => call<OptimizeResult>('/api/optimize', json({ spec, ai })),
  challenges: () => call<{ levels: Record<string, string>; challenges: ChallengeInfo[] }>('/api/challenges'),
  checkChallenge: (id: string, spec: Spec, signal?: AbortSignal) =>
    call<ChallengeCheck>(`/api/challenges/${id}/check`, { ...json({ spec }), signal }),
  hint: (id: string, spec: Spec, number: number) => call<Explanation>(`/api/challenges/${id}/hint`, json({ spec, number })),
}

/** Follow a job's live log. Returns a function that stops listening. */
export function followJob(
  id: string,
  onEvent: (e: AgentEvent) => void,
  onEnd: (status: string, error: string | null) => void,
): () => void {
  const source = new EventSource(`/api/jobs/${id}/events`)
  let ended = false
  source.addEventListener('log', (msg) => onEvent(JSON.parse((msg as MessageEvent).data)))
  source.addEventListener('end', (msg) => {
    ended = true
    const data = JSON.parse((msg as MessageEvent).data)
    source.close()
    onEnd(data.status, data.error)
  })
  source.onerror = () => {
    if (!ended) {
      source.close()
      onEnd('disconnected', 'The live log connection dropped.')
    }
  }
  return () => source.close()
}
