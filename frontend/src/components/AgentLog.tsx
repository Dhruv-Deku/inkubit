import { Fragment, useEffect, useRef } from 'react'
import type { AgentEvent, ModelCall } from '../types'
import { CallBadge } from './CallBadge'
import { DiffView } from './CodeViewer'
import { StatusIcon } from './Icons'

const STEP_LABEL: Record<string, string> = {
  plan: 'Plan', generate: 'Write code', inject: 'Demo fault', run: 'Run', verify: 'Verify', diagnose: 'Diagnose',
  repair: 'Repair', network: 'Network', explain: 'Explain', diagram: 'Diagram', done: 'Result', bottleneck: 'Bottleneck',
  fix: 'Fix', check: 'Check',
}

/** Streaming, plain-language log of everything the agent does. */
export function AgentLog({ events, live }: { events: AgentEvent[]; live: boolean }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [events.length])
  if (!events.length) return <div className="empty">{live ? 'Starting…' : 'No log yet.'}</div>
  let lastAttempt: number | null = null
  return (
    <div className="log" aria-live="polite">
      {events.map((e, i) => {
        const isLast = i === events.length - 1
        const sep = e.attempt !== null && e.attempt !== lastAttempt && e.step === 'run'
        if (e.attempt !== null) lastAttempt = e.attempt
        const call = e.details.call as ModelCall | undefined
        const diff = e.details.diff as string | undefined
        const code = e.details.code as string | undefined
        const stderr = e.details.stderr as string | undefined
        const doneCls = e.step === 'done' ? (e.status === 'ok' ? 'done-ok' : 'done-fail') : ''
        return (
          <Fragment key={e.seq}>
            {sep && <div className="attempt-sep">Attempt {e.attempt}</div>}
            <div className={`ev ${e.status} ${doneCls}`}>
              <div className="ic"><StatusIcon status={e.status} live={live && isLast} /></div>
              <div>
                <div className="meta">
                  <span>{STEP_LABEL[e.step] ?? e.step}</span>
                  <span>{e.timestamp.slice(11, 19)}</span>
                  {call && <CallBadge call={call} />}
                </div>
                <div className="msg">{e.message}</div>
                {diff && (
                  <details className="more" open={e.step === 'repair'}>
                    <summary>{e.step === 'inject' ? 'What was broken' : 'What the repair changed'}</summary>
                    <DiffView diff={diff} />
                  </details>
                )}
                {code && (
                  <details className="more"><summary>Show the script</summary><pre className="code">{code}</pre></details>
                )}
                {stderr && e.status === 'fail' && (
                  <details className="more"><summary>Show the error output</summary><pre className="code">{stderr}</pre></details>
                )}
              </div>
            </div>
          </Fragment>
        )
      })}
      <div ref={end} />
    </div>
  )
}
