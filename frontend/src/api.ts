import type {
  AgentEvent, CircuitInsights, Examples, Health, JobSummary, RunOptions, SketchAnalysis, Spec, SpecIssue,
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
    throw new ApiError('Cannot reach the Q-Canvas backend. Is it running on port 8000?', 0)
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
  insights: (spec: Spec, noise: string) => call<CircuitInsights>('/api/insights', json({ spec, noise })),
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
